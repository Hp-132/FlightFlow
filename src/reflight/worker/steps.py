"""Saga step handlers (section 6B). Each function runs inside the caller's
open transaction (worker/main.py commits/rolls back) and either advances
the saga on success or arranges a retry/compensation on failure -- always
by inserting the next message into the transactional outbox, never by
publishing to RabbitMQ directly.
"""


from sqlalchemy import select
from sqlalchemy.orm import Session

from reflight.core.constants import (
    BOOKING_REBOOKED,
    BOOKING_UNRECOVERED,
    HOLD_CONFIRMED,
    HOLD_HELD,
    HOLD_RELEASED,
    SAGA_COMPENSATED,
    SAGA_COMPENSATING,
    SAGA_COMPLETED,
    SAGA_FAILED_NO_CAPACITY,
    SAGA_NEEDS_MANUAL,
    SAGA_NOTIFYING,
    SAGA_TICKETING,
    STEP_HOLD_SEATS,
    STEP_ISSUE_TICKET,
    STEP_NOTIFY,
    STEP_RELEASE_SEATS,
    STEP_RETAG_BAGS,
    STEP_VOID_TICKET,
)
from reflight.core.metrics import (
    dlq_messages_total,
    saga_finished_total,
    saga_step_retries_total,
    seat_conflict_total,
)
from reflight.core.models import Booking, Passenger, Saga, SagaEvent, SeatHold, SeatInventory
from reflight.core.outbox import enqueue
from reflight.core.priority import to_rabbitmq_priority
from reflight.core.rabbitmq import QUEUE_RETRY_5S, QUEUE_RETRY_30S, QUEUE_SAGA_STEPS
from reflight.planner.candidates import AirlineFlightCache, generate_candidates
from reflight.planner.greedy import load_plan_inputs
from reflight.worker.partners_client import TransientPartnerError, issue_ticket, notify, tag_bags, void_ticket

MAX_ATTEMPTS = 4


class NoCapacityError(Exception):
    pass


def _next_seq(db: Session, saga_id: str) -> int:
    last = db.execute(
        select(SagaEvent.seq).where(SagaEvent.saga_id == saga_id).order_by(SagaEvent.seq.desc()).limit(1)
    ).scalar_one_or_none()
    return (last or 0) + 1


def _record_event(db: Session, saga: Saga, event_type: str, payload: dict) -> None:
    db.add(SagaEvent(saga_id=saga.id, seq=_next_seq(db, saga.id), type=event_type, payload=payload))
    db.flush()  # so a second _record_event call in the same transaction sees this seq


def _mark_processed(db: Session, saga_id: str, step: str) -> None:
    from reflight.core.models import ProcessedMessage

    db.add(ProcessedMessage(saga_id=saga_id, step=step))


def _enqueue_step(db: Session, saga: Saga, step: str) -> None:
    enqueue(db, QUEUE_SAGA_STEPS, {"saga_id": saga.id, "step": step}, priority=to_rabbitmq_priority(saga.priority))


def _enqueue_retry(db: Session, saga: Saga, step: str, attempt: int) -> None:
    retry_queue = QUEUE_RETRY_5S if attempt <= 2 else QUEUE_RETRY_30S
    enqueue(db, retry_queue, {"saga_id": saga.id, "step": step}, priority=to_rabbitmq_priority(saga.priority))


def _start_compensation(db: Session, saga: Saga, chain: list[str]) -> None:
    saga.state = SAGA_COMPENSATING
    plan = dict(saga.plan_json or {})
    plan["pending_compensations"] = chain[1:]
    saga.plan_json = plan
    saga.current_step = chain[0]
    saga.attempt = 0
    _record_event(db, saga, "COMPENSATING", {"chain": chain})
    _enqueue_step(db, saga, chain[0])


def _advance_compensation(db: Session, saga: Saga) -> None:
    pending = list((saga.plan_json or {}).get("pending_compensations", []))
    if not pending:
        saga.state = SAGA_COMPENSATED
        saga.current_step = None
        db.execute(
            Booking.__table__.update().where(Booking.id == saga.booking_id).values(status=BOOKING_UNRECOVERED)
        )
        _record_event(db, saga, "COMPENSATED", {})
        saga_finished_total.add(1, {"state": SAGA_COMPENSATED})
        return
    next_step = pending.pop(0)
    plan = dict(saga.plan_json or {})
    plan["pending_compensations"] = pending
    saga.plan_json = plan
    saga.current_step = next_step
    saga.attempt = 0
    _enqueue_step(db, saga, next_step)


# ---------------------------------------------------------------------------
# HOLD_SEATS / RELEASE_SEATS
# ---------------------------------------------------------------------------


