"""CP-SAT batch planner (F7, section 8).

Same interface and same candidate itineraries as the greedy planner, so the
two are directly comparable: `plan(booking_ids, inventory_snapshot) ->
assignments`. The difference is that greedy commits to the best option for
each booking in priority order, while CP-SAT optimises the whole batch at
once against the seat constraints.

    maximise  sum over b,o of  x[b,o] * (W * weight_b - delay_minutes[b,o])
    s.t.      sum over o of x[b,o] <= 1                      (one itinerary per booking)
              sum of x[b,o] using (flight, cabin) <= available   (no oversell)

W is large enough (10_000) that recovering one more weighted passenger
always beats any achievable delay saving -- the longest candidate delay is
bounded by the 48h rebooking window, i.e. 2880 minutes.
"""

import logging
from typing import Any

from ortools.sat.python import cp_model
from sqlalchemy.orm import Session

from reflight.planner.candidates import AirlineFlightCache, generate_candidates
from reflight.planner.greedy import BookingPlanInput, PlanResult, load_plan_inputs

log = logging.getLogger("reflight.planner.cpsat")

CHUNK_SIZE = 500
TIME_LIMIT_SECONDS = 10.0
RECOVERY_WEIGHT = 10_000


def _candidates_for(
    cache: AirlineFlightCache, b: BookingPlanInput, snapshot: dict[tuple[str, str], int]
) -> list[dict[str, Any]]:
    return generate_candidates(
        cache,
        b.airline_id,
        b.origin,
        b.dest,
        b.preferred_cabin,
        b.not_before,
        b.original_arrival,
        snapshot,
    )


def _greedy_hint(
    inputs: list[BookingPlanInput],
    options: dict[str, list[dict[str, Any]]],
    snapshot: dict[tuple[str, str], int],
) -> dict[str, int]:
    """Run the greedy rule over the same option lists to seed the solver."""
    remaining = dict(snapshot)
    chosen: dict[str, int] = {}
    for b in sorted(inputs, key=lambda x: (-x.priority, x.original_departure)):
        for idx, option in enumerate(options[b.booking_id]):
            if all(remaining.get((s["flight_id"], s["cabin"]), 0) > 0 for s in option["segments"]):
                for s in option["segments"]:
                    key = (s["flight_id"], s["cabin"])
                    remaining[key] = remaining.get(key, 0) - 1
                chosen[b.booking_id] = idx
                break
    return chosen


def _solve_chunk(
    inputs: list[BookingPlanInput],
    options: dict[str, list[dict[str, Any]]],
    snapshot: dict[tuple[str, str], int],
    time_limit_s: float,
) -> tuple[dict[str, int], str]:
    model = cp_model.CpModel()
    x: dict[tuple[str, int], Any] = {}
    seat_usage: dict[tuple[str, str], list[Any]] = {}
    objective_terms = []

    for b in inputs:
        booking_options = options[b.booking_id]
        if not booking_options:
            continue
        weight = b.priority + 1
        vars_for_booking = []
        for idx, option in enumerate(booking_options):
            var = model.NewBoolVar(f"x_{b.booking_id}_{idx}")
            x[(b.booking_id, idx)] = var
            vars_for_booking.append(var)
            for seg in option["segments"]:
                seat_usage.setdefault((seg["flight_id"], seg["cabin"]), []).append(var)
            objective_terms.append(var * (RECOVERY_WEIGHT * weight - int(option["delay_minutes"])))
        model.AddAtMostOne(vars_for_booking)

    if not x:
        return {}, "EMPTY"

    for (flight_id, cabin), vars_using in seat_usage.items():
        model.Add(sum(vars_using) <= max(0, snapshot.get((flight_id, cabin), 0)))

    model.Maximize(sum(objective_terms))

    for booking_id, idx in _greedy_hint(inputs, options, snapshot).items():
        if (booking_id, idx) in x:
            model.AddHint(x[(booking_id, idx)], 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 4
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {}, solver.StatusName(status)

    assignments = {
        booking_id: idx for (booking_id, idx), var in x.items() if solver.Value(var) == 1
    }
    return assignments, solver.StatusName(status)


def plan_cpsat(
    db: Session,
    cache: AirlineFlightCache,
    booking_ids: list[str],
    inventory_snapshot: dict[tuple[str, str], int],
    time_limit_s: float = TIME_LIMIT_SECONDS,
) -> list[PlanResult]:
    all_inputs = load_plan_inputs(db, booking_ids)
    all_inputs.sort(key=lambda b: (-b.priority, b.original_departure))

    results: list[PlanResult] = []
    for start in range(0, len(all_inputs), CHUNK_SIZE):
        chunk = all_inputs[start : start + CHUNK_SIZE]
        options = {b.booking_id: _candidates_for(cache, b, inventory_snapshot) for b in chunk}

        assignments, status = _solve_chunk(chunk, options, inventory_snapshot, time_limit_s)
        log.info("cpsat chunk of %d bookings solved: %s", len(chunk), status)

        for b in chunk:
            idx = assignments.get(b.booking_id)
            if idx is None:
                results.append(PlanResult(b.booking_id, b.priority, None, None))
                continue
            option = options[b.booking_id][idx]
            for seg in option["segments"]:
                key = (seg["flight_id"], seg["cabin"])
                inventory_snapshot[key] = inventory_snapshot.get(key, 0) - 1
            results.append(
                PlanResult(b.booking_id, b.priority, option["segments"], option["delay_minutes"])
            )

    return results
