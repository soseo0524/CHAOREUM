from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from deps import CurrentUser, require_user
from schemas.parking_map import AreasOut
from services import parking_areas

router = APIRouter(prefix="/parking-zones", tags=["parking-zones"])


@router.get("/areas", response_model=AreasOut)
def areas(u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    """전체 지도(02.02)용. 구역(A·B·C)별 빈자리 수·가득 참 여부·미니 현황(자리별 상태)."""
    return parking_areas(db, u.id)

