#!/usr/bin/env python3
"""Ready-made demo runs for FlightFlow, built on the existing presets.

Each case drives the normal API exactly like the dashboard's Start button
(generate -> load -> create run -> start), waits until every saga is
terminal, runs the six invariant checks, and leaves chaos/fairness back at
their defaults afterwards. Nothing here changes the simulation itself.

    python scripts/demo_cases.py list
    python scripts/demo_cases.py run small-baseline --base https://<host> --key <API key>
    python scripts/demo_cases.py run all --base http://localhost:8000      (local stack)

Runs are sequential by design: loading a scenario resets the operational
tables, so never start a case while another one is still in flight.

Sizes below were computed from the generator with these exact settings;
"disrupted" is the number of sagas the run will create.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

TERMINAL = {"COMPLETED", "COMPENSATED", "FAILED_NO_CAPACITY", "NEEDS_MANUAL"}
DEFAULT_FAIRNESS_CAP = 8

# crash: worker crash probability for a local Docker Compose stack, where
# workers are separate containers. crash_hosted: the value used against any
# non-local host -- in single-container (ALL_IN_ONE) hosting a crash restarts
# the whole service, website included, so it must stay low.
CASES = {
    "small-baseline": dict(
        n=1, title="Small normal recovery", preset="small", seed=42, severity=0.6, cascade=0,
        strategy="greedy", disrupted=13,
    ),
    "medium-greedy": dict(
        n=2, title="Medium disruption (Greedy)", preset="small", seed=2024, severity=0.8, cascade=3,
        strategy="greedy", disrupted=49,
    ),
    "large-greedy": dict(
        n=3, title="Large disruption (Greedy)", preset="small", seed=101, severity=1.0, cascade=10,
        strategy="greedy", disrupted=160,
    ),
    "small-cpsat": dict(
        n=4, title="Small CP-SAT optimisation (pair with case 1)", preset="small", seed=42,
        severity=0.6, cascade=0, strategy="cpsat", disrupted=13,
    ),
    "medium-cpsat": dict(
        n=5, title="Medium CP-SAT optimisation (pair with case 2)", preset="small", seed=2024,
        severity=0.8, cascade=3, strategy="cpsat", disrupted=49,
    ),
    "worker-chaos-20": dict(
        n=6, title="Worker chaos ~20%", preset="small", seed=42, severity=0.6, cascade=0,
        strategy="greedy", disrupted=13, crash=0.2, crash_hosted=0.03,
    ),
    "worker-chaos-30": dict(
        n=7, title="Heavy worker chaos ~30%", preset="small", seed=42, severity=0.6, cascade=0,
        strategy="greedy", disrupted=13, crash=0.3, crash_hosted=0.05,
    ),
    "partner-failure": dict(
        n=8, title="Partner/API failure: retries + compensation", preset="small", seed=7,
        severity=0.8, cascade=3, strategy="greedy", disrupted=19, partner_failure=0.5,
    ),
    "seat-contention": dict(
        n=9, title="High contention + per-airline fairness cap of 1", preset="small", seed=2024,
        severity=1.0, cascade=10, strategy="greedy", disrupted=102, fairness_cap=1,
    ),
}


def is_local(base: str) -> bool:
    return urlparse(base).hostname in {"localhost", "127.0.0.1", "::1"}


def call(base, key, method, path, body=None, headers=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{base}{path}", data=data, method=method)
    req.add_header("X-API-Key", key)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        sys.exit(f"{method} {path} failed: {exc.code} {exc.read().decode()[:300]}")


def call_retrying(base, key, method, path, body=None, attempts=30):
    """For polling during chaos runs, when the service may be restarting."""
    for _ in range(attempts):
        try:
            return call(base, key, method, path, body, timeout=30)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(5)
    sys.exit(f"{method} {path}: service did not come back")


def run_case(name, base, key, timeout):
    c = CASES[name]
    crash = c.get("crash", 0.0)
    if crash and not is_local(base):
        crash = c["crash_hosted"]
        print(f"   hosted target: using crash probability {crash} instead of {c['crash']}", file=sys.stderr)
    partner = c.get("partner_failure", 0.0)

    print(f"==> case {c['n']}: {c['title']}  (~{c['disrupted']} disrupted bookings)", file=sys.stderr)
    call(base, key, "POST", "/chaos", {"crash_probability": crash, "partner_failure_rate": partner})
    call(base, key, "POST", "/fairness", {"default_cap": c.get("fairness_cap", DEFAULT_FAIRNESS_CAP)})

    scenario = call(base, key, "POST", "/scenarios", {
        "preset": c["preset"], "seed": c["seed"], "severity": c["severity"], "cascade_chains": c["cascade"],
    })
    call(base, key, "POST", f"/scenarios/{scenario['id']}/load")
    run = call(base, key, "POST", "/runs", {"scenario_id": scenario["id"], "strategy": c["strategy"]},
               headers={"Idempotency-Key": f"demo-{name}-{time.time()}"})
    started = call(base, key, "POST", f"/runs/{run['id']}/start")
    print(f"   run {run['id']}: {started['disrupted_bookings']} bookings disrupted; waiting…", file=sys.stderr)

    t0, states, settled = time.monotonic(), {}, False
    while time.monotonic() - t0 < timeout:
        states = call_retrying(base, key, "GET", f"/runs/{run['id']}")["sagas_by_state"]
        if states and all(s in TERMINAL for s in states):
            settled = True
            break
        time.sleep(3)

    # Back to defaults *before* checking, so a crash can't interrupt the checker.
    call_retrying(base, key, "POST", "/chaos", {"crash_probability": 0.0, "partner_failure_rate": 0.0})
    call_retrying(base, key, "POST", "/fairness", {"default_cap": DEFAULT_FAIRNESS_CAP})

    inv = call_retrying(base, key, "POST", f"/runs/{run['id']}/invariants/check")
    m = call_retrying(base, key, "GET", f"/runs/{run['id']}/metrics")
    print(json.dumps({
        "case": name, "run_id": run["id"], "settled": settled,
        "seconds": round(time.monotonic() - t0, 1),
        "sagas_by_state": states,
        "recovered": f"{m['recovered']}/{m['total_sagas']} ({m['recovered_pct']}%)",
        "avg_delay_minutes": m["avg_delay_minutes"],
        "planner_cpu_seconds": m["planner_cpu_seconds"],
        "seat_conflicts": m["seat_conflicts"],
        "invariants": "PASS" if inv["passed"] else f"FAIL ({inv['total_violations']} violations)",
    }, indent=2))
    if not settled:
        print("WARNING: did not fully settle within the timeout", file=sys.stderr)
    return inv["passed"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("case", choices=[*CASES, "all"])
    r.add_argument("--base", default="http://localhost:8000")
    r.add_argument("--key", default="dev-local-key-change-me")
    r.add_argument("--timeout", type=float, default=900)
    args = ap.parse_args()

    if args.cmd == "list":
        for name, c in CASES.items():
            extra = []
            if c.get("crash"):
                extra.append(f"crash {c['crash']} local / {c['crash_hosted']} hosted")
            if c.get("partner_failure"):
                extra.append(f"partner failure {c['partner_failure']}")
            if c.get("fairness_cap"):
                extra.append(f"fairness cap {c['fairness_cap']}")
            print(f"{c['n']}. {name:16} {c['preset']}/seed {c['seed']}/sev {c['severity']}/knock-on {c['cascade']}"
                  f"/{c['strategy']:6} ~{c['disrupted']:>3} disrupted  {'; '.join(extra)}")
        return 0

    names = list(CASES) if args.case == "all" else [args.case]
    ok = all([run_case(n, args.base, args.key, args.timeout) for n in names])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
