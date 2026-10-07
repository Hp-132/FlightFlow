"""200 concurrent hold attempts on 50 seats must yield exactly 50
successes -- the atomic `UPDATE ... WHERE available >= qty` in
worker/steps.py::_try_hold is what's under test here."""

from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from reflight.core.db import SessionLocal
from reflight.core.models import SeatInventory


def _attempt_hold(flight_id: str, cabin: str) -> bool:
    session = SessionLocal()
    try:
        result = session.execute(
            SeatInventory.__table__.update()
            .where(SeatInventory.flight_id == flight_id, SeatInventory.cabin == cabin, SeatInventory.available >= 1)
            .values(available=SeatInventory.__table__.c.available - 1)
        )
        session.commit()
        return result.rowcount == 1
    finally:
        session.close()


def test_200_concurrent_holds_on_50_seats(flight_with_inventory, db):
    flight, *_ = flight_with_inventory(capacity=50)
    flight_id = flight.id  # read once on the main thread; ORM attrs expire after commit

    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(lambda _: _attempt_hold(flight_id, "ECONOMY"), range(200)))

    successes = sum(results)
    assert successes == 50

    remaining = db.execute(
        select(SeatInventory.available).where(SeatInventory.flight_id == flight_id, SeatInventory.cabin == "ECONOMY")
    ).scalar_one()
    assert remaining == 0
