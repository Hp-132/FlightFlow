from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from reflight.api.deps import get_db, require_api_key
from reflight.core.models import Booking, Passenger, Saga, SagaEvent

router = APIRouter(tags=["sagas"], dependencies=[Depends(require_api_key)])


@router.get("/sagas/{saga_id}/events")
def get_saga_events(saga_id: str, db: Session = Depends(get_db)) -> dict:
    saga = db.get(Saga, saga_id)
    if saga is None:
        raise HTTPException(status_code=404, detail="saga not found")
    events = db.execute(
        select(SagaEvent).where(SagaEvent.saga_id == saga_id).order_by(SagaEvent.seq)
    ).scalars().all()
    return {
        "saga_id": saga_id,
        "booking_id": saga.booking_id,
        "state": saga.state,
        "current_step": saga.current_step,
        "priority": saga.priority,
        "events": [
            {"seq": e.seq, "type": e.type, "payload": e.payload, "created_at": e.created_at.isoformat()}
            for e in events
        ],
    }


@router.get("/sagas/search")
def search_sagas(q: str, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Saga, Booking, Passenger)
        .join(Booking, Booking.id == Saga.booking_id)
        .join(Passenger, Passenger.id == Booking.passenger_id)
        .where((Booking.pnr.ilike(f"%{q}%")) | (Passenger.name.ilike(f"%{q}%")))
        .limit(25)
    ).all()
    return [
        {
            "saga_id": saga.id,
            "booking_id": booking.id,
            "pnr": booking.pnr,
            "passenger_name": passenger.name,
            "state": saga.state,
            "current_step": saga.current_step,
        }
        for saga, booking, passenger in rows
    ]
