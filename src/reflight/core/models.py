import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from reflight.core.constants import (
    BOOKING_STATUSES,
    CAUSES,
    EVENT_TYPES,
    FLIGHT_STATUSES,
    HOLD_STATUSES,
    RUN_STATUSES,
    SAGA_STATES,
    STRATEGIES,
    TIERS,
)
from reflight.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Airline(Base):
    __tablename__ = "airlines"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)


class Airport(Base):
    __tablename__ = "airports"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    iata: Mapped[str] = mapped_column(String(3), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    is_hub: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Flight(Base):
    __tablename__ = "flights"
    __table_args__ = (
        CheckConstraint(f"status IN {FLIGHT_STATUSES}", name="ck_flights_status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    airline_id: Mapped[str] = mapped_column(ForeignKey("airlines.id"), nullable=False)
    flight_no: Mapped[str] = mapped_column(String(16), nullable=False)
    tail_number: Mapped[str] = mapped_column(String(16), nullable=False)
    origin: Mapped[str] = mapped_column(ForeignKey("airports.id"), nullable=False)
    dest: Mapped[str] = mapped_column(ForeignKey("airports.id"), nullable=False)
    dep_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arr_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sched_dep_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sched_arr_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="SCHEDULED")

    seat_inventory: Mapped[list["SeatInventory"]] = relationship(back_populates="flight")


class SeatInventory(Base):
    __tablename__ = "seat_inventory"

    flight_id: Mapped[str] = mapped_column(ForeignKey("flights.id"), primary_key=True)
    cabin: Mapped[str] = mapped_column(String(16), primary_key=True)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    available: Mapped[int] = mapped_column(Integer, nullable=False)
    sold_other: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    flight: Mapped["Flight"] = relationship(back_populates="seat_inventory")

    __table_args__ = (
        CheckConstraint("available >= 0", name="ck_seat_inventory_available_nonneg"),
        CheckConstraint("available <= capacity", name="ck_seat_inventory_available_le_capacity"),
    )


class Passenger(Base):
    __tablename__ = "passengers"
    __table_args__ = (
        CheckConstraint(f"tier IN {TIERS}", name="ck_passengers_tier"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    airline_id: Mapped[str] = mapped_column(ForeignKey("airlines.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False, default="NONE")
    is_unaccompanied_minor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bags: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint(f"status IN {BOOKING_STATUSES}", name="ck_bookings_status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    passenger_id: Mapped[str] = mapped_column(ForeignKey("passengers.id"), nullable=False)
    pnr: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")

    segments: Mapped[list["BookingSegment"]] = relationship(back_populates="booking")


class BookingSegment(Base):
    __tablename__ = "booking_segments"

    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    flight_id: Mapped[str] = mapped_column(ForeignKey("flights.id"), nullable=False)
    cabin: Mapped[str] = mapped_column(String(16), nullable=False)

    booking: Mapped["Booking"] = relationship(back_populates="segments")


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    params_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    minio_key: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(f"strategy IN {STRATEGIES}", name="ck_runs_strategy"),
        CheckConstraint(f"status IN {RUN_STATUSES}", name="ck_runs_status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id"), nullable=False)
    strategy: Mapped[str] = mapped_column(String(16), nullable=False, default="greedy")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="CREATED")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DisruptionEvent(Base):
    __tablename__ = "disruption_events"
    __table_args__ = (
        CheckConstraint(f"type IN {EVENT_TYPES}", name="ck_disruption_events_type"),
        CheckConstraint(f"cause IN {CAUSES}", name="ck_disruption_events_cause"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    cause: Mapped[str] = mapped_column(String(16), nullable=False)
    target_flight_id: Mapped[str | None] = mapped_column(ForeignKey("flights.id"), nullable=True)
    target_airport_id: Mapped[str | None] = mapped_column(ForeignKey("airports.id"), nullable=True)
    delay_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Saga(Base):
    __tablename__ = "sagas"
    __table_args__ = (
        UniqueConstraint("run_id", "booking_id", name="uq_sagas_run_booking"),
        CheckConstraint(f"state IN {SAGA_STATES}", name="ck_sagas_state"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="PLANNED")
    current_step: Mapped[str | None] = mapped_column(String(24), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    plan_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SagaEvent(Base):
    __tablename__ = "saga_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    saga_id: Mapped[str] = mapped_column(ForeignKey("sagas.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("saga_id", "seq", name="uq_saga_events_saga_seq"),)


class SeatHold(Base):
    __tablename__ = "seat_holds"
    __table_args__ = (
        UniqueConstraint("saga_id", "flight_id", "cabin", name="uq_seat_holds_saga_flight_cabin"),
        CheckConstraint(f"status IN {HOLD_STATUSES}", name="ck_seat_holds_status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    saga_id: Mapped[str] = mapped_column(ForeignKey("sagas.id"), nullable=False)
    flight_id: Mapped[str] = mapped_column(ForeignKey("flights.id"), nullable=False)
    cabin: Mapped[str] = mapped_column(String(16), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="HELD")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Outbox(Base):
    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    routing_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"

    saga_id: Mapped[str] = mapped_column(ForeignKey("sagas.id"), primary_key=True)
    step: Mapped[str] = mapped_column(String(24), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeadLetter(Base):
    __tablename__ = "dead_letters"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    saga_id: Mapped[str] = mapped_column(ForeignKey("sagas.id"), nullable=False)
    step: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# partners schema: owned by the mock partners service (Phase 4), kept here so
# the whole schema ships in one migration.
# ---------------------------------------------------------------------------


class PartnerTicket(Base):
    __tablename__ = "tickets"
    __table_args__ = ({"schema": "partners"},)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    saga_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pnr: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ISSUED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PartnerBagTag(Base):
    __tablename__ = "bag_tags"
    __table_args__ = ({"schema": "partners"},)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    saga_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pnr: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="TAGGED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PartnerIdempotency(Base):
    __tablename__ = "idempotency"
    __table_args__ = ({"schema": "partners"},)

    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
