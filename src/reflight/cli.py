import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="reflight")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="run Alembic migrations to head")
    sub.add_parser("api", help="run the FastAPI app")
    sub.add_parser("relay", help="run the outbox relay")
    sub.add_parser("worker", help="run a saga step worker")
    sub.add_parser("planner", help="run the planner consumer")
    sub.add_parser("partners", help="run the mock partners service")

    gen = sub.add_parser("generate-scenario", help="generate a synthetic scenario and store it")
    gen.add_argument("--preset", default="small", choices=["small", "storm", "mega"])
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--hub", default=None, help="IATA code to use as the storm hub")
    gen.add_argument("--severity", type=float, default=0.8)
    gen.add_argument("--cascade-chains", type=int, default=3)
    gen.add_argument("--out", default=None, help="local file to also write scenario JSON to")

    fin = sub.add_parser("finops", help="print the FinOps estimate for a run as Markdown")
    fin.add_argument("--run", required=True, help="run id")
    fin.add_argument("--profile", default=None, help="price profile from finops/prices.yaml")

    inv = sub.add_parser("invariants", help="run the invariant checker for a run")
    inv.add_argument("--run", required=True, help="run id")

    args = parser.parse_args()

    if args.command == "migrate":
        _run_migrate()
    elif args.command == "api":
        _run_api()
    elif args.command == "relay":
        _run_relay()
    elif args.command == "worker":
        _run_worker()
    elif args.command == "planner":
        _run_planner()
    elif args.command == "partners":
        _run_partners()
    elif args.command == "generate-scenario":
        _run_generate_scenario(args)
    elif args.command == "finops":
        _run_finops(args)
    elif args.command == "invariants":
        _run_invariants(args)
    else:
        parser.print_help()
        sys.exit(1)


def _run_migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


def _run_api() -> None:
    import os

    from reflight.core.telemetry import init_telemetry

    init_telemetry("api")

    import uvicorn

    from reflight.core.config import get_settings

    settings = get_settings()
    if settings.all_in_one:
        _run_migrate()
        _start_background_consumers()

    # Hosts like Render assign the listening port through $PORT.
    port = int(os.environ.get("PORT", settings.api_port))
    uvicorn.run("reflight.api.main:app", host="0.0.0.0", port=port)


def _start_background_consumers() -> None:
    """ALL_IN_ONE mode: run relay, planner and one worker as daemon threads
    beside the API, for single-instance hosts (e.g. Render's free tier).
    Each loop reconnects if its broker connection drops. Note a chaos crash
    (os._exit) takes the whole process down; the host restarts it and the
    outbox/idempotency machinery recovers exactly as with separate services."""
    import logging
    import threading
    import time

    from reflight.core.metrics import mark_worker_active
    from reflight.planner.main import run_forever as planner_forever
    from reflight.relay.main import run_forever as relay_forever
    from reflight.worker.main import run_forever as worker_forever

    log = logging.getLogger("reflight.all_in_one")
    mark_worker_active()

    def supervise(name: str, target) -> None:
        while True:
            try:
                target()
            except Exception:
                log.exception("%s stopped; restarting in 5s", name)
            time.sleep(5)

    for name, target in (("relay", relay_forever), ("planner", planner_forever), ("worker", worker_forever)):
        threading.Thread(target=supervise, args=(name, target), name=name, daemon=True).start()


def _run_relay() -> None:
    from reflight.core.telemetry import init_telemetry

    init_telemetry("relay")

    from reflight.relay.main import run_forever

    run_forever()


def _run_worker() -> None:
    from reflight.core.telemetry import init_telemetry

    init_telemetry("worker")

    from reflight.core.metrics import mark_worker_active
    from reflight.worker.main import run_forever

    mark_worker_active()
    run_forever()


def _run_planner() -> None:
    from reflight.core.telemetry import init_telemetry

    init_telemetry("planner")

    from reflight.planner.main import run_forever

    run_forever()


def _run_partners() -> None:
    from reflight.core.telemetry import init_telemetry

    init_telemetry("partners")

    import uvicorn

    from reflight.core.config import get_settings

    uvicorn.run("reflight.partners.main:app", host="0.0.0.0", port=get_settings().partners_port)


def _run_generate_scenario(args: argparse.Namespace) -> None:
    from reflight.simulator.generator import generate_and_store

    scenario_id = generate_and_store(
        preset=args.preset,
        seed=args.seed,
        hub=args.hub,
        severity=args.severity,
        cascade_chains=args.cascade_chains,
        local_out=args.out,
    )
    print(f"scenario stored: {scenario_id}")


def _run_finops(args: argparse.Namespace) -> None:
    from reflight.core.db import SessionLocal
    from reflight.finops.report import build_report, render_markdown

    db = SessionLocal()
    try:
        print(render_markdown(build_report(db, args.run, args.profile)))
    finally:
        db.close()


def _run_invariants(args: argparse.Namespace) -> None:
    import json

    from reflight.core.db import SessionLocal
    from reflight.invariants.checks import run_all_checks

    db = SessionLocal()
    try:
        report = run_all_checks(db, args.run)
    finally:
        db.close()

    for check_id, result in report["checks"].items():
        status = "PASS" if result["passed"] else f"FAIL ({len(result['violations'])})"
        print(f"{status:<12} {check_id}")
    print()
    print(json.dumps({"passed": report["passed"], "total_violations": report["total_violations"]}))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
