from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models as m
import repo
from database import get_db
from deps import CurrentUser, require_user
from errors import ApiError
from ros_schemas.messages import ChargingCancelMsg, ChargingRequestMsg
from schemas.charge_requests import ChargeRequestCreate, ChargeRequestCreateResponse, ChargeRequestPatch, ChargeRequestPatchResponse
from schemas.common import ChargeRequestStatus as S, ErrorCode
from services import estimate, notify_queue_changes, queue_order, request_out, zone_availability
from state import dispatch, ros

router = APIRouter(prefix="/charge-requests", tags=["charge-requests"])


def _check_zone(db: Session, zone_id: str | None, current: str | None = None) -> None:
    """고른 주차 구역이 PARKING 종류이고 자리가 있는지 확인. 내 요청이 이미 잡은 구역이면 통과."""
    if zone_id is None or zone_id == current:
        return
    found = zone_availability(db, zone_id)
    if not found:
        raise ApiError(422, ErrorCode.VALIDATION_ERROR, "존재하지 않는 주차 구역입니다.")
    if found[0][1] <= 0:
        raise ApiError(409, ErrorCode.PARKING_ZONE_UNAVAILABLE, "이미 선정된 자리입니다. 다른 자리를 고르거나 자동 배정을 사용해 주세요.")
EDITABLE = {S.REQUESTED, S.ACCEPTED, S.SCHEDULED}


def _ros_request(r: m.ChargeRequest, v: m.Vehicle) -> ChargingRequestMsg:
    return ChargingRequestMsg(request_id=str(r.id), vehicle_id=v.ros_vehicle_id, desired_finish_at=r.desired_finish_at, target_soc=r.target_soc, min_soc=r.min_soc, battery_kwh=v.battery_kwh, max_charge_kw=v.max_charge_kw, parking_zone_id=r.parking_zone_id)


@router.post("", response_model=ChargeRequestCreateResponse)
def create(body: ChargeRequestCreate, resp: Response, u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    v = repo.live_vehicle(db, body.vehicle_id)
    if not v or v.owner_id != u.id:
        raise ApiError(404, ErrorCode.NOT_FOUND, "차량을 찾을 수 없습니다.")
    if v.ros_vehicle_id is None:
        raise ApiError(422, ErrorCode.VEHICLE_NOT_ASSIGNED, "관리자가 차량을 배정하는 중입니다(배정 대기).")
    if repo.current_consent(db, u.id) is None:
        raise ApiError(403, ErrorCode.CONSENT_REQUIRED, "위임 동의가 필요합니다.")
    if not body.dry_run and repo.active_request(db, v.id):
        raise ApiError(409, ErrorCode.ACTIVE_REQUEST_EXISTS, "이미 진행 중인 충전 요청이 있습니다.")
    _check_zone(db, body.parking_zone_id)
    fz = estimate(db, v, body.desired_finish_at, body.target_soc)
    if body.dry_run:
        return ChargeRequestCreateResponse(request=None, feasibility=fz)
    if not fz.feasible:
        raise ApiError(422, ErrorCode.DEADLINE_INFEASIBLE, fz.message or "요청한 시각에 완료할 수 없습니다.", {"feasibility": fz.model_dump(mode="json")})
    r = m.ChargeRequest(vehicle_id=v.id, desired_finish_at=body.desired_finish_at, target_soc=body.target_soc, min_soc=body.min_soc, parking_zone_id=body.parking_zone_id)
    db.add(r)
    try:
        db.commit()
    except IntegrityError:  # 동시 요청 경쟁: partial unique index
        db.rollback()
        raise ApiError(409, ErrorCode.ACTIVE_REQUEST_EXISTS, "이미 진행 중인 충전 요청이 있습니다.")
    ros.publish("/charging/request", _ros_request(r, v))  # 커밋 후 발행. 발행 실패 시 재발행 정책은 ROS 연동 단계에서
    resp.status_code = 201
    return ChargeRequestCreateResponse(request=request_out(r), feasibility=fz)


def _mine(db: Session, rid: UUID, u: CurrentUser):
    r = db.get(m.ChargeRequest, rid)
    v = db.get(m.Vehicle, r.vehicle_id) if r else None
    if not r or not v or v.owner_id != u.id:
        raise ApiError(404, ErrorCode.NOT_FOUND, "충전 요청을 찾을 수 없습니다.")
    return r, v


@router.patch("/{request_id}", response_model=ChargeRequestPatchResponse)
def patch(request_id: UUID, body: ChargeRequestPatch, u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    r, v = _mine(db, request_id, u)
    if body.cancel:
        if r.status not in {S.REQUESTED, S.ACCEPTED, S.SCHEDULED, S.IN_PROGRESS}:
            raise ApiError(409, ErrorCode.REQUEST_NOT_MODIFIABLE, "취소할 수 없는 상태입니다.")
        before, outbox = queue_order(db), []
        r.status, r.cancel_requested_at, r.updated_at = S.CANCEL_REQUESTED, repo.now(), repo.now()
        db.flush()
        notify_queue_changes(db, before, outbox)  # 내가 빠지면 뒤 순번이 당겨진다
        db.commit()
        dispatch(db, outbox)
        ros.publish("/charging/cancel", ChargingCancelMsg(request_id=str(r.id), vehicle_id=v.ros_vehicle_id, requested_by="user"))
        return ChargeRequestPatchResponse(request=request_out(r))
    if r.status not in EDITABLE:
        raise ApiError(409, ErrorCode.REQUEST_NOT_MODIFIABLE, "이미 진행 중이라 수정할 수 없습니다. 취소 후 다시 요청해 주세요.")
    new = {k: getattr(body, k) for k in ("desired_finish_at", "target_soc", "min_soc", "parking_zone_id") if getattr(body, k) is not None}
    ms, ts_ = new.get("min_soc", r.min_soc), new.get("target_soc", r.target_soc)
    if ms > ts_:
        raise ApiError(422, ErrorCode.VALIDATION_ERROR, "min_soc는 target_soc 이하여야 합니다.")
    _check_zone(db, new.get("parking_zone_id"), r.parking_zone_id)
    fz = estimate(db, v, new.get("desired_finish_at", r.desired_finish_at), ts_)
    if not fz.feasible:
        raise ApiError(422, ErrorCode.DEADLINE_INFEASIBLE, fz.message or "요청한 시각에 완료할 수 없습니다.", {"feasibility": fz.model_dump(mode="json")})
    for k, val in new.items():
        setattr(r, k, val)
    r.updated_at = repo.now()
    db.commit()
    ros.publish("/charging/request", _ros_request(r, v))  # 같은 request_id 재발행 = 수정(중앙관제는 request_id 기준 upsert)
    return ChargeRequestPatchResponse(request=request_out(r), feasibility=fz)
