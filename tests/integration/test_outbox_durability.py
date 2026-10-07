"""If the relay dies mid-batch, no message is lost (section 14 / D4-
adjacent): `_publish_batch` marks `published_at` inside the same
transaction as the publishes, so a failure partway through leaves every
row in that batch unpublished for the next poll to retry."""

from unittest.mock import MagicMock

from sqlalchemy import select

from reflight.core.db import session_scope
from reflight.core.models import Outbox
from reflight.relay.main import _publish_batch


def test_relay_batch_failure_loses_nothing(db):
    with session_scope() as session:
        for i in range(5):
            session.add(Outbox(routing_key="plan.requested", payload={"i": i}, priority=0))

    channel = MagicMock()
    channel.basic_publish.side_effect = [None, None, RuntimeError("connection dropped mid-publish")]

    try:
        _publish_batch(channel)
    except RuntimeError:
        pass

    unpublished = db.execute(select(Outbox).where(Outbox.published_at.is_(None))).scalars().all()
    assert len(unpublished) == 5  # the whole batch's DB transaction rolled back

    db.execute(Outbox.__table__.delete())
    db.commit()
