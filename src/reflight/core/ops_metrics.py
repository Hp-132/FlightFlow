"""Best-effort reads of live ops data (RabbitMQ queue depth, active worker
count from Prometheus) for the dashboard's combined chart. Both degrade to
None rather than failing the request if the ops stack isn't reachable."""

from urllib.parse import quote, unquote, urlparse

import httpx

from reflight.core.config import get_settings

TIMEOUT = 1.5


def _mgmt_endpoint(queue: str) -> tuple[str, tuple[str, str]]:
    """Management API URL + credentials. A managed broker (RABBITMQ_URL,
    e.g. CloudAMQP) serves it over HTTPS on the same host under /api."""
    settings = get_settings()
    if settings.rabbitmq_url_override:
        u = urlparse(settings.rabbitmq_url_override)
        vhost = quote(unquote(u.path.lstrip("/")) or "/", safe="")
        auth = (unquote(u.username or ""), unquote(u.password or ""))
        return f"https://{u.hostname}/api/queues/{vhost}/{queue}", auth
    url = f"http://{settings.rabbitmq_mgmt_host}:{settings.rabbitmq_mgmt_port}/api/queues/%2F/{queue}"
    return url, (settings.rabbitmq_default_user, settings.rabbitmq_default_pass)


def get_queue_depth(queue: str = "saga.steps") -> int | None:
    url, auth = _mgmt_endpoint(queue)
    try:
        resp = httpx.get(url, auth=auth, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("messages_ready")
    except Exception:
        return None


def get_workers_active() -> int | None:
    settings = get_settings()
    if settings.all_in_one:
        return 1  # exactly one in-process worker; no Prometheus in this mode
    url = f"http://{settings.prometheus_host}:{settings.prometheus_port}/api/v1/query"
    try:
        resp = httpx.get(url, params={"query": "sum(workers_active)"}, timeout=TIMEOUT)
        resp.raise_for_status()
        result = resp.json()["data"]["result"]
        return int(float(result[0]["value"][1])) if result else 0
    except Exception:
        return None


def avg_workers_over(window_seconds: float) -> float | None:
    """Mean worker count over the last `window_seconds`, used by the FinOps
    report to integrate replica-seconds (section 12)."""
    if window_seconds <= 0:
        return None
    settings = get_settings()
    url = f"http://{settings.prometheus_host}:{settings.prometheus_port}/api/v1/query"
    query = f"avg_over_time(sum(workers_active)[{int(window_seconds)}s:5s])"
    try:
        resp = httpx.get(url, params={"query": query}, timeout=TIMEOUT * 2)
        resp.raise_for_status()
        result = resp.json()["data"]["result"]
        return float(result[0]["value"][1]) if result else None
    except Exception:
        return None
