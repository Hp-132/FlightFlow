from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from reflight.api.deps import get_db, require_api_key
from reflight.api.schemas import ChaosRequest, FairnessRequest
from reflight.core.fairness import get_caps, inflight_counts, set_caps
from reflight.core.models import Airline
from reflight.core.redis_client import get_redis

router = APIRouter(prefix="/chaos", tags=["chaos"], dependencies=[Depends(require_api_key)])
fairness_router = APIRouter(prefix="/fairness", tags=["fairness"], dependencies=[Depends(require_api_key)])

CRASH_PROBABILITY_KEY = "chaos:crash_probability"
PARTNER_FAILURE_RATE_KEY = "chaos:partner_failure_rate"


@router.post("")
def set_chaos(req: ChaosRequest) -> dict:
    r = get_redis()
    r.set(CRASH_PROBABILITY_KEY, req.crash_probability)
    r.set(PARTNER_FAILURE_RATE_KEY, req.partner_failure_rate)
    return {"crash_probability": req.crash_probability, "partner_failure_rate": req.partner_failure_rate}


@router.get("")
def get_chaos() -> dict:
    r = get_redis()
    return {
        "crash_probability": float(r.get(CRASH_PROBABILITY_KEY) or 0.0),
        "partner_failure_rate": float(r.get(PARTNER_FAILURE_RATE_KEY) or 0.0),
    }


@fairness_router.post("")
def set_fairness(req: FairnessRequest, db: Session = Depends(get_db)) -> dict:
    """Caps are keyed by airline id internally but set by IATA-style code,
    which is what the operator (and the Tenants page) actually sees."""
    by_code = dict(db.execute(select(Airline.code, Airline.id)).all())
    caps = {by_code[code]: cap for code, cap in (req.caps or {}).items() if code in by_code}
    set_caps(default_cap=req.default_cap, caps=caps)
    return get_fairness(db)


@fairness_router.get("")
def get_fairness(db: Session = Depends(get_db)) -> dict:
    by_id = dict(db.execute(select(Airline.id, Airline.code)).all())
    caps = {by_id.get(key, key): value for key, value in get_caps().items()}
    inflight = {by_id.get(key, key): value for key, value in inflight_counts().items()}
    return {"caps": caps, "in_flight": inflight}
