"""Greedy baseline planner (F6): sort bookings by priority descending then
original departure time, assign the lowest-delay feasible option, and
decrement the in-memory inventory snapshot as it goes."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from reflight.core.models import Booking, BookingSegment, Flight, Passenger
from reflight.core.priority import compute_priority
from reflight.planner.candidates import AirlineFlightCache, generate_candidates


@dataclass
class BookingPlanInput:
    booking_id: str
    airline_id: str
    origin: str
    dest: str
    preferred_cabin: str
    not_before: datetime
    original_arrival: datetime
    original_departure: datetime
    priority: int


@dataclass
class PlanResult:
    booking_id: str
    priority: int
    segments: list[dict[str, Any]] | None
    delay_minutes: float | None


def load_plan_inputs(db: Session, booking_ids: list[str]) -> list[BookingPlanInput]:
    rows = db.execute(
        select(Booking, Passenger, BookingSegment, Flight)
        .join(Passenger, Passenger.id == Booking.passenger_id)
        .join(BookingSegment, BookingSegment.booking_id == Booking.id)
        .join(Flight, Flight.id == BookingSegment.flight_id)
        .where(Booking.id.in_(booking_ids))
        .order_by(Booking.id, BookingSegment.seq)
    ).all()

    by_booking: dict[str, list[tuple]] = {}
    for booking, passenger, segment, flight in rows:
        by_booking.setdefault(booking.id, []).append((booking, passenger, segment, flight))

    inputs = []
    for booking_id, entries in by_booking.items():
        entries.sort(key=lambda e: e[2].seq)
        booking, passenger, _, first_flight = entries[0]
        _, _, _, last_flight = entries[-1]
        has_connection = len(entries) > 1
        priority = compute_priority(
            tier=passenger.tier,
            is_unaccompanied_minor=passenger.is_unaccompanied_minor,
            has_connection=has_connection,
        )
        inputs.append(
            BookingPlanInput(
                booking_id=booking_id,
                airline_id=passenger.airline_id,
                origin=first_flight.origin,
                dest=last_flight.dest,
                preferred_cabin=entries[0][2].cabin,
                not_before=first_flight.sched_dep_at,
                original_arrival=last_flight.sched_arr_at,
                original_departure=first_flight.sched_dep_at,
                priority=priority,
            )
        )
    return inputs


def plan_greedy(
    db: Session,
    cache: AirlineFlightCache,
    booking_ids: list[str],
    inventory_snapshot: dict[tuple[str, str], int],
) -> list[PlanResult]:
    inputs = load_plan_inputs(db, booking_ids)
    inputs.sort(key=lambda b: (-b.priority, b.original_departure))

    results = []
    for b in inputs:
        candidates = generate_candidates(
            cache,
            b.airline_id,
            b.origin,
            b.dest,
            b.preferred_cabin,
            b.not_before,
            b.original_arrival,
            inventory_snapshot,
        )
        if not candidates:
            results.append(PlanResult(b.booking_id, b.priority, None, None))
            continue

        chosen = candidates[0]
        for seg in chosen["segments"]:
            key = (seg["flight_id"], seg["cabin"])
            inventory_snapshot[key] = inventory_snapshot.get(key, 0) - 1

        results.append(PlanResult(b.booking_id, b.priority, chosen["segments"], chosen["delay_minutes"]))

    return results
