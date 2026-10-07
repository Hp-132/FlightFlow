"""Seeded synthetic network generator (F1) + P0 disruption timeline (F2, F2a).

Everything is driven by one random.Random(seed), so the same
(preset, seed, hub, severity) always produces byte-identical output --
verified by comparing `content_hash` across two runs (see tests).
"""

import hashlib
import json
import random
import string
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from reflight.core.constants import TIER_GOLD, TIER_NONE, TIER_SILVER
from reflight.simulator.disruptions import (
    airport_closed_events,
    cascading_delay_events,
    random_cancellation_events,
)
from reflight.simulator.presets import get_preset

SCHEDULE_START = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
CABINS = [("ECONOMY", 150), ("BUSINESS", 20)]
TIER_WEIGHTS = [(TIER_NONE, 0.70), (TIER_SILVER, 0.20), (TIER_GOLD, 0.10)]
MIN_CONNECTION_MINUTES = 45


def _det_uuid(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def _weighted_choice(rng: random.Random, weighted: list[tuple[str, float]]) -> str:
    total = sum(w for _, w in weighted)
    x = rng.uniform(0, total)
    upto = 0.0
    for value, w in weighted:
        upto += w
        if x <= upto:
            return value
    return weighted[-1][0]


def _gen_airports(rng: random.Random, n: int, n_hubs: int) -> list[dict[str, Any]]:
    used_codes: set[str] = set()
    airports = []
    hub_indices = set(rng.sample(range(n), n_hubs))
    for i in range(n):
        while True:
            code = "".join(rng.choices(string.ascii_uppercase, k=3))
            if code not in used_codes:
                used_codes.add(code)
                break
        airports.append(
            {
                "id": _det_uuid(rng),
                "iata": code,
                "name": f"{code} International",
                "lat": round(rng.uniform(-60.0, 70.0), 4),
                "lon": round(rng.uniform(-180.0, 180.0), 4),
                "is_hub": i in hub_indices,
            }
        )
    return airports


def _gen_airlines(rng: random.Random, n: int) -> list[dict[str, Any]]:
    used_codes: set[str] = set()
    airlines = []
    for _ in range(n):
        while True:
            code = "".join(rng.choices(string.ascii_uppercase, k=2))
            if code not in used_codes:
                used_codes.add(code)
                break
        airlines.append({"id": _det_uuid(rng), "code": code, "name": f"{code} Airways"})
    return airlines


def _gen_flights(
    rng: random.Random, airline: dict[str, Any], airports: list[dict[str, Any]], count: int
) -> list[dict[str, Any]]:
    flights = []
    n_tails = max(3, count // 6)
    tails = [f"{airline['code']}-{i:03d}" for i in range(n_tails)]
    for i in range(count):
        origin, dest = rng.sample(airports, 2)
        dep_offset_min = rng.uniform(0, 24 * 60)
        duration_min = rng.uniform(45, 240)
        sched_dep = SCHEDULE_START + timedelta(minutes=dep_offset_min)
        sched_arr = sched_dep + timedelta(minutes=duration_min)
        flights.append(
            {
                "id": _det_uuid(rng),
                "airline_id": airline["id"],
                "flight_no": f"{airline['code']}{100 + i}",
                "tail_number": rng.choice(tails),
                "origin": origin["id"],
                "dest": dest["id"],
                "dep_at": sched_dep,
                "arr_at": sched_arr,
                "sched_dep_at": sched_dep,
                "sched_arr_at": sched_arr,
                "status": "SCHEDULED",
            }
        )
    return flights


def _gen_seat_inventory(flights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    inventory = []
    for f in flights:
        for cabin, capacity in CABINS:
            inventory.append(
                {
                    "flight_id": f["id"],
                    "cabin": cabin,
                    "capacity": capacity,
                    "available": capacity,
                    "sold_other": 0,
                }
            )
    return inventory


def _gen_passengers_and_bookings(
    rng: random.Random,
    airlines: list[dict[str, Any]],
    flights_by_airline: dict[str, list[dict[str, Any]]],
    flights_by_airline_origin: dict[str, dict[str, list[dict[str, Any]]]],
    seat_remaining: dict[tuple[str, str], int],
    total_passengers: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    passengers = []
    bookings = []
    segments = []
    used_pnrs: set[str] = set()

    per_airline = max(1, total_passengers // len(airlines))
    for airline in airlines:
        candidate_flights = flights_by_airline[airline["id"]]
        if not candidate_flights:
            continue
        for _ in range(per_airline):
            passenger_id = _det_uuid(rng)
            tier = _weighted_choice(rng, TIER_WEIGHTS)
            passengers.append(
                {
                    "id": passenger_id,
                    "airline_id": airline["id"],
                    "name": f"Passenger {len(passengers) + 1}",
                    "tier": tier,
                    "is_unaccompanied_minor": rng.random() < 0.02,
                    "bags": rng.randint(0, 2),
                }
            )

            booking_segments = _pick_itinerary(
                rng, candidate_flights, flights_by_airline_origin[airline["id"]], seat_remaining
            )
            if not booking_segments:
                continue

            while True:
                pnr = "".join(rng.choices(string.ascii_uppercase + string.digits, k=6))
                if pnr not in used_pnrs:
                    used_pnrs.add(pnr)
                    break

            booking_id = _det_uuid(rng)
            bookings.append({"id": booking_id, "passenger_id": passenger_id, "pnr": pnr, "status": "ACTIVE"})
            for seq, (flight, cabin) in enumerate(booking_segments):
                segments.append(
                    {"booking_id": booking_id, "seq": seq, "flight_id": flight["id"], "cabin": cabin}
                )

    return passengers, bookings, segments


def _pick_itinerary(
    rng: random.Random,
    candidate_flights: list[dict[str, Any]],
    flights_by_origin: dict[str, list[dict[str, Any]]],
    seat_remaining: dict[tuple[str, str], int],
) -> list[tuple[dict[str, Any], str]]:
    def pick_cabin_with_room(flight: dict[str, Any]) -> str | None:
        weighted = [("ECONOMY", 0.9), ("BUSINESS", 0.1)]
        cabin = _weighted_choice(rng, weighted)
        order = [cabin] + [c for c, _ in CABINS if c != cabin]
        for c in order:
            if seat_remaining.get((flight["id"], c), 0) > 0:
                return c
        return None

    for _ in range(8):
        first = rng.choice(candidate_flights)
        cabin1 = pick_cabin_with_room(first)
        if cabin1 is None:
            continue

        if rng.random() < 0.25:
            next_options = [
                f
                for f in flights_by_origin.get(first["dest"], [])
                if f["sched_dep_at"] >= first["sched_arr_at"] + timedelta(minutes=MIN_CONNECTION_MINUTES)
            ]
            if next_options:
                second = rng.choice(next_options)
                cabin2 = pick_cabin_with_room(second)
                if cabin2 is not None:
                    seat_remaining[(first["id"], cabin1)] -= 1
                    seat_remaining[(second["id"], cabin2)] -= 1
                    return [(first, cabin1), (second, cabin2)]

        seat_remaining[(first["id"], cabin1)] -= 1
        return [(first, cabin1)]

    return []


def build_scenario(
    preset_name: str,
    seed: int,
    hub_iata: str | None,
    severity: float,
    cascade_chains: int = 3,
) -> dict[str, Any]:
    preset = get_preset(preset_name)
    rng = random.Random(seed)

    airports = _gen_airports(rng, preset.num_airports, preset.num_hubs)
    airlines = _gen_airlines(rng, preset.num_airlines)

    all_flights: list[dict[str, Any]] = []
    flights_by_airline: dict[str, list[dict[str, Any]]] = {}
    flights_by_airline_origin: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for airline in airlines:
        flights = _gen_flights(rng, airline, airports, preset.flights_per_airline_per_day)
        all_flights.extend(flights)
        flights_by_airline[airline["id"]] = flights
        by_origin: dict[str, list[dict[str, Any]]] = {}
        for f in flights:
            by_origin.setdefault(f["origin"], []).append(f)
        flights_by_airline_origin[airline["id"]] = by_origin

    seat_inventory = _gen_seat_inventory(all_flights)
    seat_remaining = {(row["flight_id"], row["cabin"]): row["available"] for row in seat_inventory}

    passengers, bookings, segments = _gen_passengers_and_bookings(
        rng, airlines, flights_by_airline, flights_by_airline_origin, seat_remaining, preset.num_passengers
    )
    for row in seat_inventory:
        row["available"] = seat_remaining[(row["flight_id"], row["cabin"])]

    hub_airports = [a for a in airports if a["is_hub"]]
    chosen_hub = next((a for a in hub_airports if a["iata"] == hub_iata), None) or hub_airports[0]

    storm_start = SCHEDULE_START + timedelta(minutes=rng.uniform(4 * 60, 18 * 60))
    weather_events = airport_closed_events(rng, all_flights, chosen_hub["id"], storm_start, severity)
    cancelled_ids = {e["target_flight_id"] for e in weather_events}
    background_events = random_cancellation_events(rng, all_flights, cancelled_ids)
    cancelled_ids |= {e["target_flight_id"] for e in background_events}
    cascade_events = cascading_delay_events(rng, all_flights, cancelled_ids, n_chains=cascade_chains)

    timeline = sorted(
        weather_events + background_events + cascade_events, key=lambda e: e["occurred_at"]
    )

    scenario = {
        "preset": preset_name,
        "seed": seed,
        "storm_hub_iata": chosen_hub["iata"],
        "storm_start": storm_start.isoformat(),
        "severity": severity,
        "cascade_chains": cascade_chains,
        "schedule_start": SCHEDULE_START.isoformat(),
        "airports": airports,
        "airlines": airlines,
        "flights": [_serialize_flight(f) for f in all_flights],
        "seat_inventory": seat_inventory,
        "passengers": passengers,
        "bookings": bookings,
        "booking_segments": segments,
        "timeline": [_serialize_event(e) for e in timeline],
    }
    scenario["content_hash"] = _hash_scenario(scenario)
    return scenario


def _serialize_flight(f: dict[str, Any]) -> dict[str, Any]:
    out = dict(f)
    for k in ("dep_at", "arr_at", "sched_dep_at", "sched_arr_at"):
        out[k] = out[k].isoformat()
    return out


def _serialize_event(e: dict[str, Any]) -> dict[str, Any]:
    out = dict(e)
    out["occurred_at"] = out["occurred_at"].isoformat()
    return out


def _hash_scenario(scenario: dict[str, Any]) -> str:
    payload = {k: v for k, v in scenario.items() if k != "content_hash"}
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def generate_and_store(
    preset: str,
    seed: int,
    hub: str | None = None,
    severity: float = 0.8,
    cascade_chains: int = 3,
    local_out: str | None = None,
) -> str:
    """Build a scenario, store it in MinIO, register it in Postgres, and
    return the new scenario id. Used by both the CLI and the API."""
    from reflight.core.db import session_scope
    from reflight.core.models import Scenario
    from reflight.core.storage import put_json

    scenario = build_scenario(preset, seed, hub, severity, cascade_chains)
    params = {"preset": preset, "hub": hub, "severity": severity, "cascade_chains": cascade_chains}

    with session_scope() as db:
        row = Scenario(seed=seed, params_json=params, minio_key="")
        db.add(row)
        db.flush()
        minio_key = f"scenarios/{row.id}.json"
        row.minio_key = minio_key
        scenario_id = row.id

    put_json(minio_key, scenario)

    if local_out:
        with open(local_out, "w", encoding="utf-8") as fh:
            json.dump(scenario, fh, indent=2)

    return scenario_id
