"""공통 enum·모델. DB enum(backend/db/schema.sql)과 값이 정확히 같아야 한다."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class StrEnum(str, Enum):
    def __str__(self) -> str:  # JSON·로그에서 값 그대로 출력
        return self.value


# --- enum (세 가지 상태는 서로 다른 enum: 요청 / 차량 / 작업) ---
class AppRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class ProfileStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class ChargeRequestStatus(StrEnum):
    REQUESTED = "REQUESTED"
    ACCEPTED = "ACCEPTED"
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"  # 차량이 PARKED에 도달했을 때
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


ACTIVE_REQUEST_STATUSES = frozenset(
    {
        ChargeRequestStatus.REQUESTED,
        ChargeRequestStatus.ACCEPTED,
        ChargeRequestStatus.SCHEDULED,
        ChargeRequestStatus.IN_PROGRESS,
        ChargeRequestStatus.CANCEL_REQUESTED,
    }
)  # schema.sql의 uq_one_active_charge_request_per_vehicle 조건과 동일


class VehicleState(StrEnum):
    ARRIVED_AT_STATION = "ARRIVED_AT_STATION"
    WAITING = "WAITING"
    ASSIGNED = "ASSIGNED"
    MOVING_TO_CHARGER = "MOVING_TO_CHARGER"
    ARRIVED_AT_CHARGER = "ARRIVED_AT_CHARGER"
    CHARGING = "CHARGING"
    CHARGE_DONE = "CHARGE_DONE"
    MOVING_TO_PARKING = "MOVING_TO_PARKING"
    PARKED = "PARKED"
    MOVING_TO_EXIT = "MOVING_TO_EXIT"  # 출차: 출구 구역으로 이동 중
    EXITED = "EXITED"  # 출차: 출구 구역 도착(주차장을 나감)
    FAULT = "FAULT"
    # OFFLINE은 enum이 아니라 last_seen_at 5초 초과로 계산한 파생값(online=false)


class ExitStatus(StrEnum):
    """출차 요청 상태(충전 요청과 별개). 차량당 진행 중(REQUESTED·IN_PROGRESS) 출차는 1개."""

    REQUESTED = "REQUESTED"  # 서버가 관제에 전달함
    IN_PROGRESS = "IN_PROGRESS"  # 관제가 받아 차량이 출구로 이동 중
    COMPLETED = "COMPLETED"  # 출구 구역 도착
    FAILED = "FAILED"


ACTIVE_EXIT_STATUSES = frozenset({ExitStatus.REQUESTED, ExitStatus.IN_PROGRESS})  # schema.sql uq_one_active_exit_per_vehicle 조건과 동일


class TaskStatus(StrEnum):
    CREATED = "CREATED"
    ACCEPTED = "ACCEPTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskType(StrEnum):
    MOVE_TO_CHARGER = "MOVE_TO_CHARGER"
    MOVE_TO_PARKING = "MOVE_TO_PARKING"


class ChargerState(StrEnum):
    AVAILABLE = "AVAILABLE"
    IN_USE = "IN_USE"
    MAINTENANCE = "MAINTENANCE"
    FAULT = "FAULT"


class ParkingZoneKind(StrEnum):
    WAITING = "WAITING"
    CHARGING = "CHARGING"
    PARKING = "PARKING"


class ErrorCode(StrEnum):
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    ACTIVE_REQUEST_EXISTS = "ACTIVE_REQUEST_EXISTS"  # 409
    VEHICLE_NOT_ASSIGNED = "VEHICLE_NOT_ASSIGNED"  # 422: ros_vehicle_id 미배정
    CONSENT_REQUIRED = "CONSENT_REQUIRED"  # 403: 위임 동의 없음
    DEADLINE_INFEASIBLE = "DEADLINE_INFEASIBLE"  # 422: 희망 완료 시각 불가
    REQUEST_NOT_MODIFIABLE = "REQUEST_NOT_MODIFIABLE"  # 409: 이미 주행 중 등
    PLATE_DUPLICATED = "PLATE_DUPLICATED"  # 409
    ROS_ID_DUPLICATED = "ROS_ID_DUPLICATED"  # 409
    HAS_ACTIVE_WORK = "HAS_ACTIVE_WORK"  # 409: 탈퇴/삭제 불가
    PARKING_ZONE_UNAVAILABLE = "PARKING_ZONE_UNAVAILABLE"  # 409: 선택한 자리가 이미 선정됨
    CENTRAL_UNAVAILABLE = "CENTRAL_UNAVAILABLE"  # 503: 중앙관제 응답 없음
    EXIT_NOT_ALLOWED = "EXIT_NOT_ALLOWED"  # 409: 지금 상태에서는 출차 불가(충전 완료·주차 이동·주차 완료에서만. 충전 중 불가)
    EXIT_IN_PROGRESS = "EXIT_IN_PROGRESS"  # 409: 이미 출차 진행 중
    VEHICLE_EXITED = "VEHICLE_EXITED"  # 409: 출차 중·출차 완료 차량은 충전 요청 불가(관제가 출차 차량을 다시 배차하지 않음)


# --- 공통 모델 ---
class ApiModel(BaseModel):
    """모든 스키마의 기반. ORM 객체에서 바로 변환 가능, 알 수 없는 필드는 요청에서 거부."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ErrorResponse(ApiModel):
    code: ErrorCode
    message: str = Field(description="사용자에게 보여줄 한국어 메시지")
    details: dict[str, Any] | None = None


class Pose(ApiModel):
    x: float
    y: float
    yaw: float


T = TypeVar("T")


class Page(ApiModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class PageQuery(BaseModel):
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class OkResponse(ApiModel):
    ok: bool = True


__all__ = [n for n in dir() if not n.startswith("_")]
