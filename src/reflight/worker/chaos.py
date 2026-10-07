"""Fault injection (F8): reads the crash probability set via POST /chaos
and, if triggered, hard-kills the process with os._exit so the effect is a
real crash, not a caught exception -- the in-flight message is left
unacked and RabbitMQ redelivers it once this worker (or its replacement,
per the container's restart policy) reconnects. Correctness then depends
on `processed_messages` idempotency, not on catching our own fake error.
"""

import logging
import os
import random

from reflight.core.redis_client import get_redis

log = logging.getLogger("reflight.worker.chaos")

CRASH_PROBABILITY_KEY = "chaos:crash_probability"


def _crash_probability() -> float:
    try:
        value = get_redis().get(CRASH_PROBABILITY_KEY)
        return float(value) if value is not None else 0.0
    except Exception:
        return 0.0


def maybe_crash(point: str) -> None:
    # Deterministic override for crash-injection tests (section 14): forces
    # a crash at exactly one named point instead of relying on the random
    # chaos probability, so tests can assert on both crash points reliably.
    if os.environ.get("REFLIGHT_FORCE_CRASH_AT") == point:
        log.warning("chaos: forced crash at %s (test override)", point)
        os._exit(1)

    p = _crash_probability()
    if p > 0 and random.random() < p:
        log.warning("chaos: simulating hard crash at %s (p=%.2f)", point, p)
        os._exit(1)
