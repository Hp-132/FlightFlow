from functools import lru_cache

import redis

from reflight.core.config import get_settings


@lru_cache
def get_redis() -> redis.Redis:
    settings = get_settings()
    if settings.redis_url_override:
        # Managed Redis hands out a single rediss:// URL with credentials.
        return redis.Redis.from_url(settings.redis_url_override, decode_responses=True)
    return redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)
