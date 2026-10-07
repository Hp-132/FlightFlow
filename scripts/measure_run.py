#!/usr/bin/env python3
"""End-to-end measurement harness -- the source of the numbers in the
README's results table.

Drives one full run through the API (generate -> load -> create -> start),
polls until every saga is terminal, runs the invariant checker, pulls the
FinOps estimate, and prints a Markdown row. Nothing here is estimated:
every number printed is measured from this run.

    python scripts/measure_run.py --preset storm --strategy greedy
    python scripts/measure_run.py --preset storm --strategy cpsat --chaos 0.3
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

TERMINAL = {"COMPLETED", "COMPENSATED", "FAILED_NO_CAPACITY", "NEEDS_MANUAL"}


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


def wait_for_terminal(base: str, key: str, run_id: str, timeout: float) -> tuple[dict, float, bool]:
    started = time.monotonic()
    last = {}
    while time.monotonic() - started < timeout:
        counters = call(base, key, "GET", f"/runs/{run_id}")
        states = counters.get("sagas_by_state", {})
        last = states
        if states and all(state in TERMINAL for state in states):
            return states, time.monotonic() - started, True
        time.sleep(2)
    return last, time.monotonic() - started, False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--key", default="dev-local-key-change-me")
    ap.add_argument("--preset", default="storm", choices=["small", "storm", "mega"])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--severity", type=float, default=0.8)
    ap.add_argument("--strategy", default="greedy", choices=["greedy", "cpsat"])
    ap.add_argument("--chaos", type=float, default=0.0, help="worker crash probability")
    ap.add_argument("--partner-failure", type=float, default=0.0)
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    label = args.label or f"{args.preset}/{args.strategy}" + (f"/chaos{args.chaos:g}" if args.chaos else "")
    print(f"==> {label}", file=sys.stderr)

    call(args.base, args.key, "POST", "/chaos",
         {"crash_probability": args.chaos, "partner_failure_rate": args.partner_failure})

    scenario = call(args.base, args.key, "POST", "/scenarios",
                    {"preset": args.preset, "seed": args.seed, "severity": args.severity})
    call(args.base, args.key, "POST", f"/scenarios/{scenario['id']}/load")
    run = call(args.base, args.key, "POST", "/runs",
               {"scenario_id": scenario["id"], "strategy": args.strategy},
               headers={"Idempotency-Key": f"measure-{time.time()}"})

    wall_start = time.monotonic()
    started = call(args.base, args.key, "POST", f"/runs/{run['id']}/start")
    states, wait_seconds, settled = wait_for_terminal(args.base, args.key, run["id"], args.timeout)
    wall_seconds = time.monotonic() - wall_start

    if args.chaos:
        # stop crashing before the checker runs, so a mid-check crash can't
        # be confused with a real violation
        call(args.base, args.key, "POST", "/chaos",
             {"crash_probability": 0.0, "partner_failure_rate": args.partner_failure})

    invariants = call(args.base, args.key, "POST", f"/runs/{run['id']}/invariants/check")
    metrics = call(args.base, args.key, "GET", f"/runs/{run['id']}/metrics")
    finops = call(args.base, args.key, "GET", f"/runs/{run['id']}/finops")

    result = {
        "label": label,
        "run_id": run["id"],
        "settled": settled,
        "disruption_events": started["disruption_events"],
        "cancelled_flights": started["cancelled_flights"],
        "delayed_flights": started["delayed_flights"],
        "disrupted_bookings": started["disrupted_bookings"],
        "sagas_by_state": states,
        "wall_seconds": round(wall_seconds, 1),
        "time_to_settle_seconds": round(wait_seconds, 1),
        "throughput_sagas_per_second": round(metrics["total_sagas"] / wall_seconds, 1) if wall_seconds else None,
        "metrics": metrics,
        "invariants_passed": invariants["passed"],
        "invariant_violations": invariants["total_violations"],
        "cost_per_1000": finops["cost_per_1000_recovered"],
        "cost_run": finops["cost_run"],
    }

    print(json.dumps(result, indent=2))
    if not settled:
        print("WARNING: run did not fully settle within the timeout", file=sys.stderr)
    return 0 if invariants["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
