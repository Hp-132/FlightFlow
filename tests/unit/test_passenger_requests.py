import string

import pytest
from pydantic import ValidationError

from reflight.api.routes_passengers import PNR_ALPHABET, PNR_LENGTH, _like, new_pnr
from reflight.api.schemas import CreatePassengerRequest, DisruptBookingRequest


def make_request(**overrides):
    body = {"name": "Priya Sharma", "flight_id": "0c8e29e3-f93e-48d5-bea2-9dfec73f6e1b"}
    body.update(overrides)
    return CreatePassengerRequest(**body)


def test_defaults_describe_an_economy_passenger_with_one_bag():
    req = make_request()

    assert (req.cabin, req.tier, req.bags, req.is_unaccompanied_minor) == ("ECONOMY", "NONE", 1, False)


def test_flight_id_must_be_a_uuid():
    with pytest.raises(ValidationError):
        make_request(flight_id="nope")


def test_name_is_stripped_of_surrounding_whitespace():
    assert make_request(name="  Priya Sharma  ").name == "Priya Sharma"


@pytest.mark.parametrize("name", ["", " ", "A", " A ", "x" * 61])
def test_names_outside_two_to_sixty_characters_are_rejected(name):
    with pytest.raises(ValidationError):
        make_request(name=name)


@pytest.mark.parametrize("field,value", [("cabin", "FIRST"), ("tier", "PLATINUM"), ("bags", -1), ("bags", 6)])
def test_out_of_range_choices_are_rejected(field, value):
    with pytest.raises(ValidationError):
        make_request(**{field: value})


@pytest.mark.parametrize("cause", ["WEATHER", "AOG", "CREW", "ATC"])
def test_manual_disruption_accepts_the_causes_a_cancellation_can_have(cause):
    assert DisruptBookingRequest(cause=cause).cause == cause


def test_cascade_is_not_a_manual_cause():
    with pytest.raises(ValidationError):
        DisruptBookingRequest(cause="CASCADE")


def test_pnr_matches_the_generators_format():
    pnr = new_pnr()

    assert len(pnr) == PNR_LENGTH == 6
    assert set(pnr) <= set(string.ascii_uppercase + string.digits)
    assert PNR_ALPHABET == string.ascii_uppercase + string.digits


def test_pnrs_are_not_repeated_across_a_large_sample():
    assert len({new_pnr() for _ in range(2000)}) == 2000


@pytest.mark.parametrize(
    "raw,expected",
    [("abc", "%abc%"), ("50%", "%50\\%%"), ("a_b", "%a\\_b%"), ("a\\b", "%a\\\\b%"), ("", "%%")],
)
def test_search_text_cannot_inject_like_wildcards(raw, expected):
    assert _like(raw) == expected
