"""F2b: a late aircraft drags its own downstream rotation with it
(section 14's "cascading-delay propagation logic" unit test)."""

import random
from datetime import UTC, datetime, timedelta

from reflight.simulator.disruptions import (
    CASCADE_CANCEL_THRESHOLD_MINUTES,
    TURNAROUND_BUFFER_MINUTES,
    cascading_delay_events,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def _rotation(tail: str, n: int, other_tails: int = 0) -> list[dict]:
    flights = [
        {
            "id": f"{tail}-{i}",
            "tail_number": tail,
            "origin": f"AP{i}",
            "sched_dep_at": START + timedelta(hours=2 * i),
        }
        for i in range(n)
    ]
    for t in range(other_tails):
        flights.append(
            {
                "id": f"OTHER{t}",
                "tail_number": f"OTHER{t}",
                "origin": "APX",
                "sched_dep_at": START,
            }
        )
    return flights


def test_delay_propagates_down_the_same_tail_only():
    rng = random.Random(1)
    flights = _rotation("TAIL-1", 8, other_tails=3)

    events = cascading_delay_events(rng, flights, set(), n_chains=1)

    assert len(events) >= 4, "expected a chain of at least 4 affected legs"
    assert {e["target_flight_id"].split("-")[0] for e in events} == {"TAIL"}
    assert all(e["tail_number"] == "TAIL-1" for e in events)


def test_root_is_a_delay_and_downstream_is_cascade():
    rng = random.Random(2)
    events = cascading_delay_events(rng, _rotation("TAIL-1", 8), set(), n_chains=1)

    root, *downstream = events
    assert root["type"] == "DELAY"
    assert root["cause"] == "AOG"
    assert all(e["cause"] == "CASCADE" for e in downstream)


def test_delay_decays_by_the_turnaround_buffer_each_leg():
    rng = random.Random(3)
    events = cascading_delay_events(rng, _rotation("TAIL-1", 12), set(), n_chains=1)

    delays = [e["delay_minutes"] for e in events if e["delay_minutes"] is not None]
    for earlier, later in zip(delays, delays[1:], strict=False):
        assert later == earlier - TURNAROUND_BUFFER_MINUTES


def test_legs_past_the_threshold_are_cancelled_not_delayed():
    rng = random.Random(4)
    events = cascading_delay_events(rng, _rotation("TAIL-1", 12), set(), n_chains=1)

    for event in events[1:]:
        if event["type"] == "CANCELLATION":
            assert event["delay_minutes"] is None
        else:
            assert event["delay_minutes"] < CASCADE_CANCEL_THRESHOLD_MINUTES


def test_already_cancelled_flights_are_not_part_of_a_rotation():
    rng = random.Random(5)
    flights = _rotation("TAIL-1", 8)
    dead = {"TAIL-1-0", "TAIL-1-1"}

    events = cascading_delay_events(rng, flights, dead, n_chains=1)

    assert not dead & {e["target_flight_id"] for e in events}
