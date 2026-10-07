"""Mock ticketing/baggage/notification partner with fault injection and
idempotency-key deduplication. Keeps its own tables in the `partners`
Postgres schema (core/models.py), separate from the rest of the system."""

import uuid

from fastapi import Depends, FastAPI, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from reflight.api.deps import get_db
from reflight.core.models import PartnerBagTag, PartnerTicket
from reflight.core.telemetry import instrument_fastapi
from reflight.partners.idempotency import call_idempotent

app = FastAPI(title="Reflight Partners (mock)", version="0.1.0")
instrument_fastapi(app)


class SagaRef(BaseModel):
    saga_id: str


class TicketRequest(SagaRef):
    pnr: str


class BagRequest(SagaRef):
    pnr: str


class NotifyRequest(SagaRef):
    message: str


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/tickets/issue")
def issue_ticket(req: TicketRequest, idempotency_key: str = Header(..., alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    def compute() -> dict:
        ticket_id = str(uuid.uuid4())
        db.add(PartnerTicket(id=ticket_id, saga_id=req.saga_id, pnr=req.pnr, status="ISSUED"))
        return {"ticket_id": ticket_id, "status": "ISSUED"}

    result = call_idempotent(db, idempotency_key, "issue_ticket", compute)
    db.commit()
    return result


@app.post("/tickets/void")
def void_ticket(req: SagaRef, idempotency_key: str = Header(..., alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    def compute() -> dict:
        db.query(PartnerTicket).filter(PartnerTicket.saga_id == req.saga_id).update({"status": "VOIDED"})
        return {"status": "VOIDED"}

    result = call_idempotent(db, idempotency_key, "void_ticket", compute)
    db.commit()
    return result


@app.post("/bags/tag")
def tag_bags(req: BagRequest, idempotency_key: str = Header(..., alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    def compute() -> dict:
        tag_id = str(uuid.uuid4())
        db.add(PartnerBagTag(id=tag_id, saga_id=req.saga_id, pnr=req.pnr, status="TAGGED"))
        return {"tag_id": tag_id, "status": "TAGGED"}

    result = call_idempotent(db, idempotency_key, "tag_bags", compute)
    db.commit()
    return result


@app.post("/notify")
def notify(req: NotifyRequest, idempotency_key: str = Header(..., alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    def compute() -> dict:
        return {"status": "SENT"}

    result = call_idempotent(db, idempotency_key, "notify", compute)
    db.commit()
    return result
