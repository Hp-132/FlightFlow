"""Consumes plan.requested batches, runs the greedy planner (F6), creates
one saga per booking (I2: exactly one saga per disrupted booking) and
queues its first step through the outbox."""

import json
import logging
import time

from sqlalchemy import select

from reflight.core.constants import (
    BOOKING_UNRECOVERED,
    SAGA_FAILED_NO_CAPACITY,
    SAGA_PLANNED,
    STEP_HOLD_SEATS,
    STRATEGY_CPSAT,
)
from reflight.core.db import session_scope
from reflight.core.metrics import saga_started_total
from reflight.core.models import Booking, Run, Saga, SagaEvent, SeatInventory
from reflight.core.outbox import enqueue
from reflight.core.priority import to_rabbitmq_priority
from reflight.core.rabbitmq import QUEUE_PLAN_REQUESTED, QUEUE_SAGA_STEPS, declare_topology, get_connection
from reflight.planner.candidates import AirlineFlightCache
from reflight.planner.cpsat import plan_cpsat
from reflight.planner.greedy import plan_greedy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s planner: %(message)s")
log = logging.getLogger("reflight.planner")


def _load_inventory_snapshot(db) -> dict[tuple[str, str], int]:
    rows = db.execute(select(SeatInventory.flight_id, SeatInventory.cabin, SeatInventory.available)).all()
    return {(flight_id, cabin): available for flight_id, cabin, available in rows}


def _handle_batch(body: bytes) -> None:
    message = json.loads(body)
    run_id = message["run_id"]
    booking_ids = message["booking_ids"]

    with session_scope() as db:
        run = db.get(Run, run_id)
        strategy = run.strategy if run else "greedy"

        cache = AirlineFlightCache(db)
        inventory_snapshot = _load_inventory_snapshot(db)

        wall_start, cpu_start = time.monotonic(), time.process_time()
        if strategy == STRATEGY_CPSAT:
            results = plan_cpsat(db, cache, booking_ids, inventory_snapshot)
        else:
            results = plan_greedy(db, cache, booking_ids, inventory_snapshot)
        wall_seconds = time.monotonic() - wall_start
        cpu_seconds = time.process_time() - cpu_start

        if run is not None:
            metrics = dict(run.metrics_json or {})
            metrics["planning_seconds"] = round(metrics.get("planning_seconds", 0.0) + wall_seconds, 4)
            metrics["planner_cpu_seconds"] = round(metrics.get("planner_cpu_seconds", 0.0) + cpu_seconds, 4)
            metrics["planned_bookings"] = metrics.get("planned_bookings", 0) + len(results)
            run.metrics_json = metrics

        unrecovered_ids = []
        for r in results:
            saga = Saga(
                run_id=run_id,
                booking_id=r.booking_id,
                priority=r.priority,
            )
            saga_started_total.add(1)
            if r.segments is None:
                saga.state = SAGA_FAILED_NO_CAPACITY
                saga.current_step = None
                saga.plan_json = {}
                unrecovered_ids.append(r.booking_id)
                db.add(saga)
                db.flush()
                db.add(SagaEvent(saga_id=saga.id, seq=0, type="FAILED_NO_CAPACITY", payload={"reason": "no candidate itinerary"}))
                continue

            saga.state = SAGA_PLANNED
            saga.current_step = STEP_HOLD_SEATS
            saga.plan_json = {"segments": r.segments, "delay_minutes": r.delay_minutes}
            db.add(saga)
            db.flush()
            db.add(SagaEvent(saga_id=saga.id, seq=0, type="PLANNED", payload=saga.plan_json))
            enqueue(
                db,
                QUEUE_SAGA_STEPS,
                {"saga_id": saga.id, "step": STEP_HOLD_SEATS},
                priority=to_rabbitmq_priority(r.priority),
            )

        if unrecovered_ids:
            db.execute(
                Booking.__table__.update()
                .where(Booking.id.in_(unrecovered_ids))
                .values(status=BOOKING_UNRECOVERED)
            )

    log.info(
        "planned batch with %s: %d bookings (%d unrecovered) in %.2fs",
        strategy,
        len(results),
        len(unrecovered_ids),
        wall_seconds,
    )


def run_forever() -> None:
    connection = _connect_with_retry()
    channel = connection.channel()
    declare_topology(channel)
    channel.basic_qos(prefetch_count=10)

    def on_message(ch, method, properties, body):
        try:
            _handle_batch(body)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:
            log.exception("failed to plan batch, nacking without requeue -> dlq path not wired for plan.requested; requeueing")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    channel.basic_consume(queue=QUEUE_PLAN_REQUESTED, on_message_callback=on_message)
    log.info("planner started, consuming %s", QUEUE_PLAN_REQUESTED)
    channel.start_consuming()


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
