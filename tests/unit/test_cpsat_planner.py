"""CP-SAT constraint tests (section 14): never oversell a cabin, never give
a booking two itineraries, and prefer recovering high-priority passengers
over shaving delay minutes."""

from datetime import UTC, datetime, timedelta

from reflight.planner.cpsat import _solve_chunk
from reflight.planner.greedy import BookingPlanInput

START = datetime(2026, 1, 1, tzinfo=UTC)


def _booking(booking_id: str, priority: int = 0) -> BookingPlanInput:
    return BookingPlanInput(
        booking_id=booking_id,
        airline_id="AL",
        origin="AAA",
        dest="BBB",
        preferred_cabin="ECONOMY",
        not_before=START,
        original_arrival=START + timedelta(hours=2),
        original_departure=START,
        priority=priority,
    )


def _option(flight_id: str, delay: float) -> dict:
    return {
        "segments": [{"seq": 0, "flight_id": flight_id, "cabin": "ECONOMY"}],
        "delay_minutes": delay,
    }


def test_never_exceeds_available_seats():
    inputs = [_booking(f"b{i}") for i in range(5)]
    options = {b.booking_id: [_option("F1", 30)] for b in inputs}
    snapshot = {("F1", "ECONOMY"): 2}

    assignments, status = _solve_chunk(inputs, options, snapshot, time_limit_s=5)

    assert status in {"OPTIMAL", "FEASIBLE"}
    assert len(assignments) == 2


def test_at_most_one_option_per_booking():
    inputs = [_booking("b1")]
    options = {"b1": [_option("F1", 10), _option("F2", 20), _option("F3", 5)]}
    snapshot = {("F1", "ECONOMY"): 5, ("F2", "ECONOMY"): 5, ("F3", "ECONOMY"): 5}

    assignments, _ = _solve_chunk(inputs, options, snapshot, time_limit_s=5)

    assert list(assignments) == ["b1"]
    assert assignments["b1"] == 2, "should take the lowest-delay option when capacity is free"


def test_priority_wins_over_delay_when_capacity_is_tight():
    minor = _booking("uvm", priority=100)  # unaccompanied minor
    regular = _booking("plain", priority=0)
    # the scarce seat is also the slower one, so a delay-only objective
    # would hand it to nobody in particular -- weight must decide.
    options = {"uvm": [_option("F1", 120)], "plain": [_option("F1", 120)]}
    snapshot = {("F1", "ECONOMY"): 1}

    assignments, _ = _solve_chunk([minor, regular], options, snapshot, time_limit_s=5)

    assert list(assignments) == ["uvm"]


def test_bookings_with_no_options_are_simply_unassigned():
    inputs = [_booking("b1"), _booking("b2")]
    options = {"b1": [], "b2": [_option("F1", 15)]}
    snapshot = {("F1", "ECONOMY"): 1}

    assignments, _ = _solve_chunk(inputs, options, snapshot, time_limit_s=5)

    assert "b1" not in assignments
    assert assignments["b2"] == 0


def test_multi_segment_option_consumes_a_seat_on_every_leg():
    inputs = [_booking("b1"), _booking("b2")]
    connecting = {
        "segments": [
            {"seq": 0, "flight_id": "F1", "cabin": "ECONOMY"},
            {"seq": 1, "flight_id": "F2", "cabin": "ECONOMY"},
        ],
        "delay_minutes": 60.0,
    }
    options = {"b1": [connecting], "b2": [connecting]}
    snapshot = {("F1", "ECONOMY"): 5, ("F2", "ECONOMY"): 1}  # second leg is the bottleneck

    assignments, _ = _solve_chunk(inputs, options, snapshot, time_limit_s=5)

    assert len(assignments) == 1
