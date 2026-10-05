"""개발 전용(ROS_MODE=mock). 실제 관제 없이 앱을 시험하는 시뮬레이터 호출."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import repo
from database import get_db
from deps import CurrentUser, require_user
from dev_sim import run_simulation, start_background
from errors import ApiError
from schemas.common import ErrorCode
from state import ros

router = APIRouter(prefix="/dev", tags=["dev"])


@router.post("/simulate")
def simulate(step_s: float = Query(3.0, ge=0, le=60), wait: bool = False, u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    """내 차량의 진행 중인 충전 요청을 시뮬레이션한다. step_s=각 단계 간격(초), wait=true면 끝날 때까지 대기(테스트용)."""
    for v in repo.live_vehicles(db, u.id):
        r = repo.active_request(db, v.id)
        if r and v.ros_vehicle_id:
            if wait:
                run_simulation(ros, v.ros_vehicle_id, str(r.id), step_s)
            else:
                start_background(ros, v.ros_vehicle_id, str(r.id), step_s)
            return {"started": True, "vehicle": v.ros_vehicle_id, "request_id": str(r.id), "step_s": step_s}
    raise ApiError(404, ErrorCode.NOT_FOUND, "진행 중인 충전 요청이 없습니다. 먼저 충전 요청을 만드세요.")
