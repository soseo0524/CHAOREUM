from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models as m
import repo
from database import get_db
from deps import CurrentUser, require_user
from errors import ApiError
from schemas.common import ErrorCode, OkResponse
from schemas.vehicles import VehicleCreate, VehicleOut, VehicleUpdate

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
    return _out(v)


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
    v = _mine(db, vehicle_id, u)
    if repo.active_request(db, v.id):
        raise ApiError(409, ErrorCode.HAS_ACTIVE_WORK, "진행 중인 충전 요청이 있어 삭제할 수 없습니다.")
    v.deleted_at = repo.now()
    db.commit()
    return OkResponse()
