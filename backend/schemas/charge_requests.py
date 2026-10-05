"""POST /charge-requests, PATCH /charge-requests/{id}.

desired_finish_at = 사용자가 'PARKED 상태가 되길 원하는 시각'.
스케줄러는 대기 + 충전기 이동 + 충전 + 주차구역 이동 ≤ desired_finish_at 으로 계산한다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .common import ApiModel, ChargeRequestStatus, StrEnum


class FeasibilityReason(StrEnum):
    OK = "OK"
    DEADLINE_TOO_EARLY = "DEADLINE_TOO_EARLY"  # 가장 빠른 경우에도 불가
    NO_CHARGER_CAPACITY = "NO_CHARGER_CAPACITY"  # 해당 시간대 충전기 부족
    CHARGERS_UNAVAILABLE = "CHARGERS_UNAVAILABLE"  # 점검/고장
    CENTRAL_UNAVAILABLE = "CENTRAL_UNAVAILABLE"  # 중앙관제 상태 미수신


class TimeBreakdown(ApiModel):
    """초 단위 예상 소요 시간."""

    wait_s: int = Field(ge=0)
    move_to_charger_s: int = Field(ge=0)
    charge_s: int = Field(ge=0)
    move_to_parking_s: int = Field(ge=0)


class Feasibility(ApiModel):
    feasible: bool
    reason: FeasibilityReason
    estimated_parked_at: AwareDatetime | None = Field(
        None, description="예상 주차완료(PARKED) 시각"
    )
    earliest_parked_at: AwareDatetime | None = Field(
        None, description="불가 시 제안하는 가장 빠른 PARKED 시각"
    )
    breakdown: TimeBreakdown | None = None
    message: str | None = None


def _must_be_future(v: datetime) -> datetime:
    if v <= datetime.now(timezone.utc):
        raise ValueError("desired_finish_at must be in the future")
    return v


class ChargeRequestCreate(ApiModel):
    vehicle_id: UUID
    desired_finish_at: AwareDatetime
    target_soc: int = Field(80, ge=1, le=100)
    min_soc: int = Field(0, ge=0, le=100)
    parking_zone_id: str | None = Field(None, description="고른 주차 구역 id(PARKING 종류). 비우면 자동 배정")
    dry_run: bool = Field(
        False, description="true면 저장·ROS 발행 없이 feasibility만 계산(U-03 미리보기)"
    )

    @model_validator(mode="after")
    def _check(self):
        _must_be_future(self.desired_finish_at)
        if self.min_soc > self.target_soc:
            raise ValueError("min_soc must be <= target_soc")
        return self


class ChargeRequestOut(ApiModel):
    id: UUID
    vehicle_id: UUID
    desired_finish_at: AwareDatetime
    target_soc: int
    min_soc: int
    parking_zone_id: str | None = None
    status: ChargeRequestStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime
    cancel_requested_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    queue_position: int | None = Field(None, ge=1, description="대기 순번(1=다음 차례). REQUESTED·ACCEPTED·SCHEDULED일 때만. GET /me/status에서만 채운다")
    estimated_wait_min: int | None = Field(None, ge=0, description="앞선 대기 대수 × 평균 소요 분(추정)")


class ChargeRequestCreateResponse(ApiModel):
    """201(생성) 또는 200(dry_run). dry_run이면 request=None.

    feasible=false 이고 dry_run=false 이면 저장하지 않고 422 DEADLINE_INFEASIBLE
    (ErrorResponse.details.feasibility 에 이 Feasibility를 담는다).
    """

    request: ChargeRequestOut | None
    feasibility: Feasibility


class ChargeRequestPatch(ApiModel):
    """수정(시각·SOC·구역) 또는 취소 중 하나. 수정은 REQUESTED/ACCEPTED/SCHEDULED에서만."""

    desired_finish_at: AwareDatetime | None = None
    target_soc: int | None = Field(None, ge=1, le=100)
    min_soc: int | None = Field(None, ge=0, le=100)
    parking_zone_id: str | None = Field(None, description="주차 구역 변경(자동 배정으로 되돌리는 기능은 없음)")
    cancel: bool | None = Field(None, description="true면 취소 요청(→ CANCEL_REQUESTED)")

    @model_validator(mode="after")
    def _check(self):
        edits = {
            k: getattr(self, k)
            for k in ("desired_finish_at", "target_soc", "min_soc", "parking_zone_id")
            if getattr(self, k) is not None
        }
        if self.cancel is False:
            raise ValueError("cancel must be true or omitted")
        if self.cancel and edits:
            raise ValueError("cancel cannot be combined with edits")
        if not self.cancel and not edits:
            raise ValueError("nothing to update")
        if self.desired_finish_at is not None:
            _must_be_future(self.desired_finish_at)
        if (
            self.min_soc is not None
            and self.target_soc is not None
            and self.min_soc > self.target_soc
        ):
            raise ValueError("min_soc must be <= target_soc")
        return self


class ChargeRequestPatchResponse(ApiModel):
    request: ChargeRequestOut
    feasibility: Feasibility | None = None  # 수정 시 재계산 결과


class ParkingZoneOut(ApiModel):
    """주차 구역 선택 화면용. available = capacity - (주차 중 + 예약된 요청)."""

    id: str
    name: str
    capacity: int
    available: int
    is_available: bool
