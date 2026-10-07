from typing import Any

from sqlalchemy.orm import Session

from reflight.core.models import Outbox


def enqueue(db: Session, routing_key: str, payload: dict[str, Any], priority: int = 0) -> Outbox:
    """Insert an outbox row in the caller's transaction.

    The caller commits; the relay picks up unpublished rows and publishes
    them to RabbitMQ. This keeps the DB write and the message enqueue
    atomic (the transactional outbox pattern).
    """
    row = Outbox(routing_key=routing_key, payload=payload, priority=priority)
    db.add(row)
    return row
