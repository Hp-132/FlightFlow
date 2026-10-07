from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from reflight.api.deps import get_db, require_api_key
from reflight.api.schemas import GenerateScenarioRequest, LoadScenarioResponse, ScenarioResponse
from reflight.core.models import Scenario
from reflight.simulator.generator import generate_and_store
from reflight.simulator.loader import load_scenario

router = APIRouter(prefix="/scenarios", tags=["scenarios"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=ScenarioResponse, status_code=201)
def create_scenario(req: GenerateScenarioRequest) -> ScenarioResponse:
    scenario_id = generate_and_store(
        preset=req.preset,
        seed=req.seed,
        hub=req.hub,
        severity=req.severity,
        cascade_chains=req.cascade_chains,
    )
    return ScenarioResponse(id=scenario_id)


@router.post("/{scenario_id}/load", response_model=LoadScenarioResponse)
def load(scenario_id: str, db: Session = Depends(get_db)) -> LoadScenarioResponse:
    scenario_row = db.get(Scenario, scenario_id)
    if scenario_row is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    counts = load_scenario(db, scenario_row)
    db.commit()
    return LoadScenarioResponse(scenario_id=scenario_id, counts=counts)
