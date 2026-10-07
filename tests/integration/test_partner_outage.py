"""100% ticketing failure must end the saga COMPENSATED with no leaked
holds (section 14 / D3): after MAX_ATTEMPTS failures on ISSUE_TICKET, the
worker compensates by releasing the seats it held (there's no ticket to
void since one was never issued)."""

import json
from unittest.mock import patch

from sqlalchemy import select

from reflight.core.models import Saga, SeatHold, SeatInventory
from reflight.worker.main import _handle_message
from reflight.worker.partners_client import TransientPartnerError


def test_ticketing_outage_ends_compensated_no_leaks(saga_ready_for_hold, db):
    saga, flight, booking = saga_ready_for_hold(capacity=10)

    # Drive HOLD_SEATS for real so seat_holds exist, then force ISSUE_TICKET
    # to fail every time.
    _handle_message(json.dumps({"saga_id": saga.id, "step": "HOLD_SEATS"}).encode())

    with patch("reflight.worker.steps.issue_ticket", side_effect=TransientPartnerError("simulated outage")):
        for _ in range(4):  # MAX_ATTEMPTS
            _handle_message(json.dumps({"saga_id": saga.id, "step": "ISSUE_TICKET"}).encode())

    refreshed = db.get(Saga, saga.id)
    db.refresh(refreshed)
    assert refreshed.state == "COMPENSATING"
    assert refreshed.current_step == "RELEASE_SEATS"

    _handle_message(json.dumps({"saga_id": saga.id, "step": "RELEASE_SEATS"}).encode())

    refreshed = db.get(Saga, saga.id)
    db.refresh(refreshed)
    assert refreshed.state == "COMPENSATED"

    holds = db.execute(select(SeatHold).where(SeatHold.saga_id == saga.id)).scalars().all()
    assert all(h.status == "RELEASED" for h in holds)

    available = db.execute(
        select(SeatInventory.available).where(SeatInventory.flight_id == flight.id, SeatInventory.cabin == "ECONOMY")
    ).scalar_one()
    assert available == 10  # fully restored
