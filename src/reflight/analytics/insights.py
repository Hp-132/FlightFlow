"""Turns the analytics aggregates into stated observations.

Pure functions only: every input is a plain dict from `queries`, so these are
unit-testable without a database. Each observation carries the counts behind
it, thin samples are flagged `limited_data`, and an observation the data
cannot support is not emitted at all.
"""

from statistics import pstdev
from typing import Any

# Sample floors. Below these the observation still ships, flagged, because
# "we looked and there were only 9 delayed flights" is itself useful.
MIN_FLIGHTS_FOR_HOURLY = 48
MIN_DELAYED_FOR_PROFILE = 10
MIN_SAGAS_FOR_CAUSE = 20
MIN_SAGAS_FOR_RETRY = 20

# Below this relative spread, hourly volume is flat enough that naming a
# "peak hour" would be reading noise.
FLAT_VOLUME_CV = 0.25


def _pct(part: float, whole: float) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def _insight(
    key: str,
    headline: str,
    detail: str,
    support: dict[str, Any],
    *,
    limited_data: bool = False,
    tone: str = "neutral",
) -> dict[str, Any]:
    return {
        "key": key,
        "headline": headline,
        "detail": detail,
        "support": support,
        "limited_data": limited_data,
        "tone": tone,
    }


def hourly_volume_spread(by_hour: list[dict[str, Any]]) -> dict[str, Any]:
    """Relative spread of departures across the hours present.

    The generator draws each departure uniformly across a 24-hour day, so a
    flat result here is the expected shape of synthetic data, not a finding
    about airline scheduling. Reported either way so the UI can say which it
    is.
    """
    volumes = [h["flights"] for h in by_hour]
    total = sum(volumes)
    mean = total / len(volumes) if volumes else 0.0
    cv = (pstdev(volumes) / mean) if mean else 0.0
    return {
        "hours_covered": len(volumes),
        "total_flights": total,
        "mean_per_hour": round(mean, 1),
        "coefficient_of_variation": round(cv, 3),
        "is_flat": cv < FLAT_VOLUME_CV,
    }


