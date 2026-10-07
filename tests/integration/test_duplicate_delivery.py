"""The same step message delivered 5 times must have exactly one effect
(section 14 / D4). worker/main.py::_handle_message guards this via
`processed_messages` plus the `current_step` match on a row-locked saga."""

import json

from sqlalchemy import select

from reflight.core.models import ProcessedMessage, Saga, SeatInventory
from reflight.worker.main import _handle_message


def test_same_message_delivered_5_times_has_one_effect(saga_ready_for_hold, db):
    saga, flight, booking = saga_ready_for_hold(capacity=10)
    body = json.dumps({"saga_id": saga.id, "step": "HOLD_SEATS"}).encode()

    for _ in range(5):
        _handle_message(body)

    available = db.execute(
        select(SeatInventory.available).where(SeatInventory.flight_id == flight.id, SeatInventory.cabin == "ECONOMY")
    ).scalar_one()
    assert available == 9  # decremented exactly once, not five times

    processed_count = db.execute(
        select(ProcessedMessage).where(ProcessedMessage.saga_id == saga.id, ProcessedMessage.step == "HOLD_SEATS")
    ).scalars().all()
    assert len(processed_count) == 1

    refreshed = db.get(Saga, saga.id)
    db.refresh(refreshed)
    assert refreshed.current_step == "ISSUE_TICKET"
