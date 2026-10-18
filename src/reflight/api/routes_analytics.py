"""Flight scheduling & operations analytics.

One endpoint serves the whole page, aggregated in Postgres. It sits at
/analytics/summary so it cannot shadow the dashboard's own /analytics route
when a single origin serves both (ALL_IN_ONE), and its reads share one
REPEATABLE READ transaction so the panels cannot disagree mid-run.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from reflight.analytics.insights import build_insights, build_overview, missing_capabilities
from reflight.analytics.queries import (
    begin_snapshot,
    fetch_recovery,
    fetch_schedule,
    resolve_run_ids,
)
from reflight.api.deps import get_db, require_api_key
from reflight.core.models import Flight, Scenario

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(require_api_key)])


@router.get("/summary")
def get_analytics(
    run_id: str | None = Query(None, description="restrict recovery analytics to one run"),
    window_days: int | None = Query(
        None, ge=1, le=365, description="restrict to runs created in the last N days"
    ),
    top_n: int = Query(8, ge=1, le=50, description="rows in the route and airport tables"),
    db: Session = Depends(get_db),
) -> dict:
    begin_snapshot(db)
    run_ids = resolve_run_ids(db, run_id, window_days)
    schedule = fetch_schedule(db, top_n=top_n)
    recovery = fetch_recovery(db, run_ids)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "filters": {"run_id": run_id, "window_days": window_days, "top_n": top_n},
        "provenance": _provenance(db, run_ids, schedule),
        "overview": build_overview(schedule, recovery),
        "schedule": schedule,
        "recovery": recovery,
        "insights": build_insights(schedule, recovery),
        "gaps": missing_capabilities(schedule),
    }


def _provenance(db: Session, run_ids: list[str], schedule: dict) -> dict:
    """What the numbers on this page actually are.

    Every figure is aggregated live from Postgres. The underlying network,
    however, is synthetic: flights, passengers and bookings are written by the
    seeded scenario generator, and delays exist only where a scenario injected
    them. The page says so rather than implying an operational feed.
    """
    # Distinct (seed, preset) pairs: re-seeding the same scenario repeatedly is
    # normal here, and listing "42, 42, 42, 42, 42" tells the reader nothing.
    scenarios = db.execute(
        select(Scenario.seed, Scenario.params_json)
        .order_by(Scenario.created_at.desc())
        .limit(25)
    ).all()
    seen: set[tuple] = set()
    unique_scenarios = []
    for seed, params in scenarios:
        key = (seed, (params or {}).get("preset"))
        if key not in seen:
            seen.add(key)
            unique_scenarios.append(key)
    unique_scenarios = unique_scenarios[:5]
    flight_count = db.execute(select(func.count()).select_from(Flight)).scalar_one()

    return {
        "source": "postgres_live_aggregation",
        "network_origin": "generated" if flight_count else "empty",
        "is_synthetic": True,
        "note": (
            "Aggregated live from the FlightFlow database. The flight network is produced by "
            "the seeded scenario generator, not an operational feed, and a departure is only "
            "late where a scenario injected a delay."
        ),
        "scenarios": [{"seed": seed, "preset": preset} for seed, preset in unique_scenarios],
        "runs_covered": len(run_ids),
        "has_flight_data": flight_count > 0,
        "has_recovery_data": bool(run_ids),
        "schedule_window": {
            "first_departure": schedule["flights"]["first_departure"],
            "last_departure": schedule["flights"]["last_departure"],
        },
    }