def worst_departure_hour(by_hour: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Departure hour with the highest disruption rate, over hours carrying
    enough flights to rank at all."""
    ranked = [h for h in by_hour if h["flights"] >= 3]
    if not ranked:
        return None
    worst = max(ranked, key=lambda h: (h["disrupted"] / h["flights"], h["flights"]))
    if worst["disrupted"] == 0:
        return None
    return {
        "hour": worst["hour"],
        "flights": worst["flights"],
        "disrupted": worst["disrupted"],
        "disrupted_pct": _pct(worst["disrupted"], worst["flights"]),
        "avg_delay_minutes": worst["avg_delay_minutes"],
    }


def build_overview(schedule: dict[str, Any], recovery: dict[str, Any]) -> dict[str, Any]:
    """The KPI row. Shares the vocabulary of the rest of the app: a booking is
    'recovered' when its saga COMPLETED."""
    flights = schedule["flights"]
    sagas = recovery["sagas"]
    bookings = schedule["bookings_by_status"]

    total_flights = flights["total"]
    disrupted_flights = flights["delayed"] + flights["cancelled"]
    total_bookings = sum(bookings.values())
    touched_bookings = (
        bookings.get("DISRUPTED", 0) + bookings.get("REBOOKED", 0) + bookings.get("UNRECOVERED", 0)
    )

    return {
        "total_flights": total_flights,
        "disrupted_flights": disrupted_flights,
        "disrupted_flights_pct": _pct(disrupted_flights, total_flights),
        "on_time_flights": flights["on_time"],
        "on_time_pct": _pct(flights["on_time"], total_flights),
        "cancelled_flights": flights["cancelled"],
        "delayed_flights": flights["delayed"],
        "avg_delay_minutes": flights["avg_delay_minutes"],
        "total_bookings": total_bookings,
        "affected_bookings": touched_bookings,
        "rebooked_bookings": bookings.get("REBOOKED", 0),
        "unrecovered_bookings": bookings.get("UNRECOVERED", 0),
        "sagas": sagas["total"],
        "recovered_sagas": sagas["completed"],
        "recovery_rate_pct": _pct(sagas["completed"], sagas["total"]),
        "retry_rate_pct": _pct(sagas["retried"], sagas["total"]),
        "avg_recovery_seconds": sagas["avg_recovery_seconds"],
        "avg_rebooked_delay_minutes": sagas["avg_rebooked_delay_minutes"],
        "dead_letters": sum(d["dead_letters"] for d in recovery["dead_letters"]),
    }


def build_insights(schedule: dict[str, Any], recovery: dict[str, Any]) -> list[dict[str, Any]]:
    """Observations derived from the aggregates, most actionable first."""
    out: list[dict[str, Any]] = []
    flights = schedule["flights"]
    sagas = recovery["sagas"]
    total_flights = flights["total"]

    spread = hourly_volume_spread(schedule["by_hour"])
    worst_hour = worst_departure_hour(schedule["by_hour"])
    if worst_hour:
        out.append(
            _insight(
                "worst_departure_hour",
                f"Departures at {worst_hour['hour']:02d}:00 are the most disrupted",
                (
                    f"{worst_hour['disrupted']} of {worst_hour['flights']} flights "
                    f"({worst_hour['disrupted_pct']}%) scheduled in that hour were delayed or "
                    f"cancelled"
                    + (
                        f", averaging {worst_hour['avg_delay_minutes']} min of delay."
                        if worst_hour["avg_delay_minutes"]
                        else " -- all of them cancellations, so there is no delay figure."
                    )
                    + (
                        " Departure volume is near-flat across the day in this dataset, so "
                        "treat this as where the storm landed, not a recurring traffic peak."
                        if spread["is_flat"]
                        else ""
                    )
                ),
                {
                    "hour": worst_hour["hour"],
                    "flights_in_hour": worst_hour["flights"],
                    "disrupted": worst_hour["disrupted"],
                    "disrupted_pct": worst_hour["disrupted_pct"],
                    "hourly_volume_cv": spread["coefficient_of_variation"],
                },
                limited_data=total_flights < MIN_FLIGHTS_FOR_HOURLY,
                tone="warning",
            )
        )

    histogram = {b["bucket"]: b["flights"] for b in schedule["delay_histogram"]}
    delayed = flights["delayed"]
    if delayed:
        long_delays = histogram.get("121-180", 0) + histogram.get("180+", 0)
        out.append(
            _insight(
                "delay_severity",
                (
                    f"{_pct(long_delays, delayed)}% of delayed departures are over two hours"
                    if long_delays
                    else "No delayed departure exceeds two hours"
                ),
                (
                    f"{long_delays} of {delayed} delayed flights sit in the 121-180 and 180+ minute "
                    f"buckets; the mean delay across all delayed flights is "
                    f"{flights['avg_delay_minutes']} min and the worst is "
                    f"{flights['max_delay_minutes']} min."
                ),
                {
                    "delayed_flights": delayed,
                    "over_two_hours": long_delays,
                    "avg_delay_minutes": flights["avg_delay_minutes"],
                    "max_delay_minutes": flights["max_delay_minutes"],
                },
                limited_data=delayed < MIN_DELAYED_FOR_PROFILE,
                tone="warning" if long_delays else "success",
            )
        )

    by_cause = [c for c in recovery["recovery_by_cause"] if c["sagas"] > 0]
    if len(by_cause) >= 2:
        hardest = min(by_cause, key=lambda c: c["recovered_pct"])
        easiest = max(by_cause, key=lambda c: c["recovered_pct"])
        if hardest["cause"] != easiest["cause"]:
            out.append(
                _insight(
                    "recovery_by_cause",
                    f"{hardest['cause']} disruptions recover worst at {hardest['recovered_pct']}%",
                    (
                        f"{hardest['completed']} of {hardest['sagas']} passengers disrupted by "
                        f"{hardest['cause']} were rebooked, against "
                        f"{easiest['recovered_pct']}% for {easiest['cause']} "
                        f"({easiest['completed']} of {easiest['sagas']}). A booking hit by more "
                        f"than one cause counts under each."
                    ),
                    {
                        "hardest_cause": hardest["cause"],
                        "hardest_recovered_pct": hardest["recovered_pct"],
                        "hardest_sagas": hardest["sagas"],
                        "easiest_cause": easiest["cause"],
                        "easiest_recovered_pct": easiest["recovered_pct"],
                        "easiest_sagas": easiest["sagas"],
                    },
                    limited_data=min(hardest["sagas"], easiest["sagas"]) < MIN_SAGAS_FOR_CAUSE,
                    tone="warning",
                )
            )

    unrecovered = sagas["failed_no_capacity"] + sagas["needs_manual"]
    if sagas["total"]:
        out.append(
            _insight(
                "recovery_outcome",
                f"{_pct(sagas['completed'], sagas['total'])}% of disrupted passengers were rebooked",
                (
                    f"{sagas['completed']} of {sagas['total']} sagas completed, "
                    f"{sagas['compensated']} were compensated after a failed step, and "
                    f"{unrecovered} ended unrecovered "
                    f"({sagas['failed_no_capacity']} with no seat capacity, "
                    f"{sagas['needs_manual']} needing manual handling). Mean time to recover a "
                    f"booking was {sagas['avg_recovery_seconds']}s."
                ),
                {
                    "sagas": sagas["total"],
                    "completed": sagas["completed"],
                    "compensated": sagas["compensated"],
                    "failed_no_capacity": sagas["failed_no_capacity"],
                    "needs_manual": sagas["needs_manual"],
                    "avg_recovery_seconds": sagas["avg_recovery_seconds"],
                },
                limited_data=sagas["total"] < MIN_SAGAS_FOR_CAUSE,
                tone="success" if sagas["completed"] >= unrecovered else "warning",
            )
        )

    if sagas["total"] and sagas["retried"]:
        dead = sorted(recovery["dead_letters"], key=lambda d: d["dead_letters"], reverse=True)
        worst_step = dead[0] if dead else None
        out.append(
            _insight(
                "retry_concentration",
                f"{_pct(sagas['retried'], sagas['total'])}% of sagas needed at least one retry",
                (
                    f"{sagas['retried']} of {sagas['total']} sagas retried a step, "
                    f"{sagas['total_attempts']} extra attempts in total"
                    + (
                        f"; the {worst_step['step']} step accounts for the most dead letters "
                        f"({worst_step['dead_letters']})."
                        if worst_step
                        else ", and nothing reached the dead-letter queue."
                    )
                ),
                {
                    "sagas": sagas["total"],
                    "retried": sagas["retried"],
                    "total_attempts": sagas["total_attempts"],
                    "worst_step": worst_step["step"] if worst_step else None,
                    "worst_step_dead_letters": worst_step["dead_letters"] if worst_step else 0,
                },
                limited_data=sagas["total"] < MIN_SAGAS_FOR_RETRY,
                tone="warning",
            )
        )

    airports = [a for a in schedule["airports"] if a["departures"] >= 3]
    if airports:
        worst_airport = max(
            airports, key=lambda a: ((a["cancelled"] + a["delayed"]) / a["departures"], a["departures"])
        )
        hit = worst_airport["cancelled"] + worst_airport["delayed"]
        if hit:
            out.append(
                _insight(
                    "airport_impact",
                    f"{worst_airport['iata']} lost the largest share of its departures",
                    (
                        f"{hit} of {worst_airport['departures']} departures "
                        f"({_pct(hit, worst_airport['departures'])}%) from {worst_airport['iata']} "
                        f"were cancelled or delayed"
                        f"{' -- it is a hub in this network' if worst_airport['is_hub'] else ''}."
                    ),
                    {
                        "iata": worst_airport["iata"],
                        "departures": worst_airport["departures"],
                        "disrupted": hit,
                        "disrupted_pct": _pct(hit, worst_airport["departures"]),
                        "is_hub": worst_airport["is_hub"],
                    },
                    limited_data=worst_airport["departures"] < 10,
                    tone="warning",
                )
            )

    return out


def missing_capabilities(schedule: dict[str, Any]) -> list[dict[str, str]]:
    """What this schema cannot answer, and the field that would change that.

    Stated rather than silently skipped, so the page explains its own gaps
    instead of implying the analysis is complete.
    """
    gaps = [
        {
            "question": "Day-of-week and seasonal scheduling patterns",
            "needed": (
                "Flights spanning multiple days. The generator lays every departure inside one "
                "synthetic 24-hour day, so weekday effects cannot exist in this data."
            ),
        },
        {
            "question": "Actual punctuality (observed on-time performance)",
            "needed": (
                "An observed departure/arrival time distinct from the scheduled one. Here "
                "dep_at only differs from sched_dep_at when a scenario injected a delay, so "
                "'on time' means 'not disrupted by a loaded scenario'."
            ),
        },
        {
            "question": "Arrival punctuality and taxi/block-time analysis",
            "needed": "Gate/runway timestamps; only scheduled and adjusted arrival times exist.",
        },
        {
            "question": "Load factor and revenue impact per flight",
            "needed": (
                "Seats sold per flight over time. seat_inventory carries current capacity and "
                "availability, but no booking-curve history."
            ),
        },
    ]

    span_hours = _schedule_span_hours(schedule)
    if span_hours is not None and span_hours > 48:
        # The one-day claim above would be wrong, so drop it.
        gaps = [g for g in gaps if not g["question"].startswith("Day-of-week")]
    return gaps


def _schedule_span_hours(schedule: dict[str, Any]) -> float | None:
    first = schedule["flights"].get("first_departure")
    last = schedule["flights"].get("last_departure")
    if not first or not last:
        return None
    from datetime import datetime

    return (datetime.fromisoformat(last) - datetime.fromisoformat(first)).total_seconds() / 3600
