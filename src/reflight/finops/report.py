"""FinOps estimate: what one run would have cost on a managed platform
(F12, section 12).

    cost_run      = compute + queue + object_store + database
    compute       = worker replica_seconds x (vcpu x price_vcpu_s + gib x price_gib_s)
                    + planner_cpu_seconds x price_vcpu_s
    queue         = requests / 1e6 x price_per_million
    object_store  = GB_written x price_gb + PUT/GET x price_request
    database      = run_hours x price_small_instance_hour
    cost_per_1000 = cost_run / recovered_passengers x 1000

Everything on the left is measured from this run (see `inputs` in the
output); everything on the right comes from finops/prices.yaml, which
carries its own `as_of`/`source_url` per line item. These are estimates
built on stated assumptions, not billing data.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text
from sqlalchemy.orm import Session

from reflight.core.ops_metrics import avg_workers_over, get_workers_active
from reflight.core.run_metrics import compute_run_metrics

# Each message is charged as three queue requests: publish, consume, ack.
REQUESTS_PER_MESSAGE = 3

SQL_RUN_MESSAGES = """
SELECT COUNT(*)
FROM outbox o
LEFT JOIN sagas s ON s.id::text = (o.payload ->> 'saga_id')
WHERE (o.payload ->> 'run_id') = :run_id OR s.run_id::text = :run_id
"""

SQL_DB_SIZE = "SELECT pg_database_size(current_database())"


def _prices_path() -> Path:
    override = os.environ.get("REFLIGHT_PRICES_FILE")
    if override:
        return Path(override)
    # repo root / finops / prices.yaml -- src/reflight/finops/report.py -> 4 up
    return Path(__file__).resolve().parents[3] / "finops" / "prices.yaml"


@lru_cache
def load_prices() -> dict[str, Any]:
    with open(_prices_path(), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _scenario_bytes(db: Session, run_id: str) -> int:
    key = db.execute(
        text("SELECT sc.minio_key FROM runs r JOIN scenarios sc ON sc.id = r.scenario_id WHERE r.id = :run_id"),
        {"run_id": run_id},
    ).scalar_one_or_none()
    if not key:
        return 0
    try:
        from reflight.core.storage import object_size

        return object_size(key)
    except Exception:
        return 0


def collect_inputs(db: Session, run_id: str) -> dict[str, Any]:
    metrics = compute_run_metrics(db, run_id)
    run_seconds = metrics["recovery_seconds"] or 0.0

    avg_workers = avg_workers_over(run_seconds) if run_seconds else None
    assumptions: list[str] = []
    if avg_workers is None:
        avg_workers = float(get_workers_active() or 1)
        assumptions.append(
            "Prometheus had no worker history for the run window, so replica-seconds "
            f"use the current worker count ({avg_workers:g}) held flat."
        )

    messages = db.execute(text(SQL_RUN_MESSAGES), {"run_id": run_id}).scalar_one() or 0
    db_bytes = db.execute(text(SQL_DB_SIZE)).scalar_one() or 0

    return {
        "run_seconds": round(run_seconds, 1),
        "run_hours": round(run_seconds / 3600, 6),
        "avg_workers": round(float(avg_workers), 3),
        "worker_replica_seconds": round(float(avg_workers) * run_seconds, 1),
        "planner_cpu_seconds": metrics["planner_cpu_seconds"],
        "messages": messages,
        "queue_requests": messages * REQUESTS_PER_MESSAGE,
        "object_store_bytes": _scenario_bytes(db, run_id),
        "object_store_puts": 1,
        "object_store_gets": 1,
        "db_size_bytes": db_bytes,
        "recovered": metrics["recovered"],
        "strategy": metrics["strategy"],
        "_assumptions": assumptions,
        "_metrics": metrics,
    }


def build_report(
    db: Session, run_id: str, profile: str | None = None, *, live_only: bool = False
) -> dict[str, Any]:
    if not live_only:
        from reflight.core.models import Run

        run = db.get(Run, run_id)
        stored = (run.metrics_json or {}).get("final_finops") if run else None
        # The snapshot is taken against the default profile; asking for a
        # different one still needs a live recompute.
        if stored and (profile is None or stored.get("profile") == profile):
            return {**stored, "from_snapshot": True}

    prices = load_prices()
    profile_name = profile or prices["default_profile"]
    if profile_name not in prices["profiles"]:
        raise ValueError(f"unknown price profile {profile_name!r}")
    p = prices["profiles"][profile_name]
    sizing = prices["sizing"]

    inputs = collect_inputs(db, run_id)
    assumptions = list(inputs.pop("_assumptions"))
    metrics = inputs.pop("_metrics")

    worker_rate = (
        sizing["worker"]["vcpu"] * p["compute"]["price_vcpu_second"]
        + sizing["worker"]["gib"] * p["compute"]["price_gib_second"]
    )
    worker_cost = inputs["worker_replica_seconds"] * worker_rate
    planner_cost = inputs["planner_cpu_seconds"] * p["compute"]["price_vcpu_second"]
    compute_cost = worker_cost + planner_cost

    queue_cost = inputs["queue_requests"] / 1e6 * p["queue"]["price_per_million_requests"]

    gb_written = inputs["object_store_bytes"] / 1e9
    object_cost = (
        gb_written * p["object_store"]["price_gb_month"]
        + inputs["object_store_puts"] / 1000 * p["object_store"]["price_per_1000_put"]
        + inputs["object_store_gets"] / 1000 * p["object_store"]["price_per_1000_get"]
    )

    database_cost = inputs["run_hours"] * p["database"]["price_instance_hour"]

    total = compute_cost + queue_cost + object_cost + database_cost
    recovered = inputs["recovered"]
    cost_per_1000 = (total / recovered * 1000) if recovered else None

    assumptions += [
        f"Worker sized at {sizing['worker']['vcpu']} vCPU / {sizing['worker']['gib']} GiB, "
        "matching the k8s requests in k8s/base.",
        "Object storage is charged a full month for the scenario JSON, which "
        "overstates a run that only lives for minutes.",
        "Database is charged as run_hours on one small instance; storage, IOPS "
        "and backups are excluded.",
        f"Each message counts as {REQUESTS_PER_MESSAGE} queue requests (publish, consume, ack).",
        "Free tiers are ignored -- a real bill for a run this small would likely be zero.",
    ]

    return {
        "run_id": run_id,
        "profile": profile_name,
        "profile_label": p["label"],
        "currency": p["currency"],
        "region": p["region"],
        "inputs": inputs,
        "metrics": metrics,
        "components": {
            "compute": round(compute_cost, 6),
            "compute_worker": round(worker_cost, 6),
            "compute_planner": round(planner_cost, 6),
            "queue": round(queue_cost, 6),
            "object_store": round(object_cost, 6),
            "database": round(database_cost, 6),
        },
        "cost_run": round(total, 6),
        "cost_per_1000_recovered": round(cost_per_1000, 4) if cost_per_1000 is not None else None,
        "price_sources": {
            component: {
                "as_of": p[component]["as_of"],
                "source_url": p[component]["source_url"],
                "confidence": p[component]["confidence"],
            }
            for component in ("compute", "queue", "object_store", "database")
        },
        "assumptions": assumptions,
    }


def render_markdown(report: dict[str, Any]) -> str:
    cur = report["currency"]
    c = report["components"]
    i = report["inputs"]
    m = report["metrics"]

    lines = [
        f"# FinOps estimate — run `{report['run_id'][:8]}` ({m['strategy']})",
        "",
        f"Profile: **{report['profile_label']}** (`{report['profile']}`, {report['region']})",
        "",
        "| Component | Measured input | Cost |",
        "|---|---|---|",
        f"| Compute — workers | {i['worker_replica_seconds']:.0f} replica-seconds "
        f"({i['avg_workers']:g} avg workers × {i['run_seconds']:.0f}s) | {cur} {c['compute_worker']:.6f} |",
        f"| Compute — planner | {i['planner_cpu_seconds']:.2f} CPU-seconds | {cur} {c['compute_planner']:.6f} |",
        f"| Queue | {i['messages']:,} messages → {i['queue_requests']:,} requests | {cur} {c['queue']:.6f} |",
        f"| Object store | {i['object_store_bytes']/1e6:.2f} MB scenario JSON | {cur} {c['object_store']:.6f} |",
        f"| Database | {i['run_hours']:.4f} instance-hours | {cur} {c['database']:.6f} |",
        f"| **Total** | | **{cur} {report['cost_run']:.6f}** |",
        "",
    ]

    if report["cost_per_1000_recovered"] is not None:
        lines += [
            f"**Cost per 1,000 recovered passengers: {cur} "
            f"{report['cost_per_1000_recovered']:.4f}** "
            f"({m['recovered']:,} recovered of {m['total_sagas']:,} sagas)",
            "",
        ]
    else:
        lines += ["No passengers were recovered, so cost per 1,000 is undefined.", ""]

    lines += ["## Price sources", "", "| Component | As of | Confidence | Source |", "|---|---|---|---|"]
    for component, src in report["price_sources"].items():
        lines.append(
            f"| {component} | {src['as_of']} | {src['confidence']} | {src['source_url']} |"
        )

    lines += ["", "## Assumptions", ""]
    lines += [f"- {a}" for a in report["assumptions"]]
    lines += ["", "_Estimates only, derived from published list prices — not billing data._"]
    return "\n".join(lines)
