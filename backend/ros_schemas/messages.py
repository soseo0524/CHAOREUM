from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from schemas.common import (
    ChargeRequestStatus,
    ChargerState,
    Pose,
    StrEnum,
    TaskStatus,
    TaskType,
    VehicleState,
)

SCHEMA_VERSION = 1
ALL_VEHICLES = "ALL"  # 비상 정지 전체 대상
ID_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"  # ros_vehicle_id / charger_id / zone_id
UUID_PATTERN = r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$"


class RosModel(BaseModel):
    model_config = ConfigDict(extra="ignore", use_enum_values=False)
    schema_version: int = SCHEMA_VERSION


VehicleId = Field(pattern=ID_PATTERN, description="ros_vehicle_id (예: CAR_01)")
UuidStr = Field(pattern=UUID_PATTERN)


# ---------------- FastAPI → 중앙관제 ----------------
class ChargingRequestMsg(RosModel):
    """/charging/request"""

    request_id: str = UuidStr
    vehicle_id: str = VehicleId
    desired_finish_at: AwareDatetime  # PARKED가 되길 원하는 시각
    target_soc: int = Field(ge=1, le=100)
    min_soc: int = Field(0, ge=0, le=100)
    battery_kwh: float = Field(gt=0, description="충전 시간 추정용")
    max_charge_kw: float = Field(gt=0, description="충전 시간 추정용")
    parking_zone_id: str | None = Field(None, pattern=ID_PATTERN, description="(이전 방식) 사용자가 고른 칸")
    parking_area: Literal["A", "B", "C"] | None = Field(None, description="사용자가 고른 주차 구역. 구역 안의 칸은 관제가 고른다. null이면 관제가 구역도 고름")

    @model_validator(mode="after")
    def _soc(self):
        if self.min_soc > self.target_soc:
            raise ValueError("min_soc must be <= target_soc")
        return self


class ChargingCancelMsg(RosModel):
    """/charging/cancel"""

    request_id: str = UuidStr
    vehicle_id: str = VehicleId
    requested_by: Literal["user", "admin"]
    reason: str | None = None


class AdminAction(StrEnum):
    CANCEL = "cancel"
    RETRY = "retry"
    REASSIGN = "reassign"


class AdminCommandMsg(RosModel):
    """/admin/command — 관리자 수동 조치. 사유 필수(audit_logs와 동일)."""

    command_id: str = UuidStr
    action: AdminAction
    vehicle_id: str = VehicleId
    request_id: str | None = Field(None, pattern=UUID_PATTERN)
    task_id: str | None = Field(None, pattern=UUID_PATTERN)
    charger_id: str | None = Field(None, pattern=ID_PATTERN)  # reassign
    reason: str = Field(min_length=2)
    admin_id: str = UuidStr

    @model_validator(mode="after")
    def _check(self):
        if self.request_id is None and self.task_id is None:
            raise ValueError("request_id or task_id is required")
        if (self.action == AdminAction.REASSIGN) != (self.charger_id is not None):
            raise ValueError("charger_id is required only for reassign")
        return self


class EmergencyAction(StrEnum):
    STOP = "STOP"
    RELEASE = "RELEASE"


class EmergencyStopMsg(RosModel):
    """/emergency_stop — vehicle_id="ALL"이면 전체."""

    action: EmergencyAction
    vehicle_id: str = Field(ALL_VEHICLES, pattern=ID_PATTERN)
    reason: str = Field(min_length=2)
    issued_by: str = UuidStr
    issued_at: AwareDatetime


# ---------------- 중앙관제 ↔ 차량 / 충전기 ----------------
class VehicleTaskMsg(RosModel):
    """/vehicle_task — 중앙관제 → 차량. 차량은 받은 좌표로 이동만 한다."""

    task_id: str = UuidStr
    request_id: str = UuidStr
    vehicle_id: str = VehicleId
    type: TaskType
    target_id: str = Field(pattern=ID_PATTERN)  # CHARGER_01 / PARKING_02
    target_pose: Pose


