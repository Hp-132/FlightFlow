from pydantic import BaseModel, Field


class GenerateScenarioRequest(BaseModel):
    preset: str = Field(default="small", pattern="^(small|storm|mega)$")
    seed: int = 42
    hub: str | None = None
    severity: float = Field(default=0.8, ge=0.0, le=1.0)
    cascade_chains: int = Field(default=3, ge=0, le=20)


class ScenarioResponse(BaseModel):
    id: str


class LoadScenarioResponse(BaseModel):
    scenario_id: str
    counts: dict[str, int]


class CreateRunRequest(BaseModel):
    scenario_id: str
    strategy: str = Field(default="greedy", pattern="^(greedy|cpsat)$")


class RunResponse(BaseModel):
    id: str
    scenario_id: str
    strategy: str
    status: str


class StartRunResponse(BaseModel):
    run_id: str
    disruption_events: int
    cancelled_flights: int
    delayed_flights: int
    disrupted_bookings: int
    plan_batches_queued: int


class DisruptionEventResponse(BaseModel):
    id: str
    type: str
    cause: str
    target_flight_id: str | None
    target_airport_id: str | None
    delay_minutes: int | None
    occurred_at: str


class ChaosRequest(BaseModel):
    crash_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    partner_failure_rate: float = Field(default=0.0, ge=0.0, le=1.0)


class FairnessRequest(BaseModel):
    """0 means unlimited. `caps` is keyed by airline code (e.g. {"QX": 2})."""

    default_cap: int | None = Field(default=None, ge=0, le=100)
    caps: dict[str, int] | None = None
