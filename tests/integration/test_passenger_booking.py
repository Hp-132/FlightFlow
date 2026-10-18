"""Adding a passenger and cancelling their flight through the API.

The seat accounting matters most: invariant I1 requires
available = capacity - sold_other - original bookings - held, so every new
booking must take exactly one seat, atomically, and never push the count
below zero.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from reflight.api.main import app
from reflight.core.config import get_settings
from reflight.core.models import (
    Booking,
    BookingSegment,
    DisruptionEvent,
    Flight,
    Outbox,
    Run,
    Scenario,
    SeatInventory,
)

HEADERS = {"X-API-Key": get_settings().api_static_key}


def post_passenger(flight_id: str, **overrides):
    body = {"name": "Priya Sharma", "flight_id": flight_id, "cabin": "ECONOMY"}
    body.update(overrides)
    with TestClient(app) as client:
        return client.post("/passengers", json=body, headers=HEADERS)


def available(db, flight_id: str) -> int:
    db.expire_all()
    return db.execute(
        select(SeatInventory.available).where(SeatInventory.flight_id == flight_id, SeatInventory.cabin == "ECONOMY")
    ).scalar_one()


def test_adding_a_passenger_books_the_flight_and_takes_one_seat(flight_with_inventory, db):
    flight, *_ = flight_with_inventory(capacity=3)
    flight_id = flight.id

    resp = post_passenger(flight_id, tier="GOLD", bags=2)

    assert resp.status_code == 201
    body = resp.json()
    assert len(body["pnr"]) == 6
    assert available(db, flight_id) == 2

    booking = db.execute(select(Booking).where(Booking.id == body["booking_id"])).scalar_one()
    segments = db.execute(select(BookingSegment).where(BookingSegment.booking_id == booking.id)).scalars().all()
    assert booking.status == "ACTIVE"
    assert [(s.flight_id, s.cabin, s.seq) for s in segments] == [(flight_id, "ECONOMY", 0)]


def test_the_last_seat_is_sold_once(flight_with_inventory, db):
    flight, *_ = flight_with_inventory(capacity=1)
    flight_id = flight.id

    first = post_passenger(flight_id)
    second = post_passenger(flight_id)

    assert first.status_code == 201
    assert second.status_code == 409
    assert available(db, flight_id) == 0


def test_concurrent_bookings_never_oversell(flight_with_inventory, db):
    flight, *_ = flight_with_inventory(capacity=5)
    flight_id = flight.id

    with ThreadPoolExecutor(max_workers=12) as pool:
        statuses = list(pool.map(lambda _: post_passenger(flight_id).status_code, range(12)))

    assert statuses.count(201) == 5
    assert statuses.count(409) == 7
    assert available(db, flight_id) == 0


def test_cannot_book_a_cancelled_flight(flight_with_inventory, db):
    flight, *_ = flight_with_inventory(capacity=3)
    flight_id = flight.id
    db.execute(Flight.__table__.update().where(Flight.id == flight_id).values(status="CANCELLED"))
    db.commit()

    resp = post_passenger(flight_id)

    assert resp.status_code == 409
    assert available(db, flight_id) == 3


def test_disrupting_a_passenger_cancels_the_flight_and_queues_planning(flight_with_inventory, db):
    flight, *_ = flight_with_inventory(capacity=5)
    flight_id = flight.id
    scenario = Scenario(seed=1, params_json={}, minio_key="test")
    db.add(scenario)
    db.flush()
    run = Run(scenario_id=scenario.id, strategy="greedy", status="FINISHED")
    db.add(run)
    db.commit()
    run_id = run.id

    booking_id = post_passenger(flight_id).json()["booking_id"]

    with TestClient(app) as client:
        resp = client.post(f"/passengers/{booking_id}/disrupt", json={"cause": "AOG"}, headers=HEADERS)
        repeat = client.post(f"/passengers/{booking_id}/disrupt", json={"cause": "AOG"}, headers=HEADERS)

    assert resp.status_code == 200
    assert resp.json()["run_id"] == run_id
    assert resp.json()["disrupted_bookings"] == 1
    assert repeat.status_code == 409

    db.expire_all()
    assert db.get(Flight, flight_id).status == "CANCELLED"
    assert db.get(Booking, booking_id).status == "DISRUPTED"
    assert db.get(Run, run_id).status == "RUNNING"

    event = db.execute(select(DisruptionEvent).where(DisruptionEvent.run_id == run_id)).scalar_one()
    assert (event.type, event.cause, event.target_flight_id) == ("CANCELLATION", "AOG", flight_id)

    queued = db.execute(select(Outbox).where(Outbox.routing_key == "plan.requested")).scalars().all()
    assert [booking_id in row.payload["booking_ids"] for row in queued] == [True]


def test_disrupting_is_refused_without_any_run_or_scenario(flight_with_inventory, db):
    flight, *_ = flight_with_inventory(capacity=2)
    booking_id = post_passenger(flight.id).json()["booking_id"]

    with TestClient(app) as client:
        resp = client.post(f"/passengers/{booking_id}/disrupt", json={"cause": "WEATHER"}, headers=HEADERS)

    assert resp.status_code == 409
    assert "scenario" in resp.json()["detail"]


@pytest.mark.parametrize("path", ["/passengers/not-a-uuid", "/passengers/not-a-uuid/disrupt"])
def test_malformed_ids_are_rejected_before_reaching_the_database(path):
    with TestClient(app) as client:
        resp = client.get(path, headers=HEADERS) if not path.endswith("disrupt") else client.post(
            path, json={"cause": "WEATHER"}, headers=HEADERS
        )

    assert resp.status_code == 422
