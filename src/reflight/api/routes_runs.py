import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from reflight.api.deps import get_db, require_api_key
from reflight.api.schemas import (
    CreateRunRequest,
    DisruptionEventResponse,
    RunResponse,
    StartRunResponse,
)
from reflight.core.config import get_settings
from reflight.core.constants import RUN_RUNNING
from reflight.core.db import SessionLocal
from reflight.core.models import Booking, DisruptionEvent, Run, Saga, Scenario
from reflight.core.ops_metrics import get_queue_depth, get_workers_active
from reflight.core.run_metrics import compute_run_metrics, compute_tenant_metrics
from reflight.simulator.injector import apply_timeline

router = APIRouter(prefix="/runs", tags=["runs"], dependencies=[Depends(require_api_key)])
# Browser EventSource can't set custom headers, so the SSE stream takes its
# key as a query param instead and lives on its own router without the
# header-based dependency.
stream_router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunResponse, status_code=201)
def create_run(
    req: CreateRunRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> RunResponse:
    existing = db.execute(select(Run).where(Run.idempotency_key == idempotency_key)).scalar_one_or_none()
    if existing is not None:
        return RunResponse(id=existing.id, scenario_id=existing.scenario_id, strategy=existing.strategy, status=existing.status)

    scenario = db.get(Scenario, req.scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="scenario not found")

    run = Run(scenario_id=req.scenario_id, strategy=req.strategy, idempotency_key=idempotency_key)
    db.add(run)
    db.commit()
    db.refresh(run)
    return RunResponse(id=run.id, scenario_id=run.scenario_id, strategy=run.strategy, status=run.status)


@router.post("/{run_id}/start", response_model=StartRunResponse)
def start_run(run_id: str, db: Session = Depends(get_db)) -> StartRunResponse:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    scenario = db.get(Scenario, run.scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="scenario not found")

    stats = apply_timeline(db, run_id, scenario.minio_key)

    run.status = RUN_RUNNING
    run.started_at = func.now()
    db.commit()

    return StartRunResponse(run_id=run_id, **stats)


def _run_counters(db: Session, run_id: str) -> dict:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    disruption_count = db.execute(
        select(func.count()).select_from(DisruptionEvent).where(DisruptionEvent.run_id == run_id)
    ).scalar_one()

    booking_status_counts = dict(
        db.execute(select(Booking.status, func.count()).group_by(Booking.status)).all()
    )
    saga_state_counts = dict(
        db.execute(select(Saga.state, func.count()).where(Saga.run_id == run_id).group_by(Saga.state)).all()
    )

    return {
        "run_id": run_id,
        "status": run.status,
        "strategy": run.strategy,
        "disruption_events": disruption_count,
        "bookings_by_status": booking_status_counts,
        "sagas_by_state": saga_state_counts,
        "queue_depth": get_queue_depth(),
        "workers_active": get_workers_active(),
    }


@router.get("")
def list_runs(limit: int = 25, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Run, Scenario)
        .join(Scenario, Scenario.id == Run.scenario_id)
        .order_by(Run.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": run.id,
            "scenario_id": run.scenario_id,
            "strategy": run.strategy,
            "status": run.status,
            "preset": (scenario.params_json or {}).get("preset"),
            "seed": scenario.seed,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }
        for run, scenario in rows
    ]


# Declared before /{run_id} so "compare" isn't swallowed as a run id.
@router.get("/compare")
def compare_runs(a: str, b: str, db: Session = Depends(get_db)) -> dict:
    """Side-by-side metrics for two runs (section 8) -- typically the same
    scenario planned greedily vs with CP-SAT."""
    try:
        return {"a": compute_run_metrics(db, a), "b": compute_run_metrics(db, b)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    return _run_counters(db, run_id)


@router.get("/{run_id}/metrics")
def get_run_metrics(run_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return compute_run_metrics(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{run_id}/tenants")
def get_tenants(run_id: str, db: Session = Depends(get_db)) -> list[dict]:
    return compute_tenant_metrics(db, run_id)


@router.get("/{run_id}/sagas/summary")
def get_saga_summary(run_id: str, db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(Saga.state, func.count()).where(Saga.run_id == run_id).group_by(Saga.state)
    ).all()
    return {state: count for state, count in rows}


@router.get("/{run_id}/disruptions", response_model=list[DisruptionEventResponse])
def get_disruptions(run_id: str, db: Session = Depends(get_db)) -> list[DisruptionEventResponse]:
    rows = db.execute(
        select(DisruptionEvent).where(DisruptionEvent.run_id == run_id).order_by(DisruptionEvent.occurred_at)
    ).scalars().all()
    return [
        DisruptionEventResponse(
            id=r.id,
            type=r.type,
            cause=r.cause,
            target_flight_id=r.target_flight_id,
            target_airport_id=r.target_airport_id,
            delay_minutes=r.delay_minutes,
            occurred_at=r.occurred_at.isoformat(),
        )
        for r in rows
    ]


@stream_router.get("/{run_id}/stream")
async def stream_run(run_id: str, api_key: str = Query(...)):
    if api_key != get_settings().api_static_key:
        raise HTTPException(status_code=401, detail="invalid API key")

    async def event_generator():
        while True:
            db = SessionLocal()
            try:
                data = _run_counters(db, run_id)
            finally:
                db.close()
            yield {"event": "counters", "data": json.dumps(data)}
            if data["status"] == "FINISHED":
                break
            await asyncio.sleep(1.0)

    return EventSourceResponse(event_generator())
