from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from deps import CurrentUser, require_user
from schemas.charge_requests import ParkingZoneOut
from schemas.parking_map import ParkingMapOut
from services import parking_map, zone_availability

router = APIRouter(prefix="/parking-zones", tags=["parking-zones"])


@router.get("", response_model=list[ParkingZoneOut])
def list_zones(_: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    """주차 구역 선택 화면(U-04)용. 구역별 남은 자리를 돌려준다."""
    return [ParkingZoneOut(id=z.id, name=z.name, capacity=z.capacity, available=a, is_available=a > 0) for z, a in zone_availability(db)]


@router.get("/map", response_model=ParkingMapOut)
def zone_map(row: int = Query(0, ge=0, description="내 위치(맨 앞 줄)"), depth: int = Query(5, ge=1, le=11, description="앞쪽으로 보여줄 줄 수"),
             selected: str | None = Query(None, description="지금 고르는 자리(PARKING_nn). 이미 선정됐으면 selected_ok=false"),
             u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    """1인칭 지도용. 내 위치(row)에서 앞으로 depth줄의 양옆 칸 번호와 상태(TAKEN/FREE/MINE)를 돌려준다."""
    return parking_map(db, u.id, row, depth, selected)
