"""Integration tests hit the real Postgres + Redis started by
`docker compose up` (section 14: "Integration (compose or
testcontainers)"). Point POSTGRES_HOST/PORT/REDIS_HOST/PORT at the running
stack before `pytest tests/integration` -- `make test-integration` does
this for you.
"""

import uuid
from datetime import UTC

import pytest
from sqlalchemy import text

from reflight.core.db import SessionLocal
from reflight.core.models import (
    Airline,
    Airport,
    Booking,
    BookingSegment,
    Flight,
    Passenger,
    Run,
    Saga,
    Scenario,
    SeatInventory,
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def flight_with_inventory(db):
    """One flight with a single ECONOMY cabin of the given capacity."""

    def _make(capacity: int = 50):
        airline = Airline(code=f"T{uuid.uuid4().hex[:4].upper()}", name="Test Airways")
        origin = Airport(iata="AAA", name="A", lat=0, lon=0, is_hub=False)
        dest = Airport(iata="BBB", name="B", lat=0, lon=0, is_hub=False)
        db.add_all([airline, origin, dest])
        db.flush()

        from datetime import datetime

        flight = Flight(
            airline_id=airline.id,
            flight_no="T100",
            tail_number="T-001",
            origin=origin.id,
            dest=dest.id,
            dep_at=datetime.now(UTC),
            arr_at=datetime.now(UTC),
            sched_dep_at=datetime.now(UTC),
            sched_arr_at=datetime.now(UTC),
            status="SCHEDULED",
        )
        db.add(flight)
        db.flush()

        inv = SeatInventory(flight_id=flight.id, cabin="ECONOMY", capacity=capacity, available=capacity, sold_other=0)
        db.add(inv)
        db.commit()
        return flight, airline, origin, dest

    yield _make

    db.rollback()
    # Deletion order matters: children (FK holders) before parents.
    for table in [
        "dead_letters",
        "processed_messages",
        "saga_events",
        "seat_holds",
        "disruption_events",
        "sagas",
        "outbox",
        "booking_segments",
        "bookings",
        "runs",
        "seat_inventory",
        "flights",
        "passengers",
        "scenarios",
        "airports",
        "airlines",
        "partners.tickets",
        "partners.idempotency",
    ]:
        db.execute(text(f"DELETE FROM {table}"))
    db.commit()


@pytest.fixture
def saga_ready_for_hold(db, flight_with_inventory):
    """A saga in state=PLANNED, current_step=HOLD_SEATS, for a booking with
    one segment on a fresh flight with the given seat capacity."""

    def _make(capacity: int = 10, bags: int = 0):
        flight, airline, *_ = flight_with_inventory(capacity=capacity)

        scenario = Scenario(seed=1, params_json={}, minio_key="test")
        db.add(scenario)
        db.flush()
        run = Run(scenario_id=scenario.id, strategy="greedy", status="RUNNING")
        db.add(run)
        db.flush()

        passenger = Passenger(airline_id=airline.id, name="Test Passenger", tier="NONE", bags=bags)
        db.add(passenger)
        db.flush()

        booking = Booking(passenger_id=passenger.id, pnr=f"T{uuid.uuid4().hex[:5].upper()}", status="DISRUPTED")
        db.add(booking)
        db.flush()
        db.add(BookingSegment(booking_id=booking.id, seq=0, flight_id=flight.id, cabin="ECONOMY"))

        saga = Saga(
            run_id=run.id,
            booking_id=booking.id,
            state="PLANNED",
            current_step="HOLD_SEATS",
            priority=0,
            plan_json={"segments": [{"seq": 0, "flight_id": flight.id, "cabin": "ECONOMY"}]},
        )
        db.add(saga)
        db.commit()
        return saga, flight, booking

    return _make