class VehicleTaskStatusMsg(RosModel):
    """/vehicle_task_status — 차량 → 중앙관제. task_id로 수명주기 추적."""

    task_id: str = UuidStr
    vehicle_id: str = VehicleId
    status: TaskStatus
    progress: float | None = Field(None, ge=0, le=1)
    error_message: str | None = None

    @model_validator(mode="after")
    def _fail_has_reason(self):
        if self.status == TaskStatus.FAILED and not self.error_message:
            raise ValueError("error_message is required when status=FAILED")
        return self


class VehicleCommandKind(StrEnum):
    START_CHARGING = "START_CHARGING"
    STOP_CHARGING = "STOP_CHARGING"


class VehicleCommandMsg(RosModel):
    """/vehicle_command — 중앙관제 → 충전 시뮬레이터."""

    command: VehicleCommandKind
    vehicle_id: str = VehicleId
    charger_id: str = Field(pattern=ID_PATTERN)
    request_id: str = UuidStr
    target_soc: int | None = Field(None, ge=1, le=100)  # START_CHARGING

    @model_validator(mode="after")
    def _start_needs_target(self):
        if self.command == VehicleCommandKind.START_CHARGING and self.target_soc is None:
            raise ValueError("target_soc is required for START_CHARGING")
        return self


class ChargingStatusMsg(RosModel):
    """/charging_status — 충전 시뮬레이터 → 중앙관제."""

    vehicle_id: str = VehicleId
    charger_id: str = Field(pattern=ID_PATTERN)
    soc: float = Field(ge=0, le=100)
    power_kw: float = Field(ge=0)
    charging: bool
    done: bool = False
    energy_kwh: float | None = Field(None, ge=0)


# ---------------- 중앙관제 → FastAPI (1 Hz) ----------------
class VehicleStateItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    vehicle_id: str = VehicleId
    state: VehicleState
    soc: float = Field(ge=0, le=100)
    zone_id: str | None = None
    pose: Pose | None = None
    progress: float | None = Field(None, ge=0, le=1)
    charger_id: str | None = None
    current_task_id: str | None = Field(None, pattern=UUID_PATTERN)
    estimated_completion: AwareDatetime | None = None  # 예상 PARKED 시각
    last_seen_at: AwareDatetime | None = None


class TaskStateItem(BaseModel):
    """중앙관제가 관리하는 작업 현황. FastAPI가 vehicle_tasks에 upsert한다."""

    model_config = ConfigDict(extra="ignore")
    task_id: str = UuidStr
    request_id: str | None = Field(None, pattern=UUID_PATTERN)
    vehicle_id: str = VehicleId
    type: TaskType
    status: TaskStatus
    target_id: str = Field(pattern=ID_PATTERN)
    target_pose: Pose
    progress: float | None = Field(None, ge=0, le=1)
    error_message: str | None = None


class ChargerStateItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    charger_id: str = Field(pattern=ID_PATTERN)
    state: ChargerState
    vehicle_id: str | None = Field(None, pattern=ID_PATTERN)
    power_kw: float | None = Field(None, ge=0)


class RequestStateItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    request_id: str = UuidStr
    vehicle_id: str = VehicleId
    status: ChargeRequestStatus
    planned_charger_id: str | None = None
    planned_start_at: AwareDatetime | None = None
    planned_parked_at: AwareDatetime | None = None
    reason: str | None = Field(None, description="FAILED·거절 사유")


class EventItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    event_id: str = Field(min_length=1, description="중앙관제가 매기는 고유 ID. 재수신 시 중복 저장 방지")
    type: str
    at: AwareDatetime
    vehicle_id: str | None = None
    charger_id: str | None = None
    request_id: str | None = None
    task_id: str | None = None
    payload: dict = Field(default_factory=dict)


class SchedulerInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    queue_length: int = Field(0, ge=0)


class CentralStatusMsg(RosModel):
    """/central_status — 1 Hz. MVP에서는 하나로 유지(커지면 분리)."""

    at: AwareDatetime
    vehicles: list[VehicleStateItem] = Field(default_factory=list)
    tasks: list[TaskStateItem] = Field(default_factory=list)
    chargers: list[ChargerStateItem] = Field(default_factory=list)
    requests: list[RequestStateItem] = Field(default_factory=list)
    events: list[EventItem] = Field(default_factory=list)
    scheduler: SchedulerInfo = Field(default_factory=SchedulerInfo)
    emergency_stop_active: bool = False
