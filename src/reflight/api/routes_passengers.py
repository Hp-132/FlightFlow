"""Passenger directory, booking creation and single-booking disruption.

Backs the Passenger History page: pick an existing passenger, or add one and
disrupt their flight so the normal planner -> saga -> worker pipeline handles
them end to end.
"""

import secrets
import string
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from reflight.api.deps import get_db, require_api_key
from reflight.api.schemas import CreatePassengerRequest, DisruptBookingRequest
from reflight.core.constants import (
    BOOKING_ACTIVE,
    EVENT_CANCELLATION,
    FLIGHT_CANCELLED,
    RUN_RUNNING,
)
from reflight.core.models import (
    Booking,
    BookingSegment,
    Flight,
    Passenger,
    Run,
    Scenario,
    SeatInventory,
)
from reflight.simulator.injector import apply_events

router = APIRouter(tags=["passengers"], dependencies=[Depends(require_api_key)])

PNR_ALPHABET = string.ascii_uppercase + string.digits
PNR_LENGTH = 6
PNR_ATTEMPTS = 5

# Mirrors the planner's candidate window (planner/candidates.py).
REBOOKING_WINDOW_HOURS = 48

SQL_LIST_PASSENGERS = """
WITH latest_saga AS (
    SELECT DISTINCT ON (booking_id) booking_id, id AS saga_id, state, created_at
    FROM sagas
    ORDER BY booking_id, created_at DESC
),
page AS (
    SELECT b.id AS booking_id, b.pnr, b.status AS booking_status, p.id AS passenger_id,
           p.name, ls.saga_id, ls.state AS saga_state, ls.created_at AS saga_at,
           (ls.saga_id IS NULL AND b.status = 'DISRUPTED') AS awaiting_saga,
           COUNT(*) OVER () AS total
    FROM bookings b
    JOIN passengers p ON p.id = b.passenger_id
    LEFT JOIN latest_saga ls ON ls.booking_id = b.id
    WHERE (:q = '' OR b.pnr ILIKE :like ESCAPE '\\' OR p.name ILIKE :like ESCAPE '\\')
      AND (NOT :only_history OR ls.saga_id IS NOT NULL)
    ORDER BY (ls.saga_id IS NULL AND b.status = 'DISRUPTED') DESC, ls.created_at DESC NULLS LAST, p.name, b.pnr
    LIMIT :limit
)
SELECT page.*, p.tier, a.code AS airline, seg.origin, seg.dest, seg.flights
FROM page
JOIN passengers p ON p.id = page.passenger_id
JOIN airlines a ON a.id = p.airline_id
JOIN LATERAL (
    SELECT (array_agg(o.iata ORDER BY bs.seq))[1]      AS origin,
           (array_agg(d.iata ORDER BY bs.seq DESC))[1] AS dest,
           string_agg(f.flight_no, ' + ' ORDER BY bs.seq) AS flights
    FROM booking_segments bs
    JOIN flights f  ON f.id = bs.flight_id
    JOIN airports o ON o.id = f.origin
    JOIN airports d ON d.id = f.dest
    WHERE bs.booking_id = page.booking_id
) seg ON true
ORDER BY page.awaiting_saga DESC, page.saga_at DESC NULLS LAST, page.name, page.pnr
"""

SQL_BOOKING_HEADER = """
SELECT b.id AS booking_id, b.pnr, b.status AS booking_status,
       p.name, p.tier, p.bags, p.is_unaccompanied_minor, p.airline_id, a.code AS airline
FROM bookings b
JOIN passengers p ON p.id = b.passenger_id
JOIN airlines a   ON a.id = p.airline_id
WHERE b.id = :booking_id
"""