def _try_hold(db: Session, saga: Saga, segments: list[dict]) -> bool:
    held: list[dict] = []
    for seg in segments:
        result = db.execute(
            SeatInventory.__table__.update()
            .where(
                SeatInventory.flight_id == seg["flight_id"],
                SeatInventory.cabin == seg["cabin"],
                SeatInventory.available >= 1,
            )
            .values(available=SeatInventory.__table__.c.available - 1)
        )
        if result.rowcount == 0:
            seat_conflict_total.add(1)
            return False
        held.append(seg)

    for seg in held:
        db.add(SeatHold(saga_id=saga.id, flight_id=seg["flight_id"], cabin=seg["cabin"], qty=1, status=HOLD_HELD))
    return True


def handle_hold_seats(db: Session, saga: Saga) -> None:
    segments = saga.plan_json.get("segments", [])
    if _try_hold(db, saga, segments):
        saga.state = "HOLDING"
        saga.current_step = STEP_ISSUE_TICKET
        saga.attempt = 0
        _record_event(db, saga, "HOLD_SEATS_OK", {"segments": segments})
        _mark_processed(db, saga.id, STEP_HOLD_SEATS)
        _enqueue_step(db, saga, STEP_ISSUE_TICKET)
        return

    # No capacity on the planned itinerary: replan once against live inventory.
    db.rollback()
    inputs = load_plan_inputs(db, [saga.booking_id])
    if not inputs:
        _fail_no_capacity(db, saga)
        return
    b = inputs[0]
    cache = AirlineFlightCache(db)
    snapshot = {
        (fid, cabin): avail
        for fid, cabin, avail in db.execute(select(SeatInventory.flight_id, SeatInventory.cabin, SeatInventory.available)).all()
    }
    candidates = generate_candidates(
        cache, b.airline_id, b.origin, b.dest, b.preferred_cabin, b.not_before, b.original_arrival, snapshot
    )
    if not candidates or not _try_hold(db, saga, candidates[0]["segments"]):
        _fail_no_capacity(db, saga)
        return

    saga.plan_json = {"segments": candidates[0]["segments"], "delay_minutes": candidates[0]["delay_minutes"]}
    saga.state = "HOLDING"
    saga.current_step = STEP_ISSUE_TICKET
    saga.attempt = 0
    _record_event(db, saga, "HOLD_SEATS_REPLANNED", saga.plan_json)
    _mark_processed(db, saga.id, STEP_HOLD_SEATS)
    _enqueue_step(db, saga, STEP_ISSUE_TICKET)


def _fail_no_capacity(db: Session, saga: Saga) -> None:
    saga.state = SAGA_FAILED_NO_CAPACITY
    saga.current_step = None
    db.execute(Booking.__table__.update().where(Booking.id == saga.booking_id).values(status=BOOKING_UNRECOVERED))
    _record_event(db, saga, "FAILED_NO_CAPACITY", {})
    saga_finished_total.add(1, {"state": SAGA_FAILED_NO_CAPACITY})


def handle_release_seats(db: Session, saga: Saga) -> None:
    holds = db.execute(
        select(SeatHold).where(SeatHold.saga_id == saga.id, SeatHold.status.in_([HOLD_HELD, HOLD_CONFIRMED]))
    ).scalars().all()
    for hold in holds:
        db.execute(
            SeatInventory.__table__.update()
            .where(SeatInventory.flight_id == hold.flight_id, SeatInventory.cabin == hold.cabin)
            .values(available=SeatInventory.__table__.c.available + hold.qty)
        )
        hold.status = HOLD_RELEASED
    _record_event(db, saga, "RELEASE_SEATS_OK", {"released": len(holds)})
    _mark_processed(db, saga.id, STEP_RELEASE_SEATS)
    _advance_compensation(db, saga)


# ---------------------------------------------------------------------------
# ISSUE_TICKET / VOID_TICKET
# ---------------------------------------------------------------------------


def _booking_pnr(db: Session, booking_id: str) -> str:
    return db.execute(select(Booking.pnr).where(Booking.id == booking_id)).scalar_one()


def handle_issue_ticket(db: Session, saga: Saga) -> str:
    pnr = _booking_pnr(db, saga.booking_id)
    try:
        issue_ticket(saga.id, pnr)
    except TransientPartnerError as exc:
        return _retry_or_compensate(db, saga, STEP_ISSUE_TICKET, str(exc))

    db.execute(
        SeatHold.__table__.update().where(SeatHold.saga_id == saga.id).values(status=HOLD_CONFIRMED)
    )
    db.execute(Booking.__table__.update().where(Booking.id == saga.booking_id).values(status=BOOKING_REBOOKED))
    saga.state = SAGA_TICKETING
    saga.current_step = STEP_RETAG_BAGS
    saga.attempt = 0
    _record_event(db, saga, "ISSUE_TICKET_OK", {"pnr": pnr})
    _mark_processed(db, saga.id, STEP_ISSUE_TICKET)
    _enqueue_step(db, saga, STEP_RETAG_BAGS)
    return "SUCCESS"


