"""Server-side aggregations behind /analytics.

Two different clocks live in this schema, and the split matters for anything
built on top:

* Flights carry *scenario* time (`sched_dep_at`), which the generator lays
  down inside a single synthetic 24-hour day starting at SCHEDULE_START.
  Hour-of-day analysis is meaningful; day-of-week is not, and calendar date
  ranges over flights are meaningless.
* Runs, sagas and disruption events carry *wall-clock* time (`created_at`,
  `occurred_at`), which is when the recovery actually executed. Date-range
  filtering belongs here.

A flight's delay is `dep_at - sched_dep_at`. The generator writes those equal,
and only the scenario injector pushes `dep_at` out, so "on time" in this
schema means "not disrupted by a loaded scenario" -- it is not observed
airline punctuality. Callers are expected to say so.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

# Minutes of departure delay. Anything above zero is a delay here: the
# injector only moves a departure when a disruption hit it, so there is no
# "within 15 minutes is fine" tolerance to apply.
DELAY_EXPR = "EXTRACT(EPOCH FROM (f.dep_at - f.sched_dep_at)) / 60.0"
DELAY_BUCKETS = ["1-30", "31-60", "61-120", "121-180", "180+"]

SQL_FLIGHT_SUMMARY = f"""
SELECT COUNT(*)                                                      AS total,
       COUNT(*) FILTER (WHERE f.status = 'SCHEDULED')                AS scheduled,
       COUNT(*) FILTER (WHERE f.status = 'DELAYED')                  AS delayed_status,
       COUNT(*) FILTER (WHERE f.status = 'CANCELLED')                AS cancelled,
       COUNT(*) FILTER (WHERE f.dep_at > f.sched_dep_at)             AS delayed,
       COALESCE(AVG({DELAY_EXPR}) FILTER (WHERE f.dep_at > f.sched_dep_at), 0) AS avg_delay_minutes,
       COALESCE(MAX({DELAY_EXPR}), 0)                                AS max_delay_minutes,
       MIN(f.sched_dep_at)                                           AS first_departure,
       MAX(f.sched_dep_at)                                           AS last_departure
FROM flights f
"""

SQL_BY_HOUR = f"""
SELECT CAST(EXTRACT(HOUR FROM f.sched_dep_at) AS INTEGER)            AS hour,
       COUNT(*)                                                      AS flights,
       COUNT(*) FILTER (WHERE f.status = 'CANCELLED')                AS cancelled,
       COUNT(*) FILTER (WHERE f.dep_at > f.sched_dep_at)             AS delayed,
       COALESCE(AVG({DELAY_EXPR}) FILTER (WHERE f.dep_at > f.sched_dep_at), 0) AS avg_delay_minutes
FROM flights f
GROUP BY 1
ORDER BY 1
"""

SQL_DELAY_HISTOGRAM = f"""
SELECT CASE
         WHEN {DELAY_EXPR} <= 30  THEN '1-30'
         WHEN {DELAY_EXPR} <= 60  THEN '31-60'
         WHEN {DELAY_EXPR} <= 120 THEN '61-120'
         WHEN {DELAY_EXPR} <= 180 THEN '121-180'
         ELSE '180+'
       END                                                           AS bucket,
       COUNT(*)                                                      AS flights
FROM flights f
WHERE f.dep_at > f.sched_dep_at
GROUP BY 1
"""

SQL_ROUTES = f"""
SELECT o.iata                                                        AS origin,
       d.iata                                                        AS dest,
       COUNT(*)                                                      AS flights,
       COUNT(*) FILTER (WHERE f.status = 'CANCELLED')                AS cancelled,
       COUNT(*) FILTER (WHERE f.dep_at > f.sched_dep_at)             AS delayed,
       COALESCE(AVG({DELAY_EXPR}) FILTER (WHERE f.dep_at > f.sched_dep_at), 0) AS avg_delay_minutes
