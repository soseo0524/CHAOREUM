from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models as m
import repo
from database import get_db
from deps import CurrentUser, require_user
from errors import ApiError
from schemas.common import ErrorCode, OkResponse
from ros_schemas.messages import ChargingCancelMsg
from schemas.vehicles import VehicleCreate, VehicleOut, VehicleUpdate
from state import ros

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


def _out(v: m.Vehicle) -> VehicleOut:
    return VehicleOut(id=v.id, plate_no=v.plate_no, model=v.model, battery_kwh=v.battery_kwh, max_charge_kw=v.max_charge_kw, assigned=v.ros_vehicle_id is not None, created_at=v.created_at, updated_at=v.updated_at)


def _mine(db: Session, vid: UUID, u: CurrentUser) -> m.Vehicle:
    v = repo.live_vehicle(db, vid)
    if not v or v.owner_id != u.id:
        raise ApiError(404, ErrorCode.NOT_FOUND, "차량을 찾을 수 없습니다.")
    return v


@router.get("", response_model=list[VehicleOut])
def list_vehicles(u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    return [_out(v) for v in repo.live_vehicles(db, u.id)]


@router.post("", response_model=VehicleOut, status_code=201)
def create_vehicle(body: VehicleCreate, u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    if repo.plate_taken(db, body.plate_no):
        raise ApiError(409, ErrorCode.PLATE_DUPLICATED, "이미 등록된 차량번호입니다.")
    v = m.Vehicle(owner_id=u.id, **body.model_dump())
    db.add(v)
    try:
        db.commit()
    except IntegrityError:  # 동시 등록 경쟁: DB 유니크 인덱스가 최종 방어선
        db.rollback()
        raise ApiError(409, ErrorCode.PLATE_DUPLICATED, "이미 등록된 차량번호입니다.")
    try_auto_assign(db, v)
    return _out(v)


def try_auto_assign(db: Session, v: m.Vehicle) -> None:
    """등록 직후 관제 차량 ID 자동 배정. 동시에 같은 ID를 잡으면(유니크 인덱스) 배정 대기로 남긴다."""
    if repo.auto_assign(db, v):
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            db.refresh(v)


@router.get("/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(vehicle_id: UUID, u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    return _out(_mine(db, vehicle_id, u))


@router.patch("/{vehicle_id}", response_model=VehicleOut)
def patch_vehicle(vehicle_id: UUID, body: VehicleUpdate, u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    v = _mine(db, vehicle_id, u)
    f = body.model_dump(exclude_unset=True)
    if "plate_no" in f and repo.plate_taken(db, f["plate_no"], v.id):
        raise ApiError(409, ErrorCode.PLATE_DUPLICATED, "이미 등록된 차량번호입니다.")
    for k, val in f.items():
        setattr(v, k, val)
    v.updated_at = repo.now()
    db.commit()
    return _out(v)


@router.delete("/{vehicle_id}", response_model=OkResponse)
def delete_vehicle(vehicle_id: UUID, u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    """차량과 그 차량의 요청·작업·충전 이력·이벤트를 DB에서 지운다. 진행 중인 요청이 있으면 관제에 취소를 먼저 보낸다."""
    v = _mine(db, vehicle_id, u)
    active = repo.active_request(db, v.id)
    if active and v.ros_vehicle_id:  # 차가 움직이고 있을 수 있으니 관제에 취소 전달(삭제 후에도 관제는 처리)
        ros.publish("/charging/cancel", ChargingCancelMsg(request_id=str(active.id), vehicle_id=v.ros_vehicle_id, requested_by="user"))
    rids = select(m.ChargeRequest.id).where(m.ChargeRequest.vehicle_id == v.id)
    tids = select(m.VehicleTask.id).where(m.VehicleTask.vehicle_id == v.id)
    db.execute(delete(m.Event).where(or_(m.Event.vehicle_id == v.id, m.Event.request_id.in_(rids), m.Event.task_id.in_(tids))))
    db.execute(delete(m.ChargeSession).where(m.ChargeSession.request_id.in_(rids)))
    db.execute(delete(m.VehicleStateRow).where(m.VehicleStateRow.vehicle_id == v.id))
    db.execute(update(m.ChargerStateRow).where(m.ChargerStateRow.assigned_vehicle_id == v.id).values(assigned_vehicle_id=None))
    db.execute(delete(m.VehicleTask).where(m.VehicleTask.vehicle_id == v.id))
    db.execute(delete(m.ChargeRequest).where(m.ChargeRequest.vehicle_id == v.id))
    db.delete(v)
    db.commit()
    return OkResponse()