def handle_void_ticket(db: Session, saga: Saga) -> str:
    try:
        void_ticket(saga.id)
    except TransientPartnerError as exc:
        return _retry_terminal_on_exhaustion(db, saga, STEP_VOID_TICKET, str(exc))

    _record_event(db, saga, "VOID_TICKET_OK", {})
    _mark_processed(db, saga.id, STEP_VOID_TICKET)
    _advance_compensation(db, saga)
    return "SUCCESS"


# ---------------------------------------------------------------------------
# RETAG_BAGS
# ---------------------------------------------------------------------------


def handle_retag_bags(db: Session, saga: Saga) -> str:
    passenger = db.execute(
        select(Passenger).join(Booking, Booking.passenger_id == Passenger.id).where(Booking.id == saga.booking_id)
    ).scalar_one()

    if passenger.bags > 0:
        pnr = _booking_pnr(db, saga.booking_id)
        try:
            tag_bags(saga.id, pnr)
        except TransientPartnerError as exc:
            return _retry_or_compensate(db, saga, STEP_RETAG_BAGS, str(exc))

    saga.state = SAGA_NOTIFYING
    saga.current_step = STEP_NOTIFY
    saga.attempt = 0
    _record_event(db, saga, "RETAG_BAGS_OK", {"bags": passenger.bags})
    _mark_processed(db, saga.id, STEP_RETAG_BAGS)
    _enqueue_step(db, saga, STEP_NOTIFY)
    return "SUCCESS"


# ---------------------------------------------------------------------------
# NOTIFY (forward-only tail, not compensable)
# ---------------------------------------------------------------------------


def handle_notify(db: Session, saga: Saga) -> str:
    try:
        notify(saga.id, "Your itinerary has changed. Please check your new flight details.")
    except TransientPartnerError as exc:
        saga.attempt += 1
        saga_step_retries_total.add(1, {"step": STEP_NOTIFY})
        _record_event(db, saga, "NOTIFY_RETRY", {"attempt": saga.attempt, "error": str(exc)})
        if saga.attempt >= MAX_ATTEMPTS:
            saga.state = SAGA_NEEDS_MANUAL
            saga.current_step = None
            from reflight.core.models import DeadLetter

            db.add(DeadLetter(saga_id=saga.id, step=STEP_NOTIFY, reason=str(exc), payload=saga.plan_json))
            dlq_messages_total.add(1)
            _record_event(db, saga, "NEEDS_MANUAL", {"step": STEP_NOTIFY, "reason": str(exc)})
            saga_finished_total.add(1, {"state": SAGA_NEEDS_MANUAL})
        else:
            _enqueue_retry(db, saga, STEP_NOTIFY, saga.attempt)
        return "RETRY_OR_TERMINAL"

    saga.state = SAGA_COMPLETED
    saga.current_step = None
    _record_event(db, saga, "COMPLETED", {})
    _mark_processed(db, saga.id, STEP_NOTIFY)
    saga_finished_total.add(1, {"state": SAGA_COMPLETED})
    return "SUCCESS"


# ---------------------------------------------------------------------------
# shared retry / compensation helpers for compensable forward steps
# ---------------------------------------------------------------------------


def _retry_or_compensate(db: Session, saga: Saga, step: str, error: str) -> str:
    saga.attempt += 1
    saga_step_retries_total.add(1, {"step": step})
    _record_event(db, saga, f"{step}_RETRY", {"attempt": saga.attempt, "error": error})
    if saga.attempt >= MAX_ATTEMPTS:
        full_chain = (
            [STEP_VOID_TICKET, STEP_RELEASE_SEATS] if step == STEP_RETAG_BAGS else [STEP_RELEASE_SEATS]
        )
        _start_compensation(db, saga, full_chain)
        return "COMPENSATING"
    _enqueue_retry(db, saga, step, saga.attempt)
    return "RETRYING"


def _retry_terminal_on_exhaustion(db: Session, saga: Saga, step: str, error: str) -> str:
    saga.attempt += 1
    saga_step_retries_total.add(1, {"step": step})
    _record_event(db, saga, f"{step}_RETRY", {"attempt": saga.attempt, "error": error})
    if saga.attempt >= MAX_ATTEMPTS:
        saga.state = SAGA_NEEDS_MANUAL
        saga.current_step = None
        from reflight.core.models import DeadLetter

        db.add(DeadLetter(saga_id=saga.id, step=step, reason=error, payload=saga.plan_json))
        dlq_messages_total.add(1)
        _record_event(db, saga, "NEEDS_MANUAL", {"step": step, "reason": error})
        saga_finished_total.add(1, {"state": SAGA_NEEDS_MANUAL})
        return "NEEDS_MANUAL"
    _enqueue_retry(db, saga, step, saga.attempt)
    return "RETRYING"


STEP_HANDLERS = {
    STEP_HOLD_SEATS: handle_hold_seats,
    STEP_ISSUE_TICKET: handle_issue_ticket,
    STEP_RETAG_BAGS: handle_retag_bags,
    STEP_NOTIFY: handle_notify,
    STEP_RELEASE_SEATS: handle_release_seats,
    STEP_VOID_TICKET: handle_void_ticket,
}
