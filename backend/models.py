"""SQLAlchemy 모델. backend/db/schema.sql과 컬럼이 같아야 한다(tests/test_schema_parity.py가 검사)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base, UTCDateTime
from schemas import common as c

JSON = sa.JSON().with_variant(JSONB, "postgresql")
BigPK = sa.BigInteger().with_variant(sa.Integer, "sqlite")
NUM = lambda p, s: sa.Numeric(p, s, asdecimal=False)
NOW = sa.func.now()


def pg_enum(py, name):
    return sa.Enum(py, name=name, values_callable=lambda e: [m.value for m in e], create_type=False)


def ts(**kw):
    return mapped_column(UTCDateTime, **kw)


def created():
    return mapped_column(UTCDateTime, nullable=False, server_default=NOW)


def uuid_pk():
    return mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True)  # auth.users.id (FK는 DB에만)
    name: Mapped[str | None]
    phone: Mapped[str | None]
    app_role: Mapped[c.AppRole] = mapped_column(pg_enum(c.AppRole, "app_role_enum"), nullable=False, default=c.AppRole.USER)
    status: Mapped[c.ProfileStatus] = mapped_column(pg_enum(c.ProfileStatus, "profile_status_enum"), nullable=False, default=c.ProfileStatus.ACTIVE)
    is_super_admin: Mapped[bool] = mapped_column(default=False)
    notification_prefs: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = created()


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[uuid.UUID] = uuid_pk()
    ros_vehicle_id: Mapped[str | None]
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    plate_no: Mapped[str]
    model: Mapped[str | None]
    battery_kwh: Mapped[float] = mapped_column(NUM(8, 2))
    max_charge_kw: Mapped[float] = mapped_column(NUM(8, 2))
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = created()
    deleted_at: Mapped[datetime | None] = ts()
    __table_args__ = (
        Index("uq_active_vehicle_plate", "plate_no", unique=True, postgresql_where=text("deleted_at is null"), sqlite_where=text("deleted_at is null")),
        Index("uq_active_ros_vehicle_id", "ros_vehicle_id", unique=True, postgresql_where=text("ros_vehicle_id is not null and deleted_at is null"), sqlite_where=text("ros_vehicle_id is not null and deleted_at is null")),
        Index("idx_vehicles_owner", "owner_id"),
    )


class Charger(Base):
    __tablename__ = "chargers"
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    max_power_kw: Mapped[float] = mapped_column(NUM(8, 2))
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = created()


class ParkingZone(Base):
    __tablename__ = "parking_zones"
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    kind: Mapped[c.ParkingZoneKind] = mapped_column(pg_enum(c.ParkingZoneKind, "parking_zone_kind_enum"))
    capacity: Mapped[int]
    pose_x: Mapped[float]
    pose_y: Mapped[float]
    pose_yaw: Mapped[float]
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = created()


_ACTIVE = "status in ('REQUESTED','ACCEPTED','SCHEDULED','IN_PROGRESS','CANCEL_REQUESTED')"


class ChargeRequest(Base):
    __tablename__ = "charge_requests"
    id: Mapped[uuid.UUID] = uuid_pk()
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    desired_finish_at: Mapped[datetime] = ts(nullable=False)
    target_soc: Mapped[int]
    min_soc: Mapped[int]
    parking_zone_id: Mapped[str | None] = mapped_column(ForeignKey("parking_zones.id"))  # (이전 방식) 칸 지정
    parking_area: Mapped[str | None] = mapped_column(String)  # A·B·C. null=관제 자동
    status: Mapped[c.ChargeRequestStatus] = mapped_column(pg_enum(c.ChargeRequestStatus, "charge_request_status_enum"), default=c.ChargeRequestStatus.REQUESTED)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = created()
    cancel_requested_at: Mapped[datetime | None] = ts()
    completed_at: Mapped[datetime | None] = ts()
    __table_args__ = (
        Index("uq_one_active_charge_request_per_vehicle", "vehicle_id", unique=True, postgresql_where=text(_ACTIVE), sqlite_where=text(_ACTIVE)),
        Index("idx_charge_requests_vehicle", "vehicle_id"),
        Index("idx_charge_requests_status", "status"),
        Index("idx_charge_requests_finish", "desired_finish_at"),
    )


class VehicleTask(Base):
    __tablename__ = "vehicle_tasks"
    id: Mapped[uuid.UUID] = uuid_pk()
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("charge_requests.id"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    type: Mapped[c.TaskType] = mapped_column(pg_enum(c.TaskType, "task_type_enum"))
    status: Mapped[c.TaskStatus] = mapped_column(pg_enum(c.TaskStatus, "task_status_enum"), default=c.TaskStatus.CREATED)
    target_id: Mapped[str]
    target_pose_x: Mapped[float]
    target_pose_y: Mapped[float]
    target_pose_yaw: Mapped[float]
    progress: Mapped[float] = mapped_column(NUM(5, 4), default=0)
    error_message: Mapped[str | None]
    created_at: Mapped[datetime] = created()
    accepted_at: Mapped[datetime | None] = ts()
    started_at: Mapped[datetime | None] = ts()
    completed_at: Mapped[datetime | None] = ts()
    updated_at: Mapped[datetime] = created()
    __table_args__ = (Index("idx_vehicle_tasks_request", "request_id"), Index("idx_vehicle_tasks_vehicle", "vehicle_id"), Index("idx_vehicle_tasks_status", "status"))


class VehicleStateRow(Base):
    __tablename__ = "vehicle_states"
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[c.VehicleState] = mapped_column(pg_enum(c.VehicleState, "vehicle_state_enum"))
    soc: Mapped[int]
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("parking_zones.id"))
    pose_x: Mapped[float | None]
    pose_y: Mapped[float | None]
    pose_yaw: Mapped[float | None]
    progress: Mapped[float | None] = mapped_column(NUM(5, 4))
    charger_id: Mapped[str | None] = mapped_column(ForeignKey("chargers.id"))
    current_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicle_tasks.id", ondelete="SET NULL"))
    estimated_completion: Mapped[datetime | None] = ts()
    last_seen_at: Mapped[datetime] = ts(nullable=False)
    updated_at: Mapped[datetime] = created()


class ChargerStateRow(Base):
    __tablename__ = "charger_states"
    charger_id: Mapped[str] = mapped_column(ForeignKey("chargers.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[c.ChargerState] = mapped_column(pg_enum(c.ChargerState, "charger_state_enum"))
    output_kw: Mapped[float | None] = mapped_column(NUM(8, 2))
    assigned_vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))
    maintenance: Mapped[bool] = mapped_column(default=False)
    last_seen_at: Mapped[datetime] = ts(nullable=False)
    updated_at: Mapped[datetime] = created()


class ChargeSession(Base):
    __tablename__ = "charge_sessions"
    id: Mapped[uuid.UUID] = uuid_pk()
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("charge_requests.id"))
    charger_id: Mapped[str] = mapped_column(ForeignKey("chargers.id"))
    start_at: Mapped[datetime] = ts(nullable=False)
    end_at: Mapped[datetime | None] = ts()
    start_soc: Mapped[int]
    end_soc: Mapped[int | None]
    energy_kwh: Mapped[float | None] = mapped_column(NUM(10, 3))
    unit_price_won: Mapped[int | None]  # 세션 시작 시점 단가(원/kWh). 금액 = round(energy_kwh × 단가)
    created_at: Mapped[datetime] = created()
    __table_args__ = (Index("idx_charge_sessions_request", "request_id"),)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(BigPK, primary_key=True, autoincrement=True)
    source_event_id: Mapped[str | None]  # 중앙관제 event_id. 재수신 중복 방지
    at: Mapped[datetime] = created()
    type: Mapped[str]
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))
    charger_id: Mapped[str | None] = mapped_column(ForeignKey("chargers.id"))
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("charge_requests.id"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicle_tasks.id"))
    payload: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    __table_args__ = (
        Index("uq_events_source_event_id", "source_event_id", unique=True, postgresql_where=text("source_event_id is not null"), sqlite_where=text("source_event_id is not null")),
        Index("idx_events_at", "at"), Index("idx_events_vehicle", "vehicle_id"), Index("idx_events_type", "type"),
    )


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    type: Mapped[str]
    title: Mapped[str]
    body: Mapped[str]
    data: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    read_at: Mapped[datetime | None] = ts()
    created_at: Mapped[datetime] = created()


class PushToken(Base):
    __tablename__ = "push_tokens"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    expo_push_token: Mapped[str] = mapped_column(unique=True)
    platform: Mapped[str | None]
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = created()
    last_seen_at: Mapped[datetime] = created()


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    version: Mapped[str]
    agreed_at: Mapped[datetime] = created()
    revoked_at: Mapped[datetime | None] = ts()
    __table_args__ = (Index("idx_consents_user", "user_id", "agreed_at"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(BigPK, primary_key=True, autoincrement=True)
    admin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"))
    action: Mapped[str]
    reason: Mapped[str]
    entity_type: Mapped[str | None]
    entity_id: Mapped[str | None]
    before_data: Mapped[Any | None] = mapped_column(JSON)
    after_data: Mapped[Any | None] = mapped_column(JSON)
    at: Mapped[datetime] = created()


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = created()
