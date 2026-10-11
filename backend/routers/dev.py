"""개발 전용(ROS_MODE=mock). 실제 관제 없이 앱을 시험하는 시뮬레이터 호출."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import repo
from database import get_db
from deps import CurrentUser, require_user
from dev_sim import run_exit_simulation, run_simulation, start_background, start_exit_background
from errors import ApiError
from schemas.common import ErrorCode
from state import ros

router = APIRouter(prefix="/dev", tags=["dev"])


@router.post("/simulate")
def simulate(step_s: float = Query(3.0, ge=0, le=60), wait: bool = False, wait_zone: str | None = Query(None, pattern=r"^PARKING_\d{2}$"),
             u: CurrentUser = Depends(require_user), db: Session = Depends(get_db)):
    """내 차량의 진행 중인 출차 또는 충전 요청을 시뮬레이션한다. step_s=각 단계 간격(초), wait=true면 끝날 때까지 대기(테스트용).
    wait_zone(예: PARKING_05)을 주면 충전기가 모두 사용 중이라 그 칸에 임시 주차했다가 충전하러 가는 흐름."""
    for v in repo.live_vehicles(db, u.id):
        ex = repo.active_exit(db, v.id)
        if ex and v.ros_vehicle_id:
            rid = str(ex.charge_request_id) if ex.charge_request_id else None
            (run_exit_simulation if wait else start_exit_background)(ros, v.ros_vehicle_id, str(ex.id), rid, step_s)
            return {"started": True, "vehicle": v.ros_vehicle_id, "exit_id": str(ex.id), "step_s": step_s}
        r = repo.active_request(db, v.id)
        if r and v.ros_vehicle_id:
            if wait:
                run_simulation(ros, v.ros_vehicle_id, str(r.id), step_s, wait_zone=wait_zone)
            else:
                start_background(ros, v.ros_vehicle_id, str(r.id), step_s, wait_zone)
            return {"started": True, "vehicle": v.ros_vehicle_id, "request_id": str(r.id), "step_s": step_s}
    raise ApiError(404, ErrorCode.NOT_FOUND, "진행 중인 충전 요청이 없습니다. 먼저 충전 요청을 만드세요.")
