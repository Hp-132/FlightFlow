"""Pure functions that compute disruption timelines from a generated
network: the storm (F2), background AOG/CREW noise (F2a) and cascading
aircraft delays down a tail number's rotation (F2b).
"""

import random
from datetime import timedelta
from typing import Any

from reflight.core.constants import (
    CAUSE_AOG,
    CAUSE_CASCADE,
    CAUSE_CREW,
    CAUSE_WEATHER,
    EVENT_CANCELLATION,
    EVENT_DELAY,
)

STORM_WINDOW_MINUTES = 240
BACKGROUND_CANCELLATION_RATE = 0.015  # share of non-storm flights

# F2b cascading delay
TURNAROUND_BUFFER_MINUTES = 25
CASCADE_CANCEL_THRESHOLD_MINUTES = 180
MIN_ROTATION_FLIGHTS = 4
ROOT_DELAY_RANGE_MINUTES = (150, 300)


def airport_closed_events(
    rng: random.Random,
    flights: list[dict[str, Any]],
    hub_airport_id: str,
    storm_start: Any,
    severity: float,
) -> list[dict[str, Any]]:
    """Cancel `severity` share of the hub's departures within the storm
    window. cause = WEATHER."""
    window_end = storm_start + timedelta(minutes=STORM_WINDOW_MINUTES)
    candidates = [
        f
        for f in flights
        if f["origin"] == hub_airport_id and storm_start <= f["sched_dep_at"] < window_end
    ]
    n_cancel = round(len(candidates) * severity)
    chosen = rng.sample(candidates, n_cancel) if n_cancel <= len(candidates) else candidates

    events = []
    for f in chosen:
        occurred_at = storm_start + timedelta(minutes=rng.uniform(0, STORM_WINDOW_MINUTES))
        events.append(
            {
                "type": EVENT_CANCELLATION,
                "cause": CAUSE_WEATHER,
                "target_flight_id": f["id"],
                "target_airport_id": hub_airport_id,
                "delay_minutes": None,
                "occurred_at": occurred_at,
            }
        )
    return events


def random_cancellation_events(
    rng: random.Random,
    flights: list[dict[str, Any]],
    already_cancelled_ids: set[str],
    rate: float = BACKGROUND_CANCELLATION_RATE,
) -> list[dict[str, Any]]:
    """Small background Poisson-ish rate of AOG/CREW cancellations,
    independent of the storm, so not every disrupted booking traces back
    to it."""
    eligible = [f for f in flights if f["id"] not in already_cancelled_ids]
    n_cancel = round(len(eligible) * rate)
    chosen = rng.sample(eligible, min(n_cancel, len(eligible)))

    events = []
    for f in chosen:
        cause = rng.choice([CAUSE_AOG, CAUSE_CREW])
        lead_minutes = rng.uniform(15, 180)
        occurred_at = f["sched_dep_at"] - timedelta(minutes=lead_minutes)
        events.append(
            {
                "type": EVENT_CANCELLATION,
                "cause": cause,
                "target_flight_id": f["id"],
                "target_airport_id": f["origin"],
                "delay_minutes": None,
                "occurred_at": occurred_at,
            }
        )
    return events


def cascading_delay_events(
    rng: random.Random,
    flights: list[dict[str, Any]],
    already_cancelled_ids: set[str],
    n_chains: int = 3,
) -> list[dict[str, Any]]:
    """F2b: one aircraft runs late, and the lateness walks down that tail
    number's remaining rotation.

    The root flight is an AOG delay. Each later flight on the same tail
    inherits ``max(0, inherited - TURNAROUND_BUFFER_MINUTES)`` -- schedule
    slack absorbs a little lateness at every turn -- and is emitted with
    cause CASCADE. A leg whose inherited delay is still at or beyond
    CASCADE_CANCEL_THRESHOLD_MINUTES can't realistically operate, so it is
    cancelled instead of delayed; propagation continues past it because the
    aircraft is still out of position.
    """
    by_tail: dict[str, list[dict[str, Any]]] = {}
    for f in flights:
        if f["id"] in already_cancelled_ids:
            continue
        by_tail.setdefault(f["tail_number"], []).append(f)

    eligible = sorted(tail for tail, fl in by_tail.items() if len(fl) >= MIN_ROTATION_FLIGHTS)
    if not eligible:
        return []

    events: list[dict[str, Any]] = []
    for tail in rng.sample(eligible, min(n_chains, len(eligible))):
        rotation = sorted(by_tail[tail], key=lambda f: f["sched_dep_at"])
        last_start = len(rotation) - MIN_ROTATION_FLIGHTS
        start_idx = rng.randint(0, last_start) if last_start > 0 else 0

        root = rotation[start_idx]
        delay = float(rng.randint(*ROOT_DELAY_RANGE_MINUTES))
        events.append(
            {
                "type": EVENT_DELAY,
                "cause": CAUSE_AOG,
                "target_flight_id": root["id"],
                "target_airport_id": root["origin"],
                "delay_minutes": int(delay),
                "occurred_at": root["sched_dep_at"],
                "tail_number": tail,
            }
        )

        for leg in rotation[start_idx + 1 :]:
            delay = max(0.0, delay - TURNAROUND_BUFFER_MINUTES)
            if delay <= 0:
                break
            cancelled = delay >= CASCADE_CANCEL_THRESHOLD_MINUTES
            events.append(
                {
                    "type": EVENT_CANCELLATION if cancelled else EVENT_DELAY,
                    "cause": CAUSE_CASCADE,
                    "target_flight_id": leg["id"],
                    "target_airport_id": leg["origin"],
                    "delay_minutes": None if cancelled else int(delay),
                    "occurred_at": leg["sched_dep_at"],
                    "tail_number": tail,
                }
            )

    return events
