import random
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from reflight.core.models import PartnerIdempotency
from reflight.core.redis_client import get_redis

FAILURE_RATE_KEY = "chaos:partner_failure_rate"


def failure_rate() -> float:
    try:
        value = get_redis().get(FAILURE_RATE_KEY)
        return float(value) if value is not None else 0.0
    except Exception:
        return 0.0


def call_idempotent(
    db: Session, idempotency_key: str, endpoint: str, compute: Callable[[], dict[str, Any]]
) -> dict[str, Any]:
    """Runs `compute` at most once per idempotency key. A stored response is
    always replayed verbatim, even if a fresh call would now roll a
    failure -- that's the whole point of the key: a crash-and-retry after a
    partner call already succeeded must not flip the outcome."""
    existing = db.get(PartnerIdempotency, idempotency_key)
    if existing is not None:
        return existing.response_json

    if random.random() < failure_rate():
        raise HTTPException(status_code=503, detail=f"{endpoint}: simulated partner outage")

    response = compute()
    db.add(PartnerIdempotency(idempotency_key=idempotency_key, endpoint=endpoint, response_json=response))
    return response
