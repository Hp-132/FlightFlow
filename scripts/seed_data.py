#!/usr/bin/env python3
"""Seeds one deterministic run and freezes it into a JSON fixture, so the
dashboard has data on a fresh boot before anyone has triggered a storm.

Drives the same flow as measure_run.py (generate -> load -> create -> start)
with seed 42 / GREEDY. The dashboard falls back to the fixture when the live
API reports no affected bookings, labelled there as sample data (see
dashboard/src/lib/seed-fixture.ts).

Counters are sampled once a second for the whole run, not just at the end: the
Run Progress charts are built client-side from the counter stream, so an
end-state snapshot alone would leave them empty.

    python scripts/seed_data.py                      # skips if fixture exists
    python scripts/seed_data.py --force              # re-seed and overwrite
    python scripts/seed_data.py --preset storm --severity 0.9

Affected-booking count is emergent, not a dial: it falls out of preset size
and which flights the storm hits. Measured against a live stack (seed 42):
small/0.8 and small/1.0 both give 37 bookings with 38% recovered, while
storm/0.1 gives 275 with 81% recovered and five times the chart samples --
severity barely moves `small`, because its storm window holds few hub
departures. Hence the storm default. --target-bookings only sets the band
this script warns outside of.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

TERMINAL = {"COMPLETED", "COMPENSATED", "FAILED_NO_CAPACITY", "NEEDS_MANUAL"}
NON_TERMINAL = ["PLANNED", "HOLDING", "TICKETING", "BAGGAGE", "NOTIFYING", "COMPENSATING"]

# Keep in step with HISTORY_LIMIT in dashboard/src/pages/live-run.tsx: the
# page only plots the last N points, so more than that is dead weight.
HISTORY_LIMIT = 60
SAMPLE_INTERVAL_SECONDS = 1.0
FIXTURE_VERSION = 1

# The compose seeder sets SEED_OUT to its mount instead of passing --out: a
# leading-slash path on the command line gets rewritten by MSYS2 (Git Bash
# on Windows) before Docker ever sees it.
DEFAULT_OUT = "dashboard/public/fixtures/seed42_greedy.json"


def call(base: str, key: str, method: str, path: str, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{base}{path}", data=data, method=method)
    req.add_header("X-API-Key", key)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        print(f"{method} {path} failed: {exc.code} {exc.read().decode()[:400]}", file=sys.stderr)
        raise


def wait_for_api(base: str, timeout: float) -> bool:
    """Run directly (not via the compose seeder), this may start before the API."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/healthz", timeout=5) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(2)
    return False


def sample(counters: dict, offset_seconds: float) -> dict:
    """One chart point, in the shape the dashboard's HistoryPoint expects."""
    sagas = counters.get("sagas_by_state") or {}
    return {
        "offset_seconds": round(offset_seconds, 1),
        "completed": sagas.get("COMPLETED", 0),
        "inFlight": sum(sagas.get(state, 0) for state in NON_TERMINAL),
        "queueDepth": counters.get("queue_depth") or 0,
        "workers": counters.get("workers_active") or 0,
    }