FROM flights f
JOIN airports o ON o.id = f.origin
JOIN airports d ON d.id = f.dest
GROUP BY 1, 2
ORDER BY COUNT(*) FILTER (WHERE f.status = 'CANCELLED' OR f.dep_at > f.sched_dep_at) DESC,
         COUNT(*) DESC
LIMIT :limit
"""

SQL_AIRPORTS = f"""
SELECT a.iata                                                        AS iata,
       a.is_hub                                                      AS is_hub,
       COUNT(*)                                                      AS departures,
       COUNT(*) FILTER (WHERE f.status = 'CANCELLED')                AS cancelled,
       COUNT(*) FILTER (WHERE f.dep_at > f.sched_dep_at)             AS delayed,
       COALESCE(AVG({DELAY_EXPR}) FILTER (WHERE f.dep_at > f.sched_dep_at), 0) AS avg_delay_minutes
FROM flights f
JOIN airports a ON a.id = f.origin
GROUP BY 1, 2
ORDER BY COUNT(*) DESC
LIMIT :limit
"""

SQL_BOOKING_STATUS = """
SELECT b.status AS status, COUNT(*) AS bookings
FROM bookings b
GROUP BY 1
"""

# ---- run-scoped (wall-clock) -------------------------------------------

SQL_SAGA_TOTALS = """
SELECT COUNT(*)                                                      AS sagas,
       COUNT(*) FILTER (WHERE s.state = 'COMPLETED')                 AS completed,
       COUNT(*) FILTER (WHERE s.state = 'COMPENSATED')               AS compensated,
       COUNT(*) FILTER (WHERE s.state = 'FAILED_NO_CAPACITY')        AS failed_no_capacity,
       COUNT(*) FILTER (WHERE s.state = 'NEEDS_MANUAL')              AS needs_manual,
       COUNT(*) FILTER (WHERE s.attempt > 0)                         AS retried,
       COALESCE(SUM(s.attempt), 0)                                   AS total_attempts,
       COALESCE(AVG(EXTRACT(EPOCH FROM (s.updated_at - s.created_at)))
                FILTER (WHERE s.state = 'COMPLETED'), 0)             AS avg_recovery_seconds,
       COALESCE(AVG((s.plan_json ->> 'delay_minutes')::float)
                FILTER (WHERE s.state = 'COMPLETED'), 0)             AS avg_rebooked_delay_minutes
FROM sagas s
WHERE s.run_id IN :run_ids
"""

SQL_SAGA_STATES = """
SELECT s.state AS state, COUNT(*) AS sagas
FROM sagas s
WHERE s.run_id IN :run_ids
GROUP BY 1
"""

SQL_DISRUPTION_CAUSES = """
SELECT de.cause                                                      AS cause,
       COUNT(*)                                                      AS events,
       COUNT(*) FILTER (WHERE de.type = 'CANCELLATION')              AS cancellations,
       COUNT(*) FILTER (WHERE de.type = 'DELAY')                     AS delays,
       COALESCE(AVG(de.delay_minutes) FILTER (WHERE de.delay_minutes IS NOT NULL), 0) AS avg_delay_minutes
FROM disruption_events de
WHERE de.run_id IN :run_ids
GROUP BY 1
ORDER BY COUNT(*) DESC
"""

# Recovery outcome per disruption cause. The link is real, not inferred:
# booking_segments keeps the ORIGINAL itinerary (rebooking only moves
# bookings.status and writes the new legs into sagas.plan_json), so a saga can
# be traced back to the disrupted flight that caused it. A booking hit by two
# causes is counted under both, hence COUNT(DISTINCT s.id) per cause.
SQL_RECOVERY_BY_CAUSE = """
SELECT de.cause                                                                 AS cause,
       COUNT(DISTINCT s.id)                                                     AS sagas,
       COUNT(DISTINCT s.id) FILTER (WHERE s.state = 'COMPLETED')                AS completed,
       COUNT(DISTINCT s.id) FILTER (WHERE s.state = 'COMPENSATED')              AS compensated,
       COUNT(DISTINCT s.id) FILTER (WHERE s.state = 'FAILED_NO_CAPACITY')       AS failed_no_capacity,
       COUNT(DISTINCT s.id) FILTER (WHERE s.state = 'NEEDS_MANUAL')             AS needs_manual
