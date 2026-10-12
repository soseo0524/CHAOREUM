"""시연용 '다른 차량'. 실제로는 다른 사용자가 폰으로 충전 요청해야 하지만, 시연에서 차가 한 대뿐일 때
관제(가짜 관제) 게이트웨이가 {"type": "demo_guest", "payload": {...}}를 보내면 주인 없는 시연 차량과 실제 충전 요청을 DB에 만들고
보통 요청처럼 관제로 보낸다(/charging/request). 이후 진행은 다른 차량과 똑같이 관제 상태로 DB에 반영된다.

payload: minutes(충전에 걸릴 시간, 기본 60), soc(시작 배터리, 기본 20), target_soc(기본 100).
배터리 용량은 '남은 충전 = minutes'가 되도록 정해서, 그 차 뒤에 기다리는 사용자에게 '약 minutes분 대기'가 보이게 한다.
게이트웨이 토큰을 가진 쪽(관제)만 보낼 수 있다.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

import models as m
import repo
from config import settings

GUEST_PLATE = "시연 차량 {}"
GUEST_KW = 48.0


def _guest_ros_id(db) -> str | None:
    """사용자 차량이 쓰지 않는 관제 차량 ID(뒤에서부터: EV-03, EV-02 …). 이미 만든 시연 차량이 있으면 그것."""
    rows = db.scalars(select(m.Vehicle).where(m.Vehicle.deleted_at.is_(None), m.Vehicle.ros_vehicle_id.is_not(None))).all()
    for v in rows:
        if v.owner_id is None and v.plate_no.startswith(GUEST_PLATE.format("")):
            return v.ros_vehicle_id
    used = {v.ros_vehicle_id for v in rows}
    return next((x for x in reversed(settings.auto_assign_ros_ids) if x not in used), None)


def start_guest(db, payload: dict) -> tuple[dict, m.ChargeRequest | None, m.Vehicle | None]:
    """시연 차량의 충전 요청을 만든다. (관제에 돌려줄 응답, 만든 요청, 차량). 호출자가 commit 후 요청을 발행한다."""
    minutes = max(1, int(payload.get("minutes") or 60))
    soc = max(0, min(99, int(payload.get("soc") if payload.get("soc") is not None else 20)))
    target = max(soc + 1, min(100, int(payload.get("target_soc") or 100)))
    ros_id = _guest_ros_id(db)
    if ros_id is None:
        return {"ok": False, "message": "시연 차량에 붙일 관제 차량 ID가 없어요(EV-01~03을 모두 사용자 차량이 쓰는 중)"}, None, None
    v = repo.vehicle_by_ros(db, ros_id)
    battery = round(minutes / 60 * GUEST_KW / ((target - soc) / 100), 2)  # 남은 충전 시간이 minutes가 되는 용량
    if v is None:
        v = m.Vehicle(ros_vehicle_id=ros_id, owner_id=None, plate_no=GUEST_PLATE.format(ros_id), battery_kwh=battery, max_charge_kw=GUEST_KW)
        db.add(v)
        db.flush()
    else:
        v.battery_kwh, v.max_charge_kw, v.updated_at = battery, GUEST_KW, repo.now()
    if repo.active_request(db, v.id):
        return {"ok": False, "vehicle_id": ros_id, "message": "시연 차량에 이미 진행 중인 요청이 있어요. 먼저 빼 주세요"}, None, v
    r = m.ChargeRequest(vehicle_id=v.id, desired_finish_at=repo.now() + timedelta(minutes=minutes + 60), target_soc=target, min_soc=0)
    db.add(r)
    db.flush()
    return {"ok": True, "vehicle_id": ros_id, "request_id": str(r.id), "soc": soc, "target_soc": target, "minutes": minutes}, r, v
