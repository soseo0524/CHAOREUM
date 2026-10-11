"""개발용 중앙관제 시뮬레이터. 실제 관제 없이 앱을 개발·시연하기 위한 것이다(ROS_MODE=mock 에서만 켜짐).

요청 1건을 ACCEPTED → SCHEDULED → IN_PROGRESS → COMPLETED 로, 차량을 5단계(이동→충전→완료→주차 이동→주차)로
진행시키며 /central_status 와 같은 JSON을 주입한다. 실제 관제가 지켜야 할 동작은 docs/AIOT_CENTRAL_INTERFACE.md.
"""
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from ros_schemas.messages import CentralStatusMsg


def _msg(ros_id, request_id, req_status, state, soc, task=None, zone=None, charger=None, progress=None, event=None, req_extra=None, exits=None):
    now = datetime.now(timezone.utc)
    d = dict(
        at=now,
        vehicles=[dict(vehicle_id=ros_id, state=state, soc=soc, zone_id=zone, charger_id=charger, progress=progress,
                       current_task_id=task["task_id"] if task else None, last_seen_at=now,
                       estimated_completion=now + timedelta(minutes=5))],
        tasks=[task] if task else [],
        chargers=[dict(charger_id="CHARGER_01", state="IN_USE" if charger else "AVAILABLE", vehicle_id=ros_id if charger else None, power_kw=7.0 if state == "CHARGING" else 0)],
        requests=[dict(request_id=request_id, vehicle_id=ros_id, status=req_status, **(req_extra or {}))] if request_id else [],
        exits=exits or [],
        events=[dict(event_id=str(uuid.uuid4()), type=event, at=now, vehicle_id=ros_id, request_id=request_id)] if event else [],
    )
    return CentralStatusMsg.model_validate(d).model_dump_json()


def run_simulation(ros, ros_id: str, request_id: str, step_s: float = 3.0, soc_start: int = 30, target_soc: int = 80, wait_zone: str | None = None):
    """wait_zone을 주면 충전기가 모두 사용 중인 상황을 흉내 낸다: 그 칸으로 임시 주차(이동 → 도착) 후 충전하러 간다."""
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
    if wait_zone:
        script[1:1] = [("ACCEPTED", "MOVING_TO_PARKING", soc_start, None, None, None, 0.5, None, dict(wait_zone_id=wait_zone, wait_arrived=False)),
                       ("ACCEPTED", "PARKED", soc_start, None, wait_zone, None, None, None, dict(wait_zone_id=wait_zone, wait_arrived=True))]
    for row in script:
        req_status, state, soc, tk, zone, charger, progress, event = row[:8]
        extra = row[8] if len(row) > 8 else (dict(wait_zone_id=None) if wait_zone else None)
        ros.inject_central_status(_msg(ros_id, request_id, req_status, state, soc, tk, zone, charger, progress, event, extra))
        if step_s:
            time.sleep(step_s)


def run_exit_simulation(ros, ros_id: str, exit_id: str, request_id: str | None, step_s: float = 3.0, soc: int = 80):
    """출차: 출구로 이동 → 출구 도착. 진행 중이던 충전 요청은 취소로 끝난다."""
    ex = lambda st: [dict(exit_id=exit_id, vehicle_id=ros_id, status=st, exit_zone_id="EXIT_01")]
    for state, ex_status, req_status in (("MOVING_TO_EXIT", "IN_PROGRESS", "CANCEL_REQUESTED"), ("EXITED", "COMPLETED", "CANCELLED")):
        ros.inject_central_status(_msg(ros_id, request_id, req_status, state, soc, zone="EXIT_01" if state == "EXITED" else None, exits=ex(ex_status)))
        if step_s:
            time.sleep(step_s)


def start_background(ros, ros_id, request_id, step_s, wait_zone=None):
    th = threading.Thread(target=run_simulation, args=(ros, ros_id, request_id, step_s), kwargs=dict(wait_zone=wait_zone), daemon=True)
    th.start()
    return th


def start_exit_background(ros, ros_id, exit_id, request_id, step_s):
    th = threading.Thread(target=run_exit_simulation, args=(ros, ros_id, exit_id, request_id, step_s), daemon=True)
    th.start()
    return th
