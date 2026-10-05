"""개발용 중앙관제 시뮬레이터. 실제 관제 없이 앱을 개발·시연하기 위한 것이다(ROS_MODE=mock 에서만 켜짐).

요청 1건을 ACCEPTED → SCHEDULED → IN_PROGRESS → COMPLETED 로, 차량을 5단계(이동→충전→완료→주차 이동→주차)로
진행시키며 /central_status 와 같은 JSON을 주입한다. 실제 관제가 지켜야 할 동작은 docs/AIOT_CENTRAL_INTERFACE.md.
"""
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from ros_schemas.messages import CentralStatusMsg


def _msg(ros_id, request_id, req_status, state, soc, task=None, zone=None, charger=None, progress=None, event=None):
    now = datetime.now(timezone.utc)
    d = dict(
        at=now,
        vehicles=[dict(vehicle_id=ros_id, state=state, soc=soc, zone_id=zone, charger_id=charger, progress=progress,
                       current_task_id=task["task_id"] if task else None, last_seen_at=now,
                       estimated_completion=now + timedelta(minutes=5))],
        tasks=[task] if task else [],
        chargers=[dict(charger_id="CHARGER_01", state="IN_USE" if charger else "AVAILABLE", vehicle_id=ros_id if charger else None, power_kw=7.0 if state == "CHARGING" else 0)],
        requests=[dict(request_id=request_id, vehicle_id=ros_id, status=req_status)],
        events=[dict(event_id=str(uuid.uuid4()), type=event, at=now, vehicle_id=ros_id, request_id=request_id)] if event else [],
    )
    return CentralStatusMsg.model_validate(d).model_dump_json()


def run_simulation(ros, ros_id: str, request_id: str, step_s: float = 3.0, soc_start: int = 30, target_soc: int = 80):
    def task(kind, target):
        return dict(task_id=str(uuid.uuid4()), request_id=request_id, vehicle_id=ros_id, type=kind, status="RUNNING", target_id=target, target_pose=dict(x=1.0, y=2.0, yaw=0.0), progress=0.5)

    t1, t2 = task("MOVE_TO_CHARGER", "CHARGER_01"), task("MOVE_TO_PARKING", "PARKING_01")
    script = [
        ("ACCEPTED", "WAITING", soc_start, None, "WAIT_01", None, None, "REQUEST_ACCEPTED"),
        ("SCHEDULED", "ASSIGNED", soc_start, None, "WAIT_01", None, None, "REQUEST_SCHEDULED"),
        ("IN_PROGRESS", "MOVING_TO_CHARGER", soc_start, t1, None, None, 0.5, "TASK_STARTED"),
        ("IN_PROGRESS", "ARRIVED_AT_CHARGER", soc_start, None, "CHARGE_01", "CHARGER_01", None, "ARRIVED_AT_CHARGER"),
        *[("IN_PROGRESS", "CHARGING", s, None, "CHARGE_01", "CHARGER_01", None, "CHARGE_STARTED" if s == soc_start else None)
          for s in range(soc_start, target_soc + 1, max((target_soc - soc_start) // 4, 1))],
        ("IN_PROGRESS", "CHARGE_DONE", target_soc, None, "CHARGE_01", "CHARGER_01", None, "CHARGE_DONE"),
        ("IN_PROGRESS", "MOVING_TO_PARKING", target_soc, t2, None, None, 0.5, "TASK_STARTED"),
        ("COMPLETED", "PARKED", target_soc, None, "PARKING_01", None, None, "PARKED"),
    ]
    for req_status, state, soc, tk, zone, charger, progress, event in script:
        ros.inject_central_status(_msg(ros_id, request_id, req_status, state, soc, tk, zone, charger, progress, event))
        if step_s:
            time.sleep(step_s)


def start_background(ros, ros_id, request_id, step_s):
    th = threading.Thread(target=run_simulation, args=(ros, ros_id, request_id, step_s), daemon=True)
    th.start()
    return th