def drive_run(base: str, key: str, args: argparse.Namespace) -> dict:
    scenario = call(
        base, key, "POST", "/scenarios",
        {"preset": args.preset, "seed": args.seed, "severity": args.severity},
    )
    call(base, key, "POST", f"/scenarios/{scenario['id']}/load")

    # A fixed key makes re-runs reuse the same run row rather than piling up a
    # new one on every boot.
    idempotency_key = f"seed-{args.preset}-{args.seed}-{args.strategy}"
    run = call(
        base, key, "POST", "/runs",
        {"scenario_id": scenario["id"], "strategy": args.strategy},
        headers={"Idempotency-Key": idempotency_key},
    )

    started_wall = time.monotonic()
    started = call(base, key, "POST", f"/runs/{run['id']}/start")

    history: list[dict] = []
    settled = False
    counters: dict = {}
    deadline = started_wall + args.timeout
    while time.monotonic() < deadline:
        counters = call(base, key, "GET", f"/runs/{run['id']}")
        history.append(sample(counters, time.monotonic() - started_wall))
        states = counters.get("sagas_by_state") or {}
        if states and all(state in TERMINAL for state in states):
            settled = True
            break
        time.sleep(SAMPLE_INTERVAL_SECONDS)

    wall_seconds = time.monotonic() - started_wall

    # Thin to HISTORY_LIMIT, keeping the shape of the curve rather than its tail.
    if len(history) > HISTORY_LIMIT:
        step = len(history) / HISTORY_LIMIT
        thinned = [history[int(i * step)] for i in range(HISTORY_LIMIT - 1)]
        thinned.append(history[-1])
        history = thinned

    invariants = call(base, key, "POST", f"/runs/{run['id']}/invariants/check")
    metrics = call(base, key, "GET", f"/runs/{run['id']}/metrics")
    disruptions = call(base, key, "GET", f"/runs/{run['id']}/disruptions")
    tenants = call(base, key, "GET", f"/runs/{run['id']}/tenants")

    return {
        "fixture_version": FIXTURE_VERSION,
        "generated_by": "scripts/seed_data.py",
        "captured_at": datetime.now(UTC).isoformat(),
        "params": {
            "preset": args.preset,
            "seed": args.seed,
            "strategy": args.strategy,
            "severity": args.severity,
        },
        "run": {
            "run_id": run["id"],
            "scenario_id": scenario["id"],
            "status": counters.get("status"),
            "strategy": args.strategy,
            "settled": settled,
            "wall_seconds": round(wall_seconds, 1),
        },
        "start": started,
        "counters": counters,
        "history": history,
        "disruptions": disruptions or [],
        "metrics": metrics,
        "tenants": tenants or [],
        "invariants": invariants,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--base", default=os.environ.get("SEED_API_BASE", "http://localhost:8000"))
    ap.add_argument("--key", default=os.environ.get("API_STATIC_KEY", "dev-local-key-change-me"))
    ap.add_argument("--out", type=Path, default=Path(os.environ.get("SEED_OUT", DEFAULT_OUT)))
    ap.add_argument("--preset", default="storm", choices=["small", "storm", "mega"])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--strategy", default="greedy", choices=["greedy", "cpsat"])
    ap.add_argument("--severity", type=float, default=0.1)
    ap.add_argument("--target-bookings", type=int, default=250,
                    help="expected affected-booking count; only sets the warning band")
    ap.add_argument("--tolerance", type=float, default=2.0,
                    help="warn when the actual count is off target by more than this factor")
    ap.add_argument("--timeout", type=float, default=600, help="seconds to wait for the run to settle")
    ap.add_argument("--wait-api", type=float, default=180, help="seconds to wait for /healthz")
    ap.add_argument("--force", action="store_true", help="re-seed even if the fixture already exists")
    args = ap.parse_args()

    if args.out.is_file() and not args.force:
        print(f"fixture already present at {args.out}; nothing to do (use --force to re-seed)")
        return 0

    if not wait_for_api(args.base, args.wait_api):
        print(f"API never became healthy at {args.base} within {args.wait_api:g}s", file=sys.stderr)
        return 1

    print(f"==> seeding {args.preset}/seed {args.seed}/{args.strategy} via {args.base}", file=sys.stderr)

    # Chaos left set in Redis would bake crash noise into the default fixture.
    call(args.base, args.key, "POST", "/chaos",
         {"crash_probability": 0.0, "partner_failure_rate": 0.0})

    fixture = drive_run(args.base, args.key, args)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")

    affected = fixture["start"]["disrupted_bookings"]
    sagas = fixture["counters"].get("sagas_by_state") or {}
    invariants = fixture["invariants"] or {}
    print(
        f"wrote {args.out} -- {affected} affected bookings, "
        f"{sum(sagas.values())} sagas, {len(fixture['history'])} chart samples, "
        f"settled={fixture['run']['settled']}, "
        f"invariants={'pass' if invariants.get('passed') else invariants.get('total_violations', '?')}"
    )

    target = args.target_bookings
    if target > 0 and not (target / args.tolerance <= affected <= target * args.tolerance):
        print(
            f"NOTE: {affected} affected bookings is well off the ~{target} target. "
            f"Adjust --preset or --severity (currently {args.preset}/{args.severity:g}).",
            file=sys.stderr,
        )
    if not fixture["run"]["settled"]:
        print(
            f"NOTE: run did not settle within {args.timeout:g}s; the fixture captures it mid-flight.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
