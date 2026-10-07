"""Crash before commit and crash after commit but before ack (section 14 /
D2, the headline "kill workers mid-run" claim): either way, a subsequent
redelivery of the same message must bring the saga to the correct state
with no double effects.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select

from reflight.core.models import ProcessedMessage, Saga, SeatInventory
from reflight.worker.main import _handle_message

REPO_ROOT = Path(__file__).resolve().parents[2]
CHILD_SCRIPT = Path(__file__).resolve().parent / "_crash_child.py"


def _run_child(saga_id: str, step: str, crash_point: str) -> int:
    env = dict(os.environ)
    env["REFLIGHT_FORCE_CRASH_AT"] = crash_point
    result = subprocess.run(
        [sys.executable, str(CHILD_SCRIPT), saga_id, step],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    return result.returncode


def test_crash_before_commit_then_redelivery_completes(saga_ready_for_hold, db):
    saga, flight, booking = saga_ready_for_hold(capacity=10)

    returncode = _run_child(saga.id, "HOLD_SEATS", "before_commit")
    assert returncode != 0  # the child really did hard-crash

    # Nothing should have been written: crash happened before the handler ran.
    refreshed = db.get(Saga, saga.id)
    db.refresh(refreshed)
    assert refreshed.current_step == "HOLD_SEATS"
    available = db.execute(
        select(SeatInventory.available).where(SeatInventory.flight_id == flight.id, SeatInventory.cabin == "ECONOMY")
    ).scalar_one()
    assert available == 10

    # Redelivery (no forced crash this time) completes it exactly once.
    _handle_message(json.dumps({"saga_id": saga.id, "step": "HOLD_SEATS"}).encode())
    refreshed = db.get(Saga, saga.id)
    db.refresh(refreshed)
    assert refreshed.current_step == "ISSUE_TICKET"
    available = db.execute(
        select(SeatInventory.available).where(SeatInventory.flight_id == flight.id, SeatInventory.cabin == "ECONOMY")
    ).scalar_one()
    assert available == 9


def test_crash_after_commit_before_ack_then_redelivery_is_noop(saga_ready_for_hold, db):
    saga, flight, booking = saga_ready_for_hold(capacity=10)

    returncode = _run_child(saga.id, "HOLD_SEATS", "after_commit_before_ack")
    assert returncode != 0

    # The step DID commit successfully before the simulated crash.
    refreshed = db.get(Saga, saga.id)
    db.refresh(refreshed)
    assert refreshed.current_step == "ISSUE_TICKET"
    available = db.execute(
        select(SeatInventory.available).where(SeatInventory.flight_id == flight.id, SeatInventory.cabin == "ECONOMY")
    ).scalar_one()
    assert available == 9

    processed = db.execute(
        select(ProcessedMessage).where(ProcessedMessage.saga_id == saga.id, ProcessedMessage.step == "HOLD_SEATS")
    ).scalars().all()
    assert len(processed) == 1

    # Redelivery of the un-acked message must be a pure no-op.
    _handle_message(json.dumps({"saga_id": saga.id, "step": "HOLD_SEATS"}).encode())
    available = db.execute(
        select(SeatInventory.available).where(SeatInventory.flight_id == flight.id, SeatInventory.cabin == "ECONOMY")
    ).scalar_one()
    assert available == 9  # unchanged -- not decremented a second time
