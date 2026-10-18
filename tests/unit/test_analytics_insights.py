"""Unit tests for the pure analytics derivations.

No database: these feed `queries`-shaped dicts straight into the pure
functions, which is the reason the module is split that way.
"""

from reflight.analytics.insights import (
    build_insights,
    build_overview,
    hourly_volume_spread,
    missing_capabilities,
    worst_departure_hour,
)


def make_schedule(**overrides):
    schedule = {
        "flights": {
            "total": 80,
            "scheduled": 60,
            "delayed": 12,
            "cancelled": 8,
            "on_time": 60,
            "avg_delay_minutes": 95.0,
            "max_delay_minutes": 240.0,
            "first_departure": "2026-01-01T00:10:00+00:00",
            "last_departure": "2026-01-01T23:40:00+00:00",
        },
        "by_hour": [
            {"hour": h, "flights": 4, "cancelled": 0, "delayed": 0, "disrupted": 0, "avg_delay_minutes": 0.0}
            for h in range(20)
        ],
        "delay_histogram": [
            {"bucket": "1-30", "flights": 2},
            {"bucket": "31-60", "flights": 3},
            {"bucket": "61-120", "flights": 3},
            {"bucket": "121-180", "flights": 2},
            {"bucket": "180+", "flights": 2},
        ],
        "routes": [],
        "airports": [
            {"iata": "AAA", "is_hub": True, "departures": 30, "cancelled": 8, "delayed": 7, "avg_delay_minutes": 120.0},
            {"iata": "BBB", "is_hub": False, "departures": 25, "cancelled": 0, "delayed": 1, "avg_delay_minutes": 20.0},
        ],
        "bookings_by_status": {"ACTIVE": 300, "DISRUPTED": 5, "REBOOKED": 40, "UNRECOVERED": 5},
    }
    schedule.update(overrides)
    return schedule


def make_recovery(**overrides):
    recovery = {
        "run_ids": ["run-1"],
        "runs": [],
        "sagas": {
            "total": 50,
            "completed": 40,
            "compensated": 4,
            "failed_no_capacity": 4,
            "needs_manual": 2,
            "retried": 10,
            "total_attempts": 14,
            "avg_recovery_seconds": 12.5,
            "avg_rebooked_delay_minutes": 85.0,
        },
        "sagas_by_state": {"COMPLETED": 40, "COMPENSATED": 4, "FAILED_NO_CAPACITY": 4, "NEEDS_MANUAL": 2},
        "disruption_causes": [
            {"cause": "WEATHER", "events": 20, "cancellations": 18, "delays": 2, "avg_delay_minutes": 30.0},
        ],
        "recovery_by_cause": [
            {"cause": "WEATHER", "sagas": 30, "completed": 21, "compensated": 3, "failed_no_capacity": 4,
             "needs_manual": 2, "recovered_pct": 70.0},
            {"cause": "CREW", "sagas": 20, "completed": 19, "compensated": 1, "failed_no_capacity": 0,
             "needs_manual": 0, "recovered_pct": 95.0},
        ],
        "dead_letters": [{"step": "ISSUE_TICKET", "dead_letters": 3}],
    }
    recovery.update(overrides)
    return recovery


EMPTY_SCHEDULE = {
    "flights": {
        "total": 0, "scheduled": 0, "delayed": 0, "cancelled": 0, "on_time": 0,
        "avg_delay_minutes": 0.0, "max_delay_minutes": 0.0,
        "first_departure": None, "last_departure": None,
    },
    "by_hour": [],
    "delay_histogram": [{"bucket": b, "flights": 0} for b in ["1-30", "31-60", "61-120", "121-180", "180+"]],
    "routes": [],
    "airports": [],
    "bookings_by_status": {},
}

EMPTY_RECOVERY = {
    "run_ids": [],
    "runs": [],
    "sagas": {
        "total": 0, "completed": 0, "compensated": 0, "failed_no_capacity": 0, "needs_manual": 0,
        "retried": 0, "total_attempts": 0, "avg_recovery_seconds": 0.0, "avg_rebooked_delay_minutes": 0.0,
    },
    "sagas_by_state": {},
    "disruption_causes": [],
    "recovery_by_cause": [],
    "dead_letters": [],
}


# ---- overview ----------------------------------------------------------


def test_overview_percentages_match_counts():
    overview = build_overview(make_schedule(), make_recovery())

    assert overview["total_flights"] == 80
    assert overview["disrupted_flights"] == 20  # 12 delayed + 8 cancelled
    assert overview["disrupted_flights_pct"] == 25.0
    assert overview["on_time_pct"] == 75.0
    assert overview["recovery_rate_pct"] == 80.0  # 40 of 50
    assert overview["retry_rate_pct"] == 20.0  # 10 of 50
    assert overview["affected_bookings"] == 50  # 5 disrupted + 40 rebooked + 5 unrecovered
    assert overview["total_bookings"] == 350
    assert overview["dead_letters"] == 3


def test_overview_on_empty_database_is_all_zeros_not_an_error():
    overview = build_overview(EMPTY_SCHEDULE, EMPTY_RECOVERY)

    assert overview["total_flights"] == 0
    assert overview["disrupted_flights_pct"] == 0.0
    assert overview["recovery_rate_pct"] == 0.0
    assert overview["affected_bookings"] == 0


# ---- hourly spread -----------------------------------------------------


def test_flat_hourly_volume_is_reported_as_flat():
    spread = hourly_volume_spread(make_schedule()["by_hour"])

    assert spread["is_flat"] is True
    assert spread["coefficient_of_variation"] == 0.0
    assert spread["hours_covered"] == 20


