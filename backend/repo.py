"""자주 쓰는 DB 조회·기록. 라우터는 이 함수들과 ORM 쿼리를 함께 쓴다."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

import models as m
from schemas.common import ACTIVE_REQUEST_STATUSES, AppRole


def now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_profile(db: Session, uid: uuid.UUID, role: AppRole) -> m.Profile:
    p = db.get(m.Profile, uid)
    if p is None:  # Supabase에서는 가입 트리거가 만든다. 없을 때만 보충
        p = m.Profile(id=uid, app_role=role)
        db.add(p)
        db.commit()
    return p


def current_consent(db: Session, uid: uuid.UUID) -> m.Consent | None:
    return db.scalars(select(m.Consent).where(m.Consent.user_id == uid, m.Consent.revoked_at.is_(None)).order_by(m.Consent.agreed_at.desc())).first()


def live_vehicles(db: Session, owner: uuid.UUID | None = None) -> list[m.Vehicle]:
    q = select(m.Vehicle).where(m.Vehicle.deleted_at.is_(None)).order_by(m.Vehicle.created_at)
    if owner is not None:
        q = q.where(m.Vehicle.owner_id == owner)
    return list(db.scalars(q))


def live_vehicle(db: Session, vid: uuid.UUID) -> m.Vehicle | None:
    v = db.get(m.Vehicle, vid)
    return v if v and v.deleted_at is None else None


def vehicle_by_ros(db: Session, ros_id: str) -> m.Vehicle | None:
    return db.scalars(select(m.Vehicle).where(m.Vehicle.ros_vehicle_id == ros_id, m.Vehicle.deleted_at.is_(None))).first()


def plate_taken(db: Session, plate: str, except_id: uuid.UUID | None = None) -> bool:
    q = select(m.Vehicle.id).where(m.Vehicle.plate_no == plate, m.Vehicle.deleted_at.is_(None))
    if except_id:
        q = q.where(m.Vehicle.id != except_id)
    return db.scalars(q).first() is not None


def active_request(db: Session, vehicle_id: uuid.UUID) -> m.ChargeRequest | None:
    return db.scalars(select(m.ChargeRequest).where(m.ChargeRequest.vehicle_id == vehicle_id, m.ChargeRequest.status.in_(ACTIVE_REQUEST_STATUSES))).first()


def log_audit(db: Session, admin: uuid.UUID, action: str, entity_type: str, entity_id: Any, reason: str, before=None, after=None) -> int:
    row = m.AuditLog(admin_id=admin, action=action, entity_type=entity_type, entity_id=str(entity_id), reason=reason, before_data=before, after_data=after)
    db.add(row)
    db.flush()
    return row.id


def get_setting(db: Session, key: str, default=None):
    s = db.get(m.Setting, key)
    return s.value if s else default


def set_setting(db: Session, key: str, value, admin: uuid.UUID | None = None):
    s = db.get(m.Setting, key)
    if s is None:
        db.add(m.Setting(key=key, value=value, updated_by=admin))
    else:
        s.value, s.updated_by, s.updated_at = value, admin, now()
