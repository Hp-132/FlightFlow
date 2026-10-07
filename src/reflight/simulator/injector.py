"""Applies a scenario's disruption timeline to a run: cancels flights,
pushes delayed flights out (F2b cascades), marks the bookings those break
as DISRUPTED, and emits batched plan.requested outbox rows.

For P0 this runs synchronously and applies the whole timeline at once when
/runs/{id}/start is called. A paced, SimPy-driven replay (the "simulator"
job posting events at --speed) is the natural next step but is not needed
to prove out the saga/outbox/relay machinery, so it is deferred rather than
half-built now.
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from reflight.core.constants import (
    BOOKING_ACTIVE,
    BOOKING_DISRUPTED,
    EVENT_CANCELLATION,
    EVENT_DELAY,
    FLIGHT_CANCELLED,
    FLIGHT_DELAYED,
)
from reflight.core.metrics import disruption_events_total
from reflight.core.models import Booking, BookingSegment, DisruptionEvent, Flight
from reflight.core.outbox import enqueue
from reflight.core.rabbitmq import ROUTING_PLAN_REQUESTED
from reflight.core.storage import get_json

PLAN_BATCH_SIZE = 500
MIN_CONNECTION_MINUTES = 45


def apply_timeline(db: Session, run_id: str, scenario_minio_key: str) -> dict[str, Any]:
    scenario = get_json(scenario_minio_key)
    timeline = scenario["timeline"]

    cancelled_ids: set[str] = set()
    delay_by_flight: dict[str, int] = {}

    for event in timeline:
        db.add(
            DisruptionEvent(
                run_id=run_id,
                type=event["type"],
                cause=event["cause"],
                target_flight_id=event.get("target_flight_id"),
                target_airport_id=event.get("target_airport_id"),
                delay_minutes=event.get("delay_minutes"),
                occurred_at=datetime.fromisoformat(event["occurred_at"]),
            )
        )
        disruption_events_total.add(1, {"cause": event["cause"]})

        flight_id = event.get("target_flight_id")
        if not flight_id:
            continue
        if event["type"] == EVENT_CANCELLATION:
            cancelled_ids.add(flight_id)
        elif event["type"] == EVENT_DELAY and event.get("delay_minutes"):
            # a later cancellation on the same leg wins
            delay_by_flight[flight_id] = int(event["delay_minutes"])

    delay_by_flight = {fid: d for fid, d in delay_by_flight.items() if fid not in cancelled_ids}

    if cancelled_ids:
        db.execute(
            Flight.__table__.update()
            .where(Flight.id.in_(cancelled_ids))
            .values(status=FLIGHT_CANCELLED)
        )

    for flight_id, minutes in delay_by_flight.items():
        db.execute(
            Flight.__table__.update()
            .where(Flight.id == flight_id)
            .values(
                status=FLIGHT_DELAYED,
                dep_at=Flight.__table__.c.sched_dep_at + timedelta(minutes=minutes),
                arr_at=Flight.__table__.c.sched_arr_at + timedelta(minutes=minutes),
            )
        )

    disrupted = _bookings_hit_by_cancellations(db, cancelled_ids)
    disrupted |= _bookings_with_broken_connections(db, delay_by_flight)

    if disrupted:
        db.execute(
            Booking.__table__.update().where(Booking.id.in_(disrupted)).values(status=BOOKING_DISRUPTED)
        )

    booking_id_list = sorted(disrupted)
    batches = 0
    for i in range(0, len(booking_id_list), PLAN_BATCH_SIZE):
        batch = booking_id_list[i : i + PLAN_BATCH_SIZE]
        enqueue(db, ROUTING_PLAN_REQUESTED, {"run_id": run_id, "booking_ids": batch})
        batches += 1

    return {
        "disruption_events": len(timeline),
        "cancelled_flights": len(cancelled_ids),
        "delayed_flights": len(delay_by_flight),
        "disrupted_bookings": len(disrupted),
        "plan_batches_queued": batches,
    }


def _bookings_hit_by_cancellations(db: Session, cancelled_ids: set[str]) -> set[str]:
    if not cancelled_ids:
        return set()
    rows = db.execute(
        select(Booking.id)
        .join(BookingSegment, BookingSegment.booking_id == Booking.id)
        .where(BookingSegment.flight_id.in_(cancelled_ids), Booking.status == BOOKING_ACTIVE)
    ).all()
    return {r[0] for r in rows}


def _bookings_with_broken_connections(db: Session, delay_by_flight: dict[str, int]) -> set[str]:
    """A delay only disrupts a passenger if it breaks their onward
    connection -- a delayed direct flight still gets them there."""
    if not delay_by_flight:
        return set()

    candidate_ids = [
        r[0]
        for r in db.execute(
            select(Booking.id)
            .join(BookingSegment, BookingSegment.booking_id == Booking.id)
            .where(BookingSegment.flight_id.in_(delay_by_flight), Booking.status == BOOKING_ACTIVE)
        ).all()
    ]
    if not candidate_ids:
        return set()

    rows = db.execute(
        select(BookingSegment.booking_id, BookingSegment.seq, Flight.sched_dep_at, Flight.sched_arr_at, Flight.id)
        .join(Flight, Flight.id == BookingSegment.flight_id)
        .where(BookingSegment.booking_id.in_(candidate_ids))
        .order_by(BookingSegment.booking_id, BookingSegment.seq)
    ).all()

    itineraries: dict[str, list[tuple]] = {}
    for booking_id, seq, dep, arr, flight_id in rows:
        itineraries.setdefault(booking_id, []).append((seq, dep, arr, flight_id))

    broken: set[str] = set()
    for booking_id, segments in itineraries.items():
        segments.sort()
        # pairwise over consecutive legs; the offset slice is shorter by one
        for (_, _, arr, prev_id), (_, dep, _, next_id) in zip(segments, segments[1:], strict=False):
            actual_arr = arr + timedelta(minutes=delay_by_flight.get(prev_id, 0))
            actual_dep = dep + timedelta(minutes=delay_by_flight.get(next_id, 0))
            if actual_dep < actual_arr + timedelta(minutes=MIN_CONNECTION_MINUTES):
                broken.add(booking_id)
                break
    return broken
