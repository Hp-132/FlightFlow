"""Custom metrics (section 11 table). Call `reflight.core.telemetry.init_telemetry`
before importing this module so instruments bind to the real MeterProvider
when one is configured; otherwise they bind to OTel's default no-op
provider and every call below is a harmless no-op.
"""

from opentelemetry import metrics

_meter = metrics.get_meter("reflight")

saga_started_total = _meter.create_counter(
    "saga_started_total", description="Sagas created by the planner"
)
saga_finished_total = _meter.create_counter(
    "saga_finished_total", description="Sagas reaching a terminal state, by state"
)
saga_step_duration_seconds = _meter.create_histogram(
    "saga_step_duration_seconds", unit="s", description="Wall time spent in each step handler"
)
saga_step_retries_total = _meter.create_counter(
    "saga_step_retries_total", description="Transient step failures that were retried"
)
seat_conflict_total = _meter.create_counter(
    "seat_conflict_total", description="HOLD_SEATS attempts that found no capacity"
)
dlq_messages_total = _meter.create_counter(
    "dlq_messages_total", description="Steps that exhausted retries and were dead-lettered"
)
disruption_events_total = _meter.create_counter(
    "disruption_events_total", description="Disruption events applied to a run, by cause"
)
tenant_deferrals_total = _meter.create_counter(
    "tenant_deferrals_total",
    description="Steps parked on the delay queue because their airline was at its concurrency cap",
)

_workers_active_count = 0


def mark_worker_active() -> None:
    global _workers_active_count
    _workers_active_count = 1
    _meter.create_observable_gauge(
        "workers_active",
        callbacks=[lambda options: [metrics.Observation(_workers_active_count)]],
        description="Heartbeat: 1 per live worker process",
    )


_last_invariant_violations = 0


def set_last_invariant_violations(count: int) -> None:
    global _last_invariant_violations
    _last_invariant_violations = count


def _invariant_violations_callback(options):
    return [metrics.Observation(_last_invariant_violations)]


_meter.create_observable_gauge(
    "invariant_violations",
    callbacks=[_invariant_violations_callback],
    description="Violation count from the most recent invariant check",
)


def _outbox_lag_callback(options):
    try:
        from sqlalchemy import text

        from reflight.core.db import SessionLocal

        db = SessionLocal()
        try:
            lag = db.execute(
                text("SELECT EXTRACT(EPOCH FROM now() - MIN(created_at)) FROM outbox WHERE published_at IS NULL")
            ).scalar_one_or_none()
        finally:
            db.close()
        return [metrics.Observation(float(lag or 0.0))]
    except Exception:
        return [metrics.Observation(0.0)]


_meter.create_observable_gauge(
    "outbox_lag_seconds",
    callbacks=[_outbox_lag_callback],
    description="Age of the oldest unpublished outbox row",
)
