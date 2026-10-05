"""관리자 API. 변경 작업은 모두 reason 필수(audit_logs)."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .charge_requests import ChargeRequestOut
from .common import (
    ApiModel,
    ChargeRequestStatus,
    ChargerState,
    StrEnum,
    TaskStatus,
    TaskType,
    VehicleState,
)
from .status import CurrentTask

Reason = Field(min_length=2, max_length=500, description="감사 로그용 사유(필수)")
ROS_ID_PATTERN = r"^[A-Za-z0-9_]{1,32}$"  # 예: CAR_01


class AdminOverview(ApiModel):
    server_time: AwareDatetime
    vehicles_by_state: dict[VehicleState, int]
    vehicles_offline: int
    chargers_by_state: dict[ChargerState, int]
    active_requests: int
    queue_length: int
    fault_count: int
    emergency_stop_active: bool
    central_online: bool


class AdminOwner(ApiModel):
    id: UUID
    name: str | None


class AdminVehicleOut(ApiModel):
    id: UUID
    ros_vehicle_id: str | None
    plate_no: str
    model: str | None
    battery_kwh: float
    max_charge_kw: float
    owner: AdminOwner | None
    state: VehicleState | None
    online: bool
    soc: float | None
    zone_id: str | None
    charger_id: str | None
    current_task: CurrentTask | None
    active_request: ChargeRequestOut | None
    last_seen_at: AwareDatetime | None


class AdminVehiclePatch(ApiModel):
    """ros_vehicle_id 배정(문자열)·해제(null). 필드를 반드시 명시해야 한다."""

    ros_vehicle_id: str | None = Field(None, pattern=ROS_ID_PATTERN)
    reason: str = Reason

    @model_validator(mode="after")
    def _explicit(self):
        if "ros_vehicle_id" not in self.model_fields_set:
            raise ValueError("ros_vehicle_id must be given (null to release)")
        return self


class ChargerOut(ApiModel):
    id: str
    name: str
    max_power_kw: float
    state: ChargerState | None
    maintenance: bool = Field(False, description="IN_USE 중 점검 예약(현재 작업 종료 후 점검 진입)")
    vehicle_id: UUID | None = Field(None, description="사용 중인 차량")
    power_kw: float | None
    updated_at: AwareDatetime | None


class ChargerPatch(ApiModel):
    """점검 모드 전환(MAINTENANCE↔AVAILABLE)과 출력 제한."""

    state: ChargerState | None = None
    max_power_kw: float | None = Field(None, gt=0)
    reason: str = Reason

    @model_validator(mode="after")
    def _check(self):
        if self.state not in (None, ChargerState.AVAILABLE, ChargerState.MAINTENANCE):
            raise ValueError("state can only be AVAILABLE or MAINTENANCE")
        if self.state is None and self.max_power_kw is None:
            raise ValueError("nothing to update")
        return self


class QueueItem(ApiModel):
    request: ChargeRequestOut
    vehicle_id: UUID
    plate_no: str
    position: int
    planned_charger_id: str | None
    planned_start_at: AwareDatetime | None
    planned_parked_at: AwareDatetime | None


class QueueResponse(ApiModel):
    items: list[QueueItem]


class QueueAction(StrEnum):
    CANCEL = "cancel"
    RETRY = "retry"
    REASSIGN = "reassign"  # /admin/command 토픽과 동일


class QueueActionRequest(ApiModel):
    request_id: UUID
    action: QueueAction
    charger_id: str | None = Field(None, description="reassign일 때 필수")
    reason: str = Reason

    @model_validator(mode="after")
    def _check(self):
        if (self.action == QueueAction.REASSIGN) != (self.charger_id is not None):
            raise ValueError("charger_id is required only for reassign")
        return self


class TaskCancelRequest(ApiModel):
    reason: str = Reason


class EmergencyStopAction(StrEnum):
    STOP = "STOP"
    RELEASE = "RELEASE"


class EmergencyStopRequest(ApiModel):
    action: EmergencyStopAction
    reason: str = Reason


class EmergencyStopState(ApiModel):
    active: bool
    changed_at: AwareDatetime | None = None


class AdminActionResponse(ApiModel):
    ok: bool = True
    audit_log_id: int | UUID | None = None


class EventsQuery(ApiModel):
    type: str | None = None
    vehicle_id: UUID | None = None
    charger_id: str | None = None
    request_id: UUID | None = None
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None
    limit: int = Field(100, ge=1, le=500)
    offset: int = Field(0, ge=0)


class EventOut(ApiModel):
    id: int
    at: AwareDatetime
    type: str
    vehicle_id: UUID | None
    charger_id: str | None
    request_id: UUID | None
    task_id: UUID | None
    payload: dict[str, Any]


class SettingOut(ApiModel):
    key: str
    value: Any
    updated_at: AwareDatetime


class SettingsPatch(ApiModel):
    values: dict[str, Any] = Field(min_length=1)
    reason: str = Reason