FROM disruption_events de
JOIN booking_segments bs ON bs.flight_id = de.target_flight_id
JOIN sagas s             ON s.booking_id = bs.booking_id AND s.run_id = de.run_id
WHERE de.run_id IN :run_ids
GROUP BY 1
ORDER BY COUNT(DISTINCT s.id) DESC
"""

SQL_DEAD_LETTERS = """
SELECT dl.step AS step, COUNT(*) AS dead_letters
FROM dead_letters dl
JOIN sagas s ON s.id = dl.saga_id
WHERE s.run_id IN :run_ids
GROUP BY 1
ORDER BY COUNT(*) DESC
"""

SQL_RUNS_IN_WINDOW = """
SELECT r.id AS id
FROM runs r
WHERE r.created_at >= :since
ORDER BY r.created_at DESC
"""

# "All runs" is its own statement rather than a sentinel date: runs.created_at
# is timestamptz, and comparing it against a naive floor leans on the session
# timezone to mean anything.
SQL_ALL_RUNS = """
SELECT r.id AS id
FROM runs r
ORDER BY r.created_at DESC
"""

SQL_RUN_CONTEXT = """
SELECT r.id            AS id,
       r.strategy      AS strategy,
       r.status        AS status,
       r.created_at    AS created_at,
       sc.seed         AS seed,
       sc.params_json  AS params
