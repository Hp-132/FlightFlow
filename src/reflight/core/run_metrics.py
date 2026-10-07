"""Per-run and per-tenant metrics (section 8's comparison table and F13's
Tenants view). Read-only aggregates over sagas/saga_events, plus whatever
the planner recorded in runs.metrics_json."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from reflight.core.constants import SAGA_COMPLETED, SAGA_TERMINAL_STATES
from reflight.core.models import Run

SQL_STATE_TOTALS = """
SELECT s.state,
       COUNT(*)                                                   AS sagas,
       SUM(s.priority + 1)                                        AS weight,
       COALESCE(SUM((s.plan_json ->> 'delay_minutes')::float), 0)  AS delay_minutes
FROM sagas s
WHERE s.run_id = :run_id
GROUP BY s.state
"""

SQL_SEAT_CONFLICTS = """
SELECT
  (SELECT COUNT(*)
     FROM saga_events e JOIN sagas s ON s.id = e.saga_id
    WHERE s.run_id = :run_id AND e.type = 'HOLD_SEATS_REPLANNED')
  +
  (SELECT COUNT(*)
     FROM sagas s
    WHERE s.run_id = :run_id
      AND s.state = 'FAILED_NO_CAPACITY'
      AND (s.plan_json -> 'segments') IS NOT NULL) AS seat_conflicts
"""

SQL_RECOVERY_WINDOW = """
SELECT EXTRACT(EPOCH FROM (MAX(s.updated_at) - MIN(r.started_at))) AS seconds
FROM sagas s JOIN runs r ON r.id = s.run_id
WHERE s.run_id = :run_id AND r.started_at IS NOT NULL
"""

SQL_TENANTS = """
SELECT a.code                                                        AS airline,
       COUNT(*)                                                      AS sagas,
       COUNT(*) FILTER (WHERE s.state = 'COMPLETED')                 AS recovered,
       COUNT(*) FILTER (WHERE s.state NOT IN
             ('COMPLETED','COMPENSATED','FAILED_NO_CAPACITY','NEEDS_MANUAL')) AS in_flight,
       COALESCE(AVG((s.plan_json ->> 'delay_minutes')::float)
                FILTER (WHERE s.state = 'COMPLETED'), 0)             AS avg_delay_minutes,
       COALESCE(AVG(EXTRACT(EPOCH FROM (s.updated_at - s.created_at)))
                FILTER (WHERE s.state = 'COMPLETED'), 0)             AS avg_recovery_seconds
FROM sagas s
JOIN bookings b   ON b.id = s.booking_id
JOIN passengers p ON p.id = b.passenger_id
JOIN airlines a   ON a.id = p.airline_id
WHERE s.run_id = :run_id
GROUP BY a.code
ORDER BY a.code
"""


def compute_run_metrics(db: Session, run_id: str, *, live_only: bool = False) -> dict[str, Any]:
    """Metrics for a run.

    Finished runs are served from the snapshot the relay took when they
    settled: a later `/scenarios/{id}/load` deletes their sagas, so
    recomputing would report an empty run. `live_only=True` forces a fresh
    computation (that's what the snapshot itself is built from).
    """
    run = db.get(Run, run_id)
    if run is None:
        raise ValueError(f"run {run_id} not found")

    stored_snapshot = (run.metrics_json or {}).get("final")
    if stored_snapshot and not live_only:
        return {**stored_snapshot, "from_snapshot": True}

    rows = db.execute(text(SQL_STATE_TOTALS), {"run_id": run_id}).all()
    by_state = {r.state: {"sagas": r.sagas, "weight": r.weight or 0, "delay": r.delay_minutes or 0.0} for r in rows}

    total_sagas = sum(v["sagas"] for v in by_state.values())
    total_weight = sum(v["weight"] for v in by_state.values())
    completed = by_state.get(SAGA_COMPLETED, {"sagas": 0, "weight": 0, "delay": 0.0})

    terminal = sum(by_state.get(s, {"sagas": 0})["sagas"] for s in SAGA_TERMINAL_STATES)
    unrecovered = total_sagas - completed["sagas"]

    seat_conflicts = db.execute(text(SQL_SEAT_CONFLICTS), {"run_id": run_id}).scalar_one() or 0
    recovery_seconds = db.execute(text(SQL_RECOVERY_WINDOW), {"run_id": run_id}).scalar_one_or_none()

    stored = dict(run.metrics_json or {})

    return {
        "run_id": run_id,
        "strategy": run.strategy,
        "status": run.status,
        "sagas_by_state": {state: v["sagas"] for state, v in by_state.items()},
        "total_sagas": total_sagas,
        "terminal_sagas": terminal,
        "recovered": completed["sagas"],
        "recovered_pct": round(100 * completed["sagas"] / total_sagas, 2) if total_sagas else 0.0,
        "weighted_recovered_pct": round(100 * completed["weight"] / total_weight, 2) if total_weight else 0.0,
        "unrecovered": unrecovered,
        "total_delay_minutes": round(completed["delay"], 1),
        "avg_delay_minutes": round(completed["delay"] / completed["sagas"], 1) if completed["sagas"] else 0.0,
        "planning_seconds": stored.get("planning_seconds", 0.0),
        "planner_cpu_seconds": stored.get("planner_cpu_seconds", 0.0),
        "seat_conflicts": seat_conflicts,
        "recovery_seconds": round(float(recovery_seconds), 1) if recovery_seconds is not None else None,
        "invariants_passed": (stored.get("invariants") or {}).get("passed"),
    }


def compute_tenant_metrics(db: Session, run_id: str, *, live_only: bool = False) -> list[dict[str, Any]]:
    run = db.get(Run, run_id)
    if run is not None and not live_only:
        stored = (run.metrics_json or {}).get("final_tenants")
        if stored:
            return stored

    rows = db.execute(text(SQL_TENANTS), {"run_id": run_id}).all()
    total_in_flight = sum(r.in_flight for r in rows) or 0

    return [
        {
            "airline": r.airline,
            "sagas": r.sagas,
            "recovered": r.recovered,
            "recovered_pct": round(100 * r.recovered / r.sagas, 2) if r.sagas else 0.0,
            "in_flight": r.in_flight,
            "queue_share_pct": round(100 * r.in_flight / total_in_flight, 2) if total_in_flight else 0.0,
            "avg_delay_minutes": round(float(r.avg_delay_minutes), 1),
            "avg_recovery_seconds": round(float(r.avg_recovery_seconds), 1),
        }
        for r in rows
    ]
