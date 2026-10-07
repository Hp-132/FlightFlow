from reflight.simulator.generator import build_scenario


def test_same_seed_same_hash():
    a = build_scenario("small", seed=7, hub_iata=None, severity=0.8)
    b = build_scenario("small", seed=7, hub_iata=None, severity=0.8)
    assert a["content_hash"] == b["content_hash"]


def test_different_seed_different_hash():
    a = build_scenario("small", seed=7, hub_iata=None, severity=0.8)
    b = build_scenario("small", seed=8, hub_iata=None, severity=0.8)
    assert a["content_hash"] != b["content_hash"]


def test_scenario_shape():
    scenario = build_scenario("small", seed=1, hub_iata=None, severity=0.8)
    assert len(scenario["airports"]) == 8
    assert len(scenario["airlines"]) == 2
    assert len(scenario["passengers"]) == len(scenario["bookings"])
    assert scenario["timeline"], "expected at least one disruption event"
    for event in scenario["timeline"]:
        assert event["cause"] in {"WEATHER", "AOG", "CREW", "CASCADE"}
        assert event["type"] in {"CANCELLATION", "DELAY"}


def test_scenario_includes_a_cascade_chain():
    scenario = build_scenario("small", seed=3, hub_iata=None, severity=0.8)
    cascade = [e for e in scenario["timeline"] if e["cause"] == "CASCADE"]
    assert cascade, "expected F2b cascade events in the timeline"
    assert any(e["type"] == "CANCELLATION" for e in cascade)
