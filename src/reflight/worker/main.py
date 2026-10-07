"""Saga step worker (section 6C): one DB transaction per message.

Duplicate delivery is guarded twice, belt-and-braces: `processed_messages`
(section 5) catches a redelivery after a step already succeeded even if
this worker's ack never reached the broker, and `SELECT ... FOR UPDATE` on
the saga row plus the `current_step` match check catches everything else
(a second in-flight copy of the same message blocks on the row lock, then
sees `current_step` has already moved past it once the first copy
commits).
"""

import json
import logging
import time

from sqlalchemy import select

from reflight.core.db import session_scope
from reflight.core.fairness import acquire, new_token, release
from reflight.core.metrics import saga_step_duration_seconds, tenant_deferrals_total
from reflight.core.models import Booking, Passenger, ProcessedMessage, Saga
from reflight.core.outbox import enqueue
from reflight.core.priority import to_rabbitmq_priority
from reflight.core.rabbitmq import QUEUE_DELAY_2S, QUEUE_SAGA_STEPS, declare_topology, get_connection
from reflight.worker.chaos import maybe_crash
from reflight.worker.steps import STEP_HANDLERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s worker: %(message)s")
log = logging.getLogger("reflight.worker")


def _airline_for_saga(db, saga_id: str) -> str | None:
    return db.execute(
        select(Passenger.airline_id)
        .join(Booking, Booking.passenger_id == Passenger.id)
        .join(Saga, Saga.booking_id == Booking.id)
        .where(Saga.id == saga_id)
    ).scalar_one_or_none()


def _handle_message(body: bytes) -> None:
    message = json.loads(body)
    saga_id = message["saga_id"]
    step = message["step"]

    airline_id: str | None = None
    token: str | None = None

    try:
        with session_scope() as db:
            already_done = db.execute(
                select(ProcessedMessage).where(
                    ProcessedMessage.saga_id == saga_id, ProcessedMessage.step == step
                )
            ).scalar_one_or_none()
            if already_done is not None:
                log.info("duplicate delivery ignored: saga=%s step=%s", saga_id, step)
                return

            saga = db.execute(
                select(Saga).where(Saga.id == saga_id).with_for_update()
            ).scalar_one_or_none()
            if saga is None:
                log.warning("saga %s not found, dropping message", saga_id)
                return
            if saga.current_step != step:
                log.info(
                    "stale/out-of-order message ignored: saga=%s expected=%s got=%s",
                    saga_id,
                    saga.current_step,
                    step,
                )
                return

            # F13: park the step if this airline is already at its cap, so a
            # tenant that floods the queue can't monopolise the workers.
            airline_id = _airline_for_saga(db, saga_id)
            if airline_id is not None:
                candidate = new_token()
                if acquire(airline_id, candidate):
                    token = candidate
                else:
                    tenant_deferrals_total.add(1, {"airline_id": airline_id})
                    enqueue(
                        db,
                        QUEUE_DELAY_2S,
                        {"saga_id": saga_id, "step": step},
                        priority=to_rabbitmq_priority(saga.priority),
                    )
                    airline_id = None
                    return

            maybe_crash("before_commit")

            handler = STEP_HANDLERS[step]
            started = time.monotonic()
            handler(db, saga)
            saga_step_duration_seconds.record(time.monotonic() - started, {"step": step})
    finally:
        if airline_id is not None and token is not None:
            release(airline_id, token)

    maybe_crash("after_commit_before_ack")


def _connect_with_retry(max_attempts: int = 20, delay_seconds: float = 3.0):
    import pika

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return get_connection()
        except (pika.exceptions.AMQPConnectionError, OSError) as exc:
            last_error = exc
            log.warning("RabbitMQ not ready (attempt %d/%d): %s", attempt, max_attempts, exc)
            time.sleep(delay_seconds)
    raise RuntimeError("could not connect to RabbitMQ") from last_error


def run_forever() -> None:
    connection = _connect_with_retry()
    channel = connection.channel()
    declare_topology(channel)
    channel.basic_qos(prefetch_count=5)

    def on_message(ch, method, properties, body):
        try:
            _handle_message(body)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:
            log.exception("step handler failed, nacking with requeue: %s", body)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    channel.basic_consume(queue=QUEUE_SAGA_STEPS, on_message_callback=on_message)
    log.info("worker started, consuming %s", QUEUE_SAGA_STEPS)
    channel.start_consuming()