SQL_BOOKING_SEGMENTS = """
SELECT bs.seq, bs.cabin, f.id AS flight_id, f.flight_no, f.status,
       f.sched_dep_at, f.dep_at, f.origin AS origin_id, f.dest AS dest_id,
       o.iata AS origin, d.iata AS dest
FROM booking_segments bs
JOIN flights f  ON f.id = bs.flight_id
JOIN airports o ON o.id = f.origin
JOIN airports d ON d.id = f.dest
WHERE bs.booking_id = :booking_id
ORDER BY bs.seq
"""

SQL_OTHERS_ON_FLIGHT = """
SELECT COUNT(*)
FROM booking_segments bs
JOIN bookings b ON b.id = bs.booking_id
WHERE bs.flight_id = :flight_id AND b.status = 'ACTIVE' AND b.id <> :booking_id
"""

SQL_DIRECT_ALTERNATIVES = f"""
SELECT COUNT(*)
FROM flights g
WHERE g.airline_id = :airline_id
  AND g.origin = :origin_id
  AND g.dest = :dest_id
  AND g.status <> 'CANCELLED'
  AND g.id <> :flight_id
  AND g.sched_dep_at BETWEEN :not_before AND :not_before + interval '{REBOOKING_WINDOW_HOURS} hours'
"""

SQL_LATEST_SAGA = """
SELECT id, state, run_id
FROM sagas
WHERE booking_id = :booking_id
ORDER BY created_at DESC
LIMIT 1
"""

SQL_LIST_FLIGHTS = f"""
WITH base AS (
    SELECT f.id, f.flight_no, a.code AS airline, o.iata AS origin, d.iata AS dest,
           f.sched_dep_at,
           COALESCE(SUM(si.available) FILTER (WHERE si.cabin = 'ECONOMY'), 0)  AS economy_available,
           COALESCE(SUM(si.available) FILTER (WHERE si.cabin = 'BUSINESS'), 0) AS business_available,
           (SELECT COUNT(*) FROM flights g
             WHERE g.airline_id = f.airline_id AND g.origin = f.origin AND g.dest = f.dest
               AND g.status <> 'CANCELLED' AND g.id <> f.id
               AND g.sched_dep_at BETWEEN f.sched_dep_at
                                      AND f.sched_dep_at + interval '{REBOOKING_WINDOW_HOURS} hours'
           ) AS direct_alternatives
    FROM flights f
    JOIN airlines a ON a.id = f.airline_id
    JOIN airports o ON o.id = f.origin
    JOIN airports d ON d.id = f.dest
    LEFT JOIN seat_inventory si ON si.flight_id = f.id
    WHERE f.status <> 'CANCELLED'
      AND (:q = '' OR f.flight_no ILIKE :like ESCAPE '\\'
                   OR o.iata ILIKE :like ESCAPE '\\'
                   OR d.iata ILIKE :like ESCAPE '\\'
                   OR (o.iata || '-' || d.iata) ILIKE :like ESCAPE '\\')
    GROUP BY f.id, a.code, o.iata, d.iata
    HAVING COALESCE(SUM(si.available), 0) > 0
)
SELECT * FROM base
ORDER BY (direct_alternatives = 0), sched_dep_at, flight_no
LIMIT :limit
"""


def new_pnr() -> str:
    return "".join(secrets.choice(PNR_ALPHABET) for _ in range(PNR_LENGTH))


def _unused_pnr(db: Session) -> str:
    for _ in range(PNR_ATTEMPTS):
        pnr = new_pnr()
        if db.execute(select(Booking.id).where(Booking.pnr == pnr)).first() is None:
            return pnr
    raise HTTPException(status_code=503, detail="could not allocate a booking reference, try again")


