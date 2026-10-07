"""Reset the DB and bulk-load a scenario, so different runs (and
different planner strategies) start from identical conditions."""

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from reflight.core.models import (
    Airline,
    Airport,
    Booking,
    BookingSegment,
    Flight,
    Passenger,
    SeatInventory,
)
from reflight.core.storage import get_json

# `runs` is deliberately NOT in this list. Loading a scenario wipes the
# operational state so every run starts from identical conditions, but the
# run *records* survive -- otherwise loading a scenario for the CP-SAT run
# would delete the greedy run you wanted to compare it against. A run's
# sagas do get wiped, which is why the relay snapshots each run's final
# metrics into runs.metrics_json the moment it settles (see
# relay/main.py::_finish_settled_runs).
_RESET_TABLES = [
    "outbox",
    "processed_messages",
    "dead_letters",
    "seat_holds",
    "saga_events",
    "sagas",
    "disruption_events",
    "booking_segments",
    "bookings",
    "seat_inventory",
    "flights",
    "passengers",
    "airports",
    "airlines",
]


def reset_operational_tables(db: Session) -> None:
    tables = ", ".join(_RESET_TABLES)
    db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def load_scenario(db: Session, scenario_row) -> dict[str, Any]:
    scenario = get_json(scenario_row.minio_key)

    reset_operational_tables(db)

    db.bulk_insert_mappings(Airline, scenario["airlines"])
    db.bulk_insert_mappings(Airport, scenario["airports"])

    flights = []
    for f in scenario["flights"]:
        row = dict(f)
        for k in ("dep_at", "arr_at", "sched_dep_at", "sched_arr_at"):
            row[k] = _parse_dt(row[k])
        flights.append(row)
    db.bulk_insert_mappings(Flight, flights)

    db.bulk_insert_mappings(SeatInventory, scenario["seat_inventory"])
    db.bulk_insert_mappings(Passenger, scenario["passengers"])
    db.bulk_insert_mappings(Booking, scenario["bookings"])
    db.bulk_insert_mappings(BookingSegment, scenario["booking_segments"])

    return {
        "airports": len(scenario["airports"]),
        "airlines": len(scenario["airlines"]),
        "flights": len(scenario["flights"]),
        "passengers": len(scenario["passengers"]),
        "bookings": len(scenario["bookings"]),
        "timeline_events": len(scenario["timeline"]),
    }
