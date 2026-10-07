"""Publishes outbox rows to RabbitMQ.

Safe to run as several replicas: `SELECT ... FOR UPDATE SKIP LOCKED` means
two relay instances never grab the same row. Publisher confirms are used so
a failed publish rolls back the whole batch's `published_at` update and the
row is retried on the next poll (at-least-once; consumers dedupe via
`processed_messages` / `partners.idempotency`).
"""

import json
import logging
import time
from datetime import UTC, datetime

from sqlalchemy import select, text

from reflight.core.db import session_scope
from reflight.core.models import Outbox
from reflight.core.outbox import enqueue
from reflight.core.priority import to_rabbitmq_priority
from reflight.core.rabbitmq import (
    EXCHANGE_PLAN,
    EXCHANGE_SAGA,
    QUEUE_DELAY_2S,
    QUEUE_DLQ,
    QUEUE_RETRY_5S,
    QUEUE_RETRY_30S,
    QUEUE_SAGA_STEPS,
    ROUTING_PLAN_REQUESTED,
    declare_topology,
    get_connection,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s relay: %(message)s")
log = logging.getLogger("reflight.relay")

POLL_INTERVAL_SECONDS = 0.5
BATCH_SIZE = 100
SWEEP_INTERVAL_SECONDS = 30
STUCK_AFTER_SECONDS = 60

# A run is finished once it has sagas and every one of them is terminal.
SQL_FINISH_RUNS = """
UPDATE runs r
SET status = 'FINISHED', finished_at = now()
WHERE r.status = 'RUNNING'
  AND EXISTS (SELECT 1 FROM sagas s WHERE s.run_id = r.id)
  AND NOT EXISTS (
    SELECT 1 FROM sagas s
     WHERE s.run_id = r.id
       AND s.state NOT IN ('COMPLETED','COMPENSATED','FAILED_NO_CAPACITY','NEEDS_MANUAL'))
  AND NOT EXISTS (
    SELECT 1 FROM outbox o WHERE o.published_at IS NULL)
RETURNING r.id
"""

SQL_STUCK_SAGAS = """
SELECT id, current_step, priority
FROM sagas
WHERE current_step IS NOT NULL
  AND state NOT IN ('COMPLETED', 'COMPENSATED', 'FAILED_NO_CAPACITY', 'NEEDS_MANUAL')
  AND updated_at < now() - CAST(:stuck_after AS interval)
ORDER BY updated_at
LIMIT 200
"""


_DEFAULT_EXCHANGE_QUEUES = {QUEUE_RETRY_5S, QUEUE_RETRY_30S, QUEUE_DELAY_2S, QUEUE_DLQ}


def _route(routing_key: str) -> tuple[str, str]:
    if routing_key == ROUTING_PLAN_REQUESTED:
        return EXCHANGE_PLAN, ROUTING_PLAN_REQUESTED
    if routing_key == QUEUE_SAGA_STEPS:
        return EXCHANGE_SAGA, QUEUE_SAGA_STEPS
    if routing_key in _DEFAULT_EXCHANGE_QUEUES:
        # plain queues, addressed directly via RabbitMQ's default exchange
        return "", routing_key
    raise ValueError(f"unknown outbox routing_key: {routing_key!r}")


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
    channel.confirm_delivery()
    log.info("relay started, topology declared")

    next_sweep = time.monotonic() + SWEEP_INTERVAL_SECONDS
    while True:
        published = _publish_batch(channel)

        if time.monotonic() >= next_sweep:
            _sweep_stuck_sagas()
            _finish_settled_runs()
            next_sweep = time.monotonic() + SWEEP_INTERVAL_SECONDS

        if published == 0:
            time.sleep(POLL_INTERVAL_SECONDS)


def _finish_settled_runs() -> int:
    """Close out runs whose sagas have all reached a terminal state.

    Also snapshots the run's final metrics into `metrics_json`, because
    loading the next scenario wipes the sagas these numbers are derived
    from -- without the snapshot, the Compare page would have nothing left
    to compare against.
    """
    from reflight.core.models import Run
    from reflight.core.run_metrics import compute_run_metrics, compute_tenant_metrics
    from reflight.finops.report import build_report

    with session_scope() as db:
        finished = db.execute(text(SQL_FINISH_RUNS)).all()
        for (run_id,) in finished:
            run = db.get(Run, str(run_id))
            if run is None:
                continue
            metrics = dict(run.metrics_json or {})
            try:
                metrics["final"] = compute_run_metrics(db, str(run_id), live_only=True)
                metrics["final_tenants"] = compute_tenant_metrics(db, str(run_id), live_only=True)
            except Exception:
                log.exception("could not snapshot metrics for run %s", run_id)
                continue
            try:
                metrics["final_finops"] = build_report(db, str(run_id), live_only=True)
            except Exception:
                log.warning("could not snapshot finops for run %s", run_id, exc_info=True)
            run.metrics_json = metrics

        if finished:
            log.info("marked %d run(s) FINISHED and snapshotted their metrics", len(finished))
        return len(finished)


def _sweep_stuck_sagas() -> int:
    """Re-enqueue the current step of any non-terminal saga that hasn't
    moved in STUCK_AFTER_SECONDS (section 7). A step message can be lost if
    a worker dies between committing its DB work and publishing the retry,
    so this is the backstop that guarantees eventual completion. Redelivery
    is safe: `processed_messages` and the `current_step` check make a
    duplicate a no-op.
    """
    with session_scope() as db:
        rows = db.execute(
            text(SQL_STUCK_SAGAS), {"stuck_after": f"{STUCK_AFTER_SECONDS} seconds"}
        ).all()
        for saga_id, step, priority in rows:
            enqueue(
                db,
                QUEUE_SAGA_STEPS,
                {"saga_id": str(saga_id), "step": step},
                priority=to_rabbitmq_priority(priority),
            )
        if rows:
            db.execute(
                text("UPDATE sagas SET updated_at = now() WHERE id = ANY(:ids)"),
                {"ids": [r[0] for r in rows]},
            )
            log.warning("sweeper re-enqueued %d stuck saga(s)", len(rows))
        return len(rows)


def _publish_batch(channel) -> int:
    import pika

    with session_scope() as db:
        rows = (
            db.execute(
                select(Outbox)
                .where(Outbox.published_at.is_(None))
                .order_by(Outbox.priority.desc(), Outbox.created_at.asc())
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        if not rows:
            return 0

        for row in rows:
            exchange, routing_key = _route(row.routing_key)
            channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=json.dumps(row.payload).encode("utf-8"),
                properties=pika.BasicProperties(delivery_mode=2, priority=row.priority),
            )
            row.published_at = datetime.now(UTC)

        log.info("published %d outbox row(s)", len(rows))
        return len(rows)
