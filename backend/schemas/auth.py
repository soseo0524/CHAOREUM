"""GET /me, PATCH /me, POST /consents, DELETE /me."""
from __future__ import annotations

from pydantic import AwareDatetime, Field

from .common import ApiModel, AppRole, ProfileStatus
from uuid import UUID


class ProfileOut(ApiModel):
    id: UUID
    email: str | None = None  # auth.users에서 가져옴
    name: str | None
    phone: str | None
    app_role: AppRole
    status: ProfileStatus
    consent_agreed: bool = Field(description="현재 유효한(철회되지 않은) 위임 동의 존재 여부")
    consent_version: str | None = None


class ProfileUpdate(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    phone: str | None = Field(None, pattern=r"^[0-9+\-]{8,20}$")


class ConsentCreate(ApiModel):
    version: str = Field(min_length=1, max_length=32, description="동의 문구 버전")


class ConsentOut(ApiModel):
    id: UUID
    version: str
    agreed_at: AwareDatetime
    revoked_at: AwareDatetime | None = None


class WithdrawRequest(ApiModel):
    """DELETE /me 본문(선택). 재확인용."""

    confirm: bool = Field(description="true여야 탈퇴 진행")
