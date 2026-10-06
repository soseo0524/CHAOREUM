from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from deps import CurrentUser, require_user
from schemas.charge_requests import ParkingZoneOut
from errors import ApiError
from schemas.common import ErrorCode
from schemas.parking_map import AreaDetailOut, AreasOut
from services import parking_area_detail, parking_areas, zone_availability

router = APIRouter(prefix="/parking-zones", tags=["parking-zones"])


@router.get("", response_model=list[ParkingZoneOut])
def list_zones(_: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    """주차 구역 선택 화면(U-04)용. 구역별 남은 자리를 돌려준다."""
    return [ParkingZoneOut(id=z.id, name=z.name, capacity=z.capacity, available=a, is_available=a > 0) for z, a in zone_availability(db)]


@router.get("/areas", response_model=AreasOut)
def areas(u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    """전체 지도(02.02)용. 구역(A·B·C)별 빈자리 수·가득 참 여부·미니 현황(자리별 상태)."""
    return parking_areas(db, u.id)


@router.get("/areas/{area_id}", response_model=AreaDetailOut)
def area_detail(area_id: str, selected: str | None = Query(None, description="지금 고르는 자리(PARKING_nn). 이미 선정됐으면 selected_ok=false"),
                u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    """구역 안 맵(02.03·02-A.02)용. 자리별 상태(TAKEN/FREE/MINE)와 칸 위치(row, col)."""
    out = parking_area_detail(db, u.id, area_id, selected)
    if out is None:
        raise ApiError(404, ErrorCode.NOT_FOUND, "구역을 찾을 수 없습니다.")
    return out