def _like(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@router.get("/passengers")
def list_passengers(
    q: str = Query("", max_length=60, description="match against PNR or passenger name"),
    history: Literal["all", "with"] = Query("all", description="'with' keeps passengers that have a saga"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    q = q.strip()
    rows = db.execute(
        text(SQL_LIST_PASSENGERS),
        {"q": q, "like": _like(q), "only_history": history == "with", "limit": limit},
    ).all()
    return {
        "total": rows[0].total if rows else 0,
        "items": [
            {
                "booking_id": r.booking_id,
                "pnr": r.pnr,
                "name": r.name,
                "tier": r.tier,
                "airline": r.airline,
                "origin": r.origin,
                "dest": r.dest,
                "flights": r.flights,
                "booking_status": r.booking_status,
                "saga_id": r.saga_id,
                "saga_state": r.saga_state,
            }
            for r in rows
        ],
    }


@router.get("/passengers/{booking_id}")
def get_passenger(booking_id: UUID, db: Session = Depends(get_db)) -> dict:
    booking_id = str(booking_id)
    header = db.execute(text(SQL_BOOKING_HEADER), {"booking_id": booking_id}).first()
    if header is None:
        raise HTTPException(status_code=404, detail="passenger not found")

    segments = db.execute(text(SQL_BOOKING_SEGMENTS), {"booking_id": booking_id}).all()
    if not segments:
        raise HTTPException(status_code=404, detail="booking has no itinerary")
    first, last = segments[0], segments[-1]

    others_on_flight = db.execute(
        text(SQL_OTHERS_ON_FLIGHT), {"flight_id": first.flight_id, "booking_id": booking_id}
    ).scalar_one()
    direct_alternatives = db.execute(
        text(SQL_DIRECT_ALTERNATIVES),
        {
            "airline_id": header.airline_id,
            "origin_id": first.origin_id,
            "dest_id": last.dest_id,
            "flight_id": first.flight_id,
            "not_before": first.sched_dep_at,
        },
    ).scalar_one()
    saga = db.execute(text(SQL_LATEST_SAGA), {"booking_id": booking_id}).first()

    return {
        "booking_id": header.booking_id,
        "pnr": header.pnr,
        "booking_status": header.booking_status,
        "passenger": {
            "name": header.name,
            "tier": header.tier,
            "bags": header.bags,
            "is_unaccompanied_minor": header.is_unaccompanied_minor,
            "airline": header.airline,
        },
        "segments": [
            {
                "seq": s.seq,
                "cabin": s.cabin,
                "flight_id": s.flight_id,
                "flight_no": s.flight_no,
                "status": s.status,
                "origin": s.origin,
                "dest": s.dest,
                "sched_dep_at": _iso(s.sched_dep_at),
                "dep_at": _iso(s.dep_at),
            }
            for s in segments
        ],
        "others_on_flight": others_on_flight,
        "direct_alternatives": direct_alternatives,
        "saga": {"id": saga.id, "state": saga.state, "run_id": saga.run_id} if saga else None,
        "can_disrupt": header.booking_status == BOOKING_ACTIVE,
    }


@router.get("/flights")
def list_flights(
    q: str = Query("", max_length=40, description="flight number, airport code or ORG-DST"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    q = q.strip()
    rows = db.execute(text(SQL_LIST_FLIGHTS), {"q": q, "like": _like(q), "limit": limit}).all()
    return [
        {
            "id": r.id,
            "flight_no": r.flight_no,
            "airline": r.airline,
            "origin": r.origin,
            "dest": r.dest,
            "sched_dep_at": _iso(r.sched_dep_at),
            "economy_available": int(r.economy_available),
            "business_available": int(r.business_available),
            "direct_alternatives": r.direct_alternatives,
        }
        for r in rows
    ]


@router.post("/passengers", status_code=201)
def create_passenger(req: CreatePassengerRequest, db: Session = Depends(get_db)) -> dict:
    flight = db.get(Flight, str(req.flight_id))
    if flight is None:
        raise HTTPException(status_code=404, detail="flight not found")
    if flight.status == FLIGHT_CANCELLED:
        raise HTTPException(status_code=409, detail=f"flight {flight.flight_no} is cancelled")

    # Same atomic decrement the workers use for holds. The booking's segment
    # counts toward I1's "original" seats, so available must drop with it.
    taken = db.execute(
        update(SeatInventory)
        .where(
            SeatInventory.flight_id == flight.id,
            SeatInventory.cabin == req.cabin,
            SeatInventory.available > 0,
        )
        .values(available=SeatInventory.available - 1)
    )
    if taken.rowcount == 0:
        raise HTTPException(status_code=409, detail=f"no {req.cabin.lower()} seats left on {flight.flight_no}")

    passenger = Passenger(
        airline_id=flight.airline_id,
        name=req.name,
        tier=req.tier,
        is_unaccompanied_minor=req.is_unaccompanied_minor,
        bags=req.bags,
    )
    db.add(passenger)
    db.flush()

    booking = Booking(passenger_id=passenger.id, pnr=_unused_pnr(db), status=BOOKING_ACTIVE)
    db.add(booking)
    db.flush()
    db.add(BookingSegment(booking_id=booking.id, seq=0, flight_id=flight.id, cabin=req.cabin))
    db.commit()

    return {"booking_id": booking.id, "pnr": booking.pnr, "name": passenger.name, "flight_no": flight.flight_no}


@router.post("/passengers/{booking_id}/disrupt")
def disrupt_booking(booking_id: UUID, req: DisruptBookingRequest, db: Session = Depends(get_db)) -> dict:
    """Cancel the booking's first flight and queue every booking it breaks
    for planning, exactly as a scenario's cancellation would.

    The sagas join the most recent run rather than a new one: invariant I2
    flags any non-ACTIVE booking without a saga in the run being checked, so
    a separate run would make Safety Checks fail on the run already on screen.
    """
    booking_id = str(booking_id)
    # Locks the row so a double submit cannot queue the same booking twice,
    # which would trip the planner's unique (run_id, booking_id) saga.
    booking = db.execute(select(Booking).where(Booking.id == booking_id).with_for_update()).scalar_one_or_none()
    if booking is None:
        raise HTTPException(status_code=404, detail="passenger not found")
    if booking.status != BOOKING_ACTIVE:
        raise HTTPException(status_code=409, detail=f"booking is already {booking.status.lower()}")

    flight = db.execute(
        select(Flight)
        .join(BookingSegment, BookingSegment.flight_id == Flight.id)
        .where(BookingSegment.booking_id == booking_id)
        .order_by(BookingSegment.seq)
        .limit(1)
    ).scalar_one_or_none()
    if flight is None:
        raise HTTPException(status_code=409, detail="booking has no itinerary to disrupt")
    if flight.status == FLIGHT_CANCELLED:
        raise HTTPException(status_code=409, detail=f"flight {flight.flight_no} is already cancelled")

    run = db.execute(select(Run).order_by(Run.created_at.desc()).limit(1)).scalar_one_or_none()
    if run is None:
        scenario = db.execute(select(Scenario).order_by(Scenario.created_at.desc()).limit(1)).scalar_one_or_none()
        if scenario is None:
            raise HTTPException(status_code=409, detail="no scenario has been generated yet")
        run = Run(scenario_id=scenario.id, strategy="greedy")
        db.add(run)
        db.flush()
    # The relay closes a run once its sagas settle and re-snapshots its
    # metrics, so reopening a finished run folds the new sagas into them.
    run.status = RUN_RUNNING
    run.finished_at = None
    if run.started_at is None:
        run.started_at = datetime.now(UTC)

    stats = apply_events(
        db,
        run.id,
        [
            {
                "type": EVENT_CANCELLATION,
                "cause": req.cause,
                "target_flight_id": flight.id,
                "target_airport_id": flight.origin,
                "delay_minutes": None,
                "occurred_at": datetime.now(UTC).isoformat(),
            }
        ],
    )
    db.commit()

    return {
        "run_id": run.id,
        "flight_no": flight.flight_no,
        "cause": req.cause,
        "disrupted_bookings": stats["disrupted_bookings"],
        "plan_batches_queued": stats["plan_batches_queued"],
    }