def test_peaked_hourly_volume_is_not_flat():
    by_hour = [
        {"hour": h, "flights": 40 if h == 8 else 2, "cancelled": 0, "delayed": 0, "disrupted": 0,
         "avg_delay_minutes": 0.0}
        for h in range(24)
    ]

    assert hourly_volume_spread(by_hour)["is_flat"] is False


def test_hourly_spread_handles_no_hours():
    spread = hourly_volume_spread([])

    assert spread["hours_covered"] == 0
    assert spread["coefficient_of_variation"] == 0.0


# ---- worst departure hour ---------------------------------------------


def test_worst_departure_hour_picks_highest_disruption_rate():
    by_hour = [
        {"hour": 6, "flights": 10, "cancelled": 1, "delayed": 0, "disrupted": 1, "avg_delay_minutes": 20.0},
        {"hour": 7, "flights": 10, "cancelled": 4, "delayed": 2, "disrupted": 6, "avg_delay_minutes": 90.0},
        {"hour": 8, "flights": 2, "cancelled": 2, "delayed": 0, "disrupted": 2, "avg_delay_minutes": 50.0},
    ]

    worst = worst_departure_hour(by_hour)

    # hour 8 is 100% disrupted but below the 3-flight floor, so hour 7 wins
    assert worst["hour"] == 7
    assert worst["disrupted_pct"] == 60.0


def test_worst_departure_hour_is_none_when_nothing_was_disrupted():
    assert worst_departure_hour(make_schedule()["by_hour"]) is None


def test_worst_departure_hour_is_none_without_data():
    assert worst_departure_hour([]) is None


# ---- insights ----------------------------------------------------------


def test_insights_report_hardest_cause_with_supporting_counts():
    insights = {i["key"]: i for i in build_insights(make_schedule(), make_recovery())}

    cause = insights["recovery_by_cause"]
    assert "WEATHER" in cause["headline"]
    assert cause["support"]["hardest_recovered_pct"] == 70.0
    assert cause["support"]["easiest_cause"] == "CREW"
    # 30 and 20 sagas are both over the floor
    assert cause["limited_data"] is False


def test_thin_samples_are_flagged_as_limited_data():
    thin = make_recovery(
        sagas={
            "total": 6, "completed": 3, "compensated": 1, "failed_no_capacity": 1, "needs_manual": 1,
            "retried": 2, "total_attempts": 2, "avg_recovery_seconds": 9.0,
            "avg_rebooked_delay_minutes": 40.0,
        },
        recovery_by_cause=[
            {"cause": "WEATHER", "sagas": 4, "completed": 2, "compensated": 1, "failed_no_capacity": 1,
             "needs_manual": 0, "recovered_pct": 50.0},
            {"cause": "AOG", "sagas": 2, "completed": 2, "compensated": 0, "failed_no_capacity": 0,
             "needs_manual": 0, "recovered_pct": 100.0},
        ],
    )

    insights = {i["key"]: i for i in build_insights(make_schedule(), thin)}

    assert insights["recovery_by_cause"]["limited_data"] is True
    assert insights["recovery_outcome"]["limited_data"] is True
    assert insights["retry_concentration"]["limited_data"] is True


def test_no_insights_are_invented_for_an_empty_database():
    assert build_insights(EMPTY_SCHEDULE, EMPTY_RECOVERY) == []


def test_cause_comparison_is_skipped_with_only_one_cause():
    single = make_recovery(
        recovery_by_cause=[
            {"cause": "WEATHER", "sagas": 30, "completed": 21, "compensated": 3,
             "failed_no_capacity": 4, "needs_manual": 2, "recovered_pct": 70.0},
        ]
    )

    keys = {i["key"] for i in build_insights(make_schedule(), single)}

    assert "recovery_by_cause" not in keys


def test_delay_severity_counts_only_the_over_two_hour_buckets():
    insights = {i["key"]: i for i in build_insights(make_schedule(), make_recovery())}

    severity = insights["delay_severity"]
    assert severity["support"]["over_two_hours"] == 4  # 2 in 121-180 + 2 in 180+
    assert severity["support"]["delayed_flights"] == 12
    assert "33.3%" in severity["headline"]


def test_flat_volume_caveat_appears_in_the_departure_hour_insight():
    schedule = make_schedule(
        by_hour=[
            {"hour": h, "flights": 4, "cancelled": 1 if h == 9 else 0, "delayed": 0,
             "disrupted": 1 if h == 9 else 0, "avg_delay_minutes": 0.0}
            for h in range(20)
        ]
    )

    insights = {i["key"]: i for i in build_insights(schedule, make_recovery())}

    assert "near-flat" in insights["worst_departure_hour"]["detail"]


def test_airport_impact_prefers_the_worst_hit_share():
    insights = {i["key"]: i for i in build_insights(make_schedule(), make_recovery())}

    airport = insights["airport_impact"]
    assert airport["support"]["iata"] == "AAA"
    assert airport["support"]["disrupted"] == 15
    assert airport["support"]["is_hub"] is True


# ---- declared gaps -----------------------------------------------------


def test_single_day_schedule_declares_the_day_of_week_gap():
    questions = [g["question"] for g in missing_capabilities(make_schedule())]

    assert any(q.startswith("Day-of-week") for q in questions)


def test_multi_day_schedule_drops_the_day_of_week_gap():
    schedule = make_schedule(
        flights={
            **make_schedule()["flights"],
            "first_departure": "2026-01-01T00:00:00+00:00",
            "last_departure": "2026-01-09T00:00:00+00:00",
        }
    )

    questions = [g["question"] for g in missing_capabilities(schedule)]

    assert not any(q.startswith("Day-of-week") for q in questions)


def test_gaps_survive_an_empty_schedule():
    assert len(missing_capabilities(EMPTY_SCHEDULE)) >= 1
