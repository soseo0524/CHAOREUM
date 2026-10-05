import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import models as m
import repo
from database import get_db
from deps import CurrentUser, current_user, require_user
from errors import ApiError
from schemas.auth import ConsentCreate, ConsentOut, ProfileOut, ProfileUpdate, WithdrawRequest
from schemas.common import ErrorCode, OkResponse
from schemas.status import ChargeSessionOut, MeStatusResponse, NotificationOut, NotificationSettings, NotificationSettingsPatch, PushTokenCreate
from services import cost_of, vehicle_status

router = APIRouter(tags=["me"])


def _profile_out(db: Session, p: m.Profile, email: str | None = None) -> ProfileOut:
    c = repo.current_consent(db, p.id)
    return ProfileOut(id=p.id, email=email, name=p.name, phone=p.phone, app_role=p.app_role, status=p.status, consent_agreed=c is not None, consent_version=c.version if c else None)


@router.get("/me", response_model=ProfileOut)
def get_me(u: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    return _profile_out(db, repo.ensure_profile(db, u.id, u.role), u.email)


@router.patch("/me", response_model=ProfileOut)
def patch_me(body: ProfileUpdate, u: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    p = repo.ensure_profile(db, u.id, u.role)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    p.updated_at = repo.now()
    db.commit()
    return _profile_out(db, p, u.email)


@router.post("/consents", response_model=ConsentOut, status_code=201)
def post_consent(body: ConsentCreate, u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    c = m.Consent(user_id=u.id, version=body.version, agreed_at=repo.now())
    db.add(c)
    db.commit()
    return ConsentOut.model_validate(c)


@router.get("/me/status", response_model=MeStatusResponse)
def me_status(u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    vs = [vehicle_status(db, v) for v in repo.live_vehicles(db, u.id)]
    return MeStatusResponse(server_time=repo.now(), vehicles=vs, empty_reason=None if vs else "NO_VEHICLE")


@router.get("/me/sessions", response_model=list[ChargeSessionOut])
def me_sessions(u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    """충전 이력(12). 내 차량의 충전 세션, 최신순."""
    vids = {v.id for v in repo.live_vehicles(db, u.id)}
    if not vids:
        return []
    rows = db.execute(select(m.ChargeSession, m.ChargeRequest.vehicle_id).join(m.ChargeRequest, m.ChargeRequest.id == m.ChargeSession.request_id)
                      .where(m.ChargeRequest.vehicle_id.in_(vids)).order_by(m.ChargeSession.start_at.desc()).limit(100)).all()
    return [ChargeSessionOut(id=s.id, request_id=s.request_id, vehicle_id=vid, charger_id=s.charger_id, start_at=s.start_at, end_at=s.end_at, start_soc=s.start_soc, end_soc=s.end_soc, energy_kwh=float(s.energy_kwh) if s.energy_kwh is not None else None, unit_price_won=s.unit_price_won, cost_won=cost_of(float(s.energy_kwh), s.unit_price_won) if s.energy_kwh is not None else None) for s, vid in rows]


@router.get("/me/notifications", response_model=list[NotificationOut])
def me_notifications(u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(m.Notification).where(m.Notification.user_id == u.id).order_by(m.Notification.created_at.desc()).limit(100))
    return [NotificationOut.model_validate(n) for n in rows]


@router.delete("/me", response_model=OkResponse)
def withdraw(body: WithdrawRequest, u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    """U-09 절차. auth.users 삭제는 Supabase 연결 단계에서 추가(현재는 DB 쪽만)."""
    if not body.confirm:
        raise ApiError(422, ErrorCode.VALIDATION_ERROR, "탈퇴 확인이 필요합니다.")
    vehicles = repo.live_vehicles(db, u.id)
    if any(repo.active_request(db, v.id) for v in vehicles):
        raise ApiError(409, ErrorCode.HAS_ACTIVE_WORK, "진행 중인 충전 요청이 있어 탈퇴할 수 없습니다.")
    db.execute(delete(m.PushToken).where(m.PushToken.user_id == u.id))
    db.execute(delete(m.Notification).where(m.Notification.user_id == u.id))
    for v in vehicles:  # 차량은 soft delete + 소유자 해제(이력은 개인정보 없이 유지)
        v.deleted_at, v.owner_id = repo.now(), None
    db.flush()
    db.execute(delete(m.Consent).where(m.Consent.user_id == u.id))
    db.execute(delete(m.Profile).where(m.Profile.id == u.id))
    db.commit()
    _delete_auth_user(u.id)
    return OkResponse()


def _delete_auth_user(uid: uuid.UUID) -> None:
    """Supabase auth.users 삭제(Admin API). SUPABASE_URL·SERVICE_ROLE_KEY가 없으면(개발) 건너뛴다. 실패해도 탈퇴 응답은 막지 않는다."""
    from config import settings

    if not (settings.supabase_url and settings.supabase_service_key):
        return
    import urllib.request

    req = urllib.request.Request(f"{settings.supabase_url}/auth/v1/admin/users/{uid}", method="DELETE",
                                 headers={"apikey": settings.supabase_service_key, "Authorization": f"Bearer {settings.supabase_service_key}"})
    try:
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:  # noqa: BLE001  (로그만 남기는 자리. 운영에서는 재시도 큐가 필요)
        pass


# ---------- 알림 설정 · 푸시 토큰 · 읽음 처리 ----------
def _prefs(p: m.Profile) -> NotificationSettings:
    return NotificationSettings(**(p.notification_prefs or {}))


@router.get("/me/notification-settings", response_model=NotificationSettings)
def get_notification_settings(u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    return _prefs(repo.ensure_profile(db, u.id, u.role))


@router.patch("/me/notification-settings", response_model=NotificationSettings)
def patch_notification_settings(body: NotificationSettingsPatch, u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    p = repo.ensure_profile(db, u.id, u.role)
    merged = {**_prefs(p).model_dump(), **body.model_dump(exclude_none=True)}
    p.notification_prefs, p.updated_at = merged, repo.now()  # JSON 컬럼은 새 객체를 넣어야 변경이 감지된다
    db.commit()
    return _prefs(p)


@router.post("/me/push-tokens", response_model=OkResponse, status_code=201)
def register_push_token(body: PushTokenCreate, u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    repo.ensure_profile(db, u.id, u.role)
    row = db.scalar(select(m.PushToken).where(m.PushToken.expo_push_token == body.token))
    if row:  # 같은 기기에 다른 계정이 로그인하면 소유자를 옮긴다
        row.user_id, row.platform, row.enabled, row.last_seen_at, row.updated_at = u.id, body.platform, True, repo.now(), repo.now()
    else:
        db.add(m.PushToken(user_id=u.id, expo_push_token=body.token, platform=body.platform))
    db.commit()
    return OkResponse()


@router.delete("/me/push-tokens", response_model=OkResponse)
def delete_push_token(body: PushTokenCreate, u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    """로그아웃 시 이 기기 토큰 삭제."""
    db.execute(delete(m.PushToken).where(m.PushToken.expo_push_token == body.token, m.PushToken.user_id == u.id))
    db.commit()
    return OkResponse()


@router.post("/me/notifications/{notification_id}/read", response_model=NotificationOut)
def read_notification(notification_id: uuid.UUID, u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    n = db.get(m.Notification, notification_id)
    if not n or n.user_id != u.id:
        raise ApiError(404, ErrorCode.NOT_FOUND, "알림을 찾을 수 없습니다.")
    if n.read_at is None:
        n.read_at = repo.now()
        db.commit()
    return NotificationOut.model_validate(n)
