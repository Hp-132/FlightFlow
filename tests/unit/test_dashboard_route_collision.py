"""ALL_IN_ONE serves the API and the dashboard from one origin, so any API
path that equals a dashboard route shadows it: a browser navigating there
gets the API's "x-api-key required" error instead of the page.

That is what /analytics did on the hosted demo. These tests pin the shape
that avoids it -- data endpoints live below their prefix, and bare page
paths fall through to index.html.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

from reflight.core.config import get_settings

PAGE_ROUTES = ["/analytics", "/live", "/invariants", "/sagas", "/compare", "/tenants", "/ops"]


@pytest.fixture
def all_in_one_client(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><html><head></head><body>app</body></html>")

    monkeypatch.setenv("DASHBOARD_DIST", str(dist))
    get_settings.cache_clear()

    import reflight.api.main as main

    importlib.reload(main)
    try:
        yield TestClient(main.app)
    finally:
        monkeypatch.delenv("DASHBOARD_DIST", raising=False)
        get_settings.cache_clear()
        importlib.reload(main)


@pytest.mark.parametrize("route", PAGE_ROUTES)
def test_dashboard_routes_serve_the_app_not_an_api_error(all_in_one_client, route):
    resp = all_in_one_client.get(route)

    assert resp.status_code == 200, f"{route} returned {resp.status_code}: {resp.text[:200]}"
    assert "text/html" in resp.headers["content-type"], f"{route} served {resp.headers['content-type']}"


def test_analytics_data_endpoint_still_requires_a_key():
    from reflight.api.main import app

    resp = TestClient(app).get("/analytics/summary")

    assert resp.status_code == 422
    assert "x-api-key" in resp.text


def test_no_api_route_collides_with_a_dashboard_route():
    from reflight.api.main import app

    api_paths = {
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith("/") and "{" not in getattr(route, "path", "")
    }

    assert api_paths.isdisjoint(PAGE_ROUTES), f"shadowed dashboard routes: {api_paths & set(PAGE_ROUTES)}"