FROM runs r
JOIN scenarios sc ON sc.id = r.scenario_id
WHERE r.id IN :run_ids
ORDER BY r.created_at DESC
"""


def begin_snapshot(db: Session) -> None:
    """Pin every following read in this session to one MVCC snapshot.

    The page is assembled from a dozen separate queries. Under the default
    READ COMMITTED each one sees its own snapshot, so a run finishing
    mid-request makes the panels disagree -- observed live as saga totals of
    275 against a state breakdown summing to 259.

    Postgres requires this before any other statement in the transaction, so
    callers run it first.
    """
    db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))


def _rows(db: Session, sql: str, params: dict[str, Any] | None = None) -> list[Any]:
    return db.execute(text(sql), params or {}).all()


def _run_scoped(db: Session, sql: str, run_ids: list[str]) -> list[Any]:
    """Runs an `IN :run_ids` query. An empty list short-circuits rather than
    relying on how the driver renders an empty IN ()."""
    if not run_ids:
        return []
    stmt = text(sql).bindparams(bindparam("run_ids", expanding=True))
    return db.execute(stmt, {"run_ids": run_ids}).all()


def resolve_run_ids(db: Session, run_id: str | None, window_days: int | None) -> list[str]:
    """Which runs the recovery-side analytics cover: one explicitly, or every
    run created inside the window."""
    if run_id:
        return [run_id]
    if window_days is None:
        return [r.id for r in _rows(db, SQL_ALL_RUNS)]
    since = datetime.now(UTC) - timedelta(days=window_days)
    return [r.id for r in _rows(db, SQL_RUNS_IN_WINDOW, {"since": since})]


def fetch_schedule(db: Session, *, top_n: int = 8) -> dict[str, Any]:
    """Flight-side aggregates. Scenario clock, so no date range."""
    summary = _rows(db, SQL_FLIGHT_SUMMARY)[0]
    hours = _rows(db, SQL_BY_HOUR)
    histogram = {r.bucket: r.flights for r in _rows(db, SQL_DELAY_HISTOGRAM)}
    routes = _rows(db, SQL_ROUTES, {"limit": top_n})
    airports = _rows(db, SQL_AIRPORTS, {"limit": top_n})
    bookings = {r.status: r.bookings for r in _rows(db, SQL_BOOKING_STATUS)}

    return {
        "flights": {
            "total": summary.total,
            "scheduled": summary.scheduled,
            "delayed": summary.delayed,
            "cancelled": summary.cancelled,
            "on_time": summary.total - summary.delayed - summary.cancelled,
            "avg_delay_minutes": round(float(summary.avg_delay_minutes), 1),
            "max_delay_minutes": round(float(summary.max_delay_minutes), 1),
            "first_departure": summary.first_departure.isoformat() if summary.first_departure else None,
            "last_departure": summary.last_departure.isoformat() if summary.last_departure else None,
        },
        "by_hour": [
            {
                "hour": r.hour,
                "flights": r.flights,
                "cancelled": r.cancelled,
                "delayed": r.delayed,
                "disrupted": r.cancelled + r.delayed,
                "avg_delay_minutes": round(float(r.avg_delay_minutes), 1),
            }
            for r in hours
        ],
        "delay_histogram": [
            {"bucket": bucket, "flights": histogram.get(bucket, 0)} for bucket in DELAY_BUCKETS
        ],
        "routes": [
            {
                "route": f"{r.origin}-{r.dest}",
                "origin": r.origin,
                "dest": r.dest,
                "flights": r.flights,
                "cancelled": r.cancelled,
                "delayed": r.delayed,
                "avg_delay_minutes": round(float(r.avg_delay_minutes), 1),
            }
            for r in routes
        ],
        "airports": [
            {
                "iata": r.iata,
                "is_hub": r.is_hub,
                "departures": r.departures,
                "cancelled": r.cancelled,
                "delayed": r.delayed,
                "avg_delay_minutes": round(float(r.avg_delay_minutes), 1),
            }
            for r in airports
        ],
        "bookings_by_status": bookings,
    }


def fetch_recovery(db: Session, run_ids: list[str]) -> dict[str, Any]:
    """Run-side aggregates (sagas, disruptions, recovery outcomes)."""
    totals_rows = _run_scoped(db, SQL_SAGA_TOTALS, run_ids)
    totals = totals_rows[0] if totals_rows else None

    states = {r.state: r.sagas for r in _run_scoped(db, SQL_SAGA_STATES, run_ids)}
    causes = _run_scoped(db, SQL_DISRUPTION_CAUSES, run_ids)
    by_cause = _run_scoped(db, SQL_RECOVERY_BY_CAUSE, run_ids)
    dead_letters = _run_scoped(db, SQL_DEAD_LETTERS, run_ids)
    context = _run_scoped(db, SQL_RUN_CONTEXT, run_ids)

    return {
        "run_ids": run_ids,
        "runs": [
            {
                "id": r.id,
                "strategy": r.strategy,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "seed": r.seed,
                "preset": (r.params or {}).get("preset"),
            }
            for r in context
        ],
        "sagas": {
            "total": totals.sagas if totals else 0,
            "completed": totals.completed if totals else 0,
            "compensated": totals.compensated if totals else 0,
            "failed_no_capacity": totals.failed_no_capacity if totals else 0,
            "needs_manual": totals.needs_manual if totals else 0,
            "retried": totals.retried if totals else 0,
            "total_attempts": int(totals.total_attempts) if totals else 0,
            "avg_recovery_seconds": round(float(totals.avg_recovery_seconds), 1) if totals else 0.0,
            "avg_rebooked_delay_minutes": (
                round(float(totals.avg_rebooked_delay_minutes), 1) if totals else 0.0
            ),
        },
        "sagas_by_state": states,
        "disruption_causes": [
            {
                "cause": r.cause,
                "events": r.events,
                "cancellations": r.cancellations,
                "delays": r.delays,
                "avg_delay_minutes": round(float(r.avg_delay_minutes), 1),
            }
            for r in causes
        ],
        "recovery_by_cause": [
            {
                "cause": r.cause,
                "sagas": r.sagas,
                "completed": r.completed,
                "compensated": r.compensated,
                "failed_no_capacity": r.failed_no_capacity,
                "needs_manual": r.needs_manual,
                "recovered_pct": round(100 * r.completed / r.sagas, 1) if r.sagas else 0.0,
            }
            for r in by_cause
        ],
        "dead_letters": [{"step": r.step, "dead_letters": r.dead_letters} for r in dead_letters],
    }
