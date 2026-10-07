import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from reflight.api.routes_chaos import fairness_router
from reflight.api.routes_chaos import router as chaos_router
from reflight.api.routes_finops import router as finops_router
from reflight.api.routes_invariants import router as invariants_router
from reflight.api.routes_runs import router as runs_router
from reflight.api.routes_runs import stream_router
from reflight.api.routes_sagas import router as sagas_router
from reflight.api.routes_scenarios import router as scenarios_router
from reflight.core.config import get_settings
from reflight.core.telemetry import instrument_fastapi

settings = get_settings()

app = FastAPI(title="Reflight API", version="0.1.0")

# The dashboard may run on a different origin (Vite dev server, or a
# separately hosted static site). Locked to an explicit list rather than
# "*" since requests carry X-API-Key; set CORS_ORIGINS to change it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scenarios_router)
app.include_router(runs_router)
app.include_router(stream_router)
app.include_router(chaos_router)
app.include_router(fairness_router)
app.include_router(invariants_router)
app.include_router(finops_router)
app.include_router(sagas_router)

instrument_fastapi(app)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


# All-in-one mode: the mock partners service lives in this process too,
# reached by the worker at PARTNERS_URL=http://127.0.0.1:$PORT/partners.
if settings.all_in_one:
    from reflight.partners.main import app as partners_app

    app.mount("/partners", partners_app)


# Optionally serve the built dashboard from the same origin, so one hosted
# URL is the whole product. Registered last: API routes always win, and any
# other GET falls back to index.html for client-side routing.
if settings.dashboard_dist and Path(settings.dashboard_dist, "index.html").is_file():
    _dist = Path(settings.dashboard_dist).resolve()
    _index = _dist / "index.html"

    def _index_with_runtime_config() -> HTMLResponse:
        """index.html with this server's API key injected at serve time, so
        the dashboard always matches API_STATIC_KEY without depending on a
        build-time VITE_API_KEY (hosts don't reliably pass build args). The
        key is a demo key: anyone who can load the page can read it."""
        key = json.dumps(settings.api_static_key).replace("<", "\\u003c")
        script = f"<script>window.__FLIGHTFLOW_API_KEY__={key}</script>"
        html = _index.read_text(encoding="utf-8").replace("</head>", f"{script}</head>", 1)
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.get("/{full_path:path}", include_in_schema=False)
    def dashboard(full_path: str):
        candidate = (_dist / full_path).resolve()
        if full_path and _dist in candidate.parents and candidate.is_file() and candidate != _index:
            return FileResponse(candidate)
        if full_path.startswith(("assets/", "images/")):
            raise HTTPException(status_code=404)
        return _index_with_runtime_config()
