"""사용자 차량 CRUD. ros_vehicle_id는 관리자만 배정(admin.py)."""
from __future__ import annotations

from uuid import UUID

from pydantic import AwareDatetime, Field

from .common import ApiModel

PLATE_PATTERN = r"^[0-9가-힣A-Za-z ]{4,12}$"


class VehicleCreate(ApiModel):
    plate_no: str = Field(pattern=PLATE_PATTERN)
    model: str | None = Field(None, max_length=60)
    battery_kwh: float = Field(gt=0, le=500)
    max_charge_kw: float = Field(gt=0, le=500)


class VehicleUpdate(ApiModel):
    plate_no: str | None = Field(None, pattern=PLATE_PATTERN)
    model: str | None = Field(None, max_length=60)
    battery_kwh: float | None = Field(None, gt=0, le=500)
    max_charge_kw: float | None = Field(None, gt=0, le=500)


class VehicleOut(ApiModel):
    id: UUID
    plate_no: str
    model: str | None
    battery_kwh: float
    max_charge_kw: float
    assigned: bool = Field(description="ros_vehicle_id 배정 여부. false면 충전 요청 불가('배정 대기')")
    created_at: AwareDatetime
    updated_at: AwareDatetime
    # ros_vehicle_id는 사용자에게 노출하지 않는다(관리자 응답에만 포함).
