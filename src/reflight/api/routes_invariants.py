from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from reflight.api.deps import get_db, require_api_key
from reflight.core.metrics import set_last_invariant_violations
from reflight.core.models import Run
from reflight.invariants.checks import run_all_checks

router = APIRouter(prefix="/runs", tags=["invariants"], dependencies=[Depends(require_api_key)])


@router.post("/{run_id}/invariants/check")
def check_invariants(run_id: str, db: Session = Depends(get_db)) -> dict:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    report = run_all_checks(db, run_id)
    metrics = dict(run.metrics_json or {})
    metrics["invariants"] = {**report, "checked_at": datetime.now(UTC).isoformat()}
    run.metrics_json = metrics
    db.commit()
    set_last_invariant_violations(report["total_violations"])
    return metrics["invariants"]


@router.get("/{run_id}/invariants")
def get_invariants(run_id: str, db: Session = Depends(get_db)) -> dict:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    invariants = (run.metrics_json or {}).get("invariants")
    if invariants is None:
        raise HTTPException(status_code=404, detail="invariants not checked yet for this run")
    return invariants
