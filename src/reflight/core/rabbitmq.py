"""RabbitMQ topology and connection helpers.

Topology is declared idempotently by whichever service starts first
(relay and worker both call declare_topology() on startup) -- nothing is
clicked together in the management UI.

Exchanges:
  saga.direct        (direct)  -- routes to saga.steps by routing key = step name
Queues:
  saga.steps         priority queue (0-9), consumed by workers
  saga.retry.5s      TTL 5s,  dead-letters back to saga.steps
  saga.retry.30s     TTL 30s, dead-letters back to saga.steps
  saga.dlq           terminal poison-message sink
  plan.requested     consumed by planner
"""

import pika

from reflight.core.config import get_settings

EXCHANGE_SAGA = "saga.direct"
EXCHANGE_PLAN = "plan.direct"

QUEUE_SAGA_STEPS = "saga.steps"
QUEUE_RETRY_5S = "saga.retry.5s"
QUEUE_RETRY_30S = "saga.retry.30s"
QUEUE_DELAY_2S = "saga.delay.2s"
QUEUE_DLQ = "saga.dlq"
QUEUE_PLAN_REQUESTED = "plan.requested"

ROUTING_PLAN_REQUESTED = "plan.requested"

MAX_PRIORITY = 9


def get_connection() -> pika.BlockingConnection:
    settings = get_settings()
    params = pika.URLParameters(settings.rabbitmq_url)
    return pika.BlockingConnection(params)


def declare_topology(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    channel.exchange_declare(exchange=EXCHANGE_SAGA, exchange_type="direct", durable=True)
    channel.exchange_declare(exchange=EXCHANGE_PLAN, exchange_type="direct", durable=True)

    channel.queue_declare(
        queue=QUEUE_SAGA_STEPS,
        durable=True,
        arguments={"x-max-priority": MAX_PRIORITY},
    )
    channel.queue_bind(queue=QUEUE_SAGA_STEPS, exchange=EXCHANGE_SAGA, routing_key=QUEUE_SAGA_STEPS)

    channel.queue_declare(
        queue=QUEUE_RETRY_5S,
        durable=True,
        arguments={
            "x-message-ttl": 5000,
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": QUEUE_SAGA_STEPS,
        },
    )
    channel.queue_declare(
        queue=QUEUE_RETRY_30S,
        durable=True,
        arguments={
            "x-message-ttl": 30000,
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": QUEUE_SAGA_STEPS,
        },
    )
    # F13 fairness: steps parked here when their airline is at its
    # concurrency cap, dead-lettered back to saga.steps 2s later.
    channel.queue_declare(
        queue=QUEUE_DELAY_2S,
        durable=True,
        arguments={
            "x-message-ttl": 2000,
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": QUEUE_SAGA_STEPS,
        },
    )

    channel.queue_declare(queue=QUEUE_DLQ, durable=True)

    channel.queue_declare(queue=QUEUE_PLAN_REQUESTED, durable=True)
    channel.queue_bind(
        queue=QUEUE_PLAN_REQUESTED, exchange=EXCHANGE_PLAN, routing_key=ROUTING_PLAN_REQUESTED
    )
