from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    name: str
    num_airports: int
    num_hubs: int
    num_airlines: int
    num_passengers: int
    flights_per_airline_per_day: int


PRESETS: dict[str, Preset] = {
    "small": Preset(
        name="small",
        num_airports=8,
        num_hubs=1,
        num_airlines=2,
        num_passengers=500,
        flights_per_airline_per_day=40,
    ),
    "storm": Preset(
        name="storm",
        num_airports=12,
        num_hubs=2,
        num_airlines=3,
        num_passengers=10_000,
        flights_per_airline_per_day=150,
    ),
    "mega": Preset(
        name="mega",
        num_airports=20,
        num_hubs=3,
        num_airlines=4,
        num_passengers=30_000,
        flights_per_airline_per_day=400,
    ),
}


def get_preset(name: str) -> Preset:
    if name not in PRESETS:
        raise ValueError(f"unknown preset {name!r}; choices: {sorted(PRESETS)}")
    return PRESETS[name]
