"""Per-airline concurrency cap (F13) so one noisy tenant can't starve the
others.

Each in-flight step holds a lease in a Redis sorted set scored by
acquisition time. Leases older than LEASE_SECONDS are swept on every
acquire, so a worker that hard-crashes mid-step (the chaos hook does
exactly that) releases its slot automatically instead of leaking it.

Acquire is a single Lua script so the sweep/count/insert can't interleave
with another worker. This is a fairness heuristic, not a correctness
invariant -- the oversell guarantee lives in the DB, not here.
"""

import time
import uuid

from reflight.core.redis_client import get_redis

LEASE_SECONDS = 30
DEFAULT_CAP_KEY = "fairness:cap:default"
CAP_KEY_PREFIX = "fairness:cap:"
INFLIGHT_KEY_PREFIX = "fairness:inflight:"
DEFAULT_CAP = 8

# KEYS[1] = inflight zset, ARGV = now, cutoff, cap, token, ttl
_ACQUIRE_LUA = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[2])
local count = redis.call('ZCARD', KEYS[1])
if tonumber(ARGV[3]) > 0 and count >= tonumber(ARGV[3]) then
  return 0
end
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
redis.call('EXPIRE', KEYS[1], ARGV[5])
return 1
"""

_acquire_script = None


def _script():
    global _acquire_script
    if _acquire_script is None:
        _acquire_script = get_redis().register_script(_ACQUIRE_LUA)
    return _acquire_script


def cap_for(airline_id: str) -> int:
    """0 means unlimited."""
    r = get_redis()
    value = r.get(f"{CAP_KEY_PREFIX}{airline_id}") or r.get(DEFAULT_CAP_KEY)
    try:
        return int(value) if value is not None else DEFAULT_CAP
    except (TypeError, ValueError):
        return DEFAULT_CAP


def new_token() -> str:
    return uuid.uuid4().hex


def acquire(airline_id: str, token: str) -> bool:
    cap = cap_for(airline_id)
    if cap <= 0:
        return True
    now = time.time()
    try:
        granted = _script()(
            keys=[f"{INFLIGHT_KEY_PREFIX}{airline_id}"],
            args=[now, now - LEASE_SECONDS, cap, token, LEASE_SECONDS * 4],
        )
        return bool(granted)
    except Exception:
        # Redis being down must not stop rebooking -- fail open.
        return True


def release(airline_id: str, token: str) -> None:
    try:
        get_redis().zrem(f"{INFLIGHT_KEY_PREFIX}{airline_id}", token)
    except Exception:
        pass  # the lease will expire on its own


def inflight_counts() -> dict[str, int]:
    r = get_redis()
    counts = {}
    cutoff = time.time() - LEASE_SECONDS
    for key in r.scan_iter(f"{INFLIGHT_KEY_PREFIX}*"):
        r.zremrangebyscore(key, 0, cutoff)
        counts[key.removeprefix(INFLIGHT_KEY_PREFIX)] = r.zcard(key)
    return counts


def set_caps(default_cap: int | None = None, caps: dict[str, int] | None = None) -> None:
    r = get_redis()
    if default_cap is not None:
        r.set(DEFAULT_CAP_KEY, default_cap)
    for airline_id, cap in (caps or {}).items():
        r.set(f"{CAP_KEY_PREFIX}{airline_id}", cap)


def get_caps() -> dict[str, int]:
    r = get_redis()
    caps = {}
    for key in r.scan_iter(f"{CAP_KEY_PREFIX}*"):
        name = key.removeprefix(CAP_KEY_PREFIX)
        try:
            caps[name] = int(r.get(key))
        except (TypeError, ValueError):
            continue
    caps.setdefault("default", DEFAULT_CAP)
    return caps
