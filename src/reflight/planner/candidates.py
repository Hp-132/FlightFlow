"""Shared candidate-itinerary generation (section 8): both the greedy
planner and (in a later phase) CP-SAT consume the same candidates, so
results are comparable.

Up to 5 alternatives per booking: same origin/destination as the original
itinerary, direct or one stop, minimum 45-minute connection, departing no
earlier than the disruption and within 48h of it.
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from reflight.core.constants import FLIGHT_CANCELLED
from reflight.core.models import Flight

MAX_OPTIONS = 5
MIN_CONNECTION_MINUTES = 45
REBOOKING_WINDOW_HOURS = 48


class AirlineFlightCache:
    """Caches an airline's non-cancelled flights (and an origin index) for
    the lifetime of one planning batch, so candidate generation doesn't
    re-query the DB per booking."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._flights_by_airline: dict[str, list[dict[str, Any]]] = {}
        self._by_origin: dict[str, dict[str, list[dict[str, Any]]]] = {}

    def get(self, airline_id: str) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        if airline_id not in self._flights_by_airline:
            rows = self._db.execute(
                select(Flight).where(Flight.airline_id == airline_id, Flight.status != FLIGHT_CANCELLED)
            ).scalars().all()
            flights = [
                {
                    "id": f.id,
                    "origin": f.origin,
                    "dest": f.dest,
                    "sched_dep_at": f.sched_dep_at,
                    "sched_arr_at": f.sched_arr_at,
                }
                for f in rows
            ]
            by_origin: dict[str, list[dict[str, Any]]] = {}
            for f in flights:
                by_origin.setdefault(f["origin"], []).append(f)
            self._flights_by_airline[airline_id] = flights
            self._by_origin[airline_id] = by_origin
        return self._flights_by_airline[airline_id], self._by_origin[airline_id]


def _available(inventory_snapshot: dict[tuple[str, str], int], flight_id: str, cabin: str) -> int:
    return inventory_snapshot.get((flight_id, cabin), 0)


def generate_candidates(
    cache: AirlineFlightCache,
    airline_id: str,
    origin_airport_id: str,
    dest_airport_id: str,
    preferred_cabin: str,
    not_before: datetime,
    original_arrival: datetime,
    inventory_snapshot: dict[tuple[str, str], int],
) -> list[dict[str, Any]]:
    _, by_origin = cache.get(airline_id)
    window_end = not_before + timedelta(hours=REBOOKING_WINDOW_HOURS)
    cabins_to_try = [preferred_cabin] + [c for c in ("ECONOMY", "BUSINESS") if c != preferred_cabin]

    candidates: list[dict[str, Any]] = []

    for f in by_origin.get(origin_airport_id, []):
        if f["dest"] != dest_airport_id:
            continue
        if not (not_before <= f["sched_dep_at"] <= window_end):
            continue
        cabin = next((c for c in cabins_to_try if _available(inventory_snapshot, f["id"], c) > 0), None)
        if cabin is None:
            continue
        delay = round(max(0.0, (f["sched_arr_at"] - original_arrival).total_seconds() / 60), 1)
        candidates.append(
            {
                "segments": [{"seq": 0, "flight_id": f["id"], "cabin": cabin}],
                "delay_minutes": delay,
            }
        )

    for f1 in by_origin.get(origin_airport_id, []):
        if not (not_before <= f1["sched_dep_at"] <= window_end):
            continue
        cabin1 = next((c for c in cabins_to_try if _available(inventory_snapshot, f1["id"], c) > 0), None)
        if cabin1 is None:
            continue
        min_connect = f1["sched_arr_at"] + timedelta(minutes=MIN_CONNECTION_MINUTES)
        for f2 in by_origin.get(f1["dest"], []):
            if f2["dest"] != dest_airport_id:
                continue
            if f2["sched_dep_at"] < min_connect or f2["sched_dep_at"] > window_end:
                continue
            cabin2 = next((c for c in cabins_to_try if _available(inventory_snapshot, f2["id"], c) > 0), None)
            if cabin2 is None:
                continue
            delay = round(max(0.0, (f2["sched_arr_at"] - original_arrival).total_seconds() / 60), 1)
            candidates.append(
                {
                    "segments": [
                        {"seq": 0, "flight_id": f1["id"], "cabin": cabin1},
                        {"seq": 1, "flight_id": f2["id"], "cabin": cabin2},
                    ],
                    "delay_minutes": delay,
                }
            )

    candidates.sort(key=lambda c: (len(c["segments"]), c["delay_minutes"]))
    return candidates[:MAX_OPTIONS]
