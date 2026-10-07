from typing import Any

import httpx

from reflight.core.config import get_settings

TIMEOUT_SECONDS = 2.0


class TransientPartnerError(Exception):
    pass


def _post(path: str, idempotency_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    url = f"{settings.partners_base_url}{path}"
    try:
        resp = httpx.post(
            url,
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise TransientPartnerError(str(exc)) from exc

    if resp.status_code >= 500:
        raise TransientPartnerError(f"{path} returned {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json()


def issue_ticket(saga_id: str, pnr: str) -> dict[str, Any]:
    return _post("/tickets/issue", f"{saga_id}:ISSUE_TICKET", {"saga_id": saga_id, "pnr": pnr})


def void_ticket(saga_id: str) -> dict[str, Any]:
    return _post("/tickets/void", f"{saga_id}:VOID_TICKET", {"saga_id": saga_id})


def tag_bags(saga_id: str, pnr: str) -> dict[str, Any]:
    return _post("/bags/tag", f"{saga_id}:RETAG_BAGS", {"saga_id": saga_id, "pnr": pnr})


def notify(saga_id: str, message: str) -> dict[str, Any]:
    return _post("/notify", f"{saga_id}:NOTIFY", {"saga_id": saga_id, "message": message})
