"""관제(macaron8_AIOT-main) 게이트웨이 프로토콜 ↔ 우리 계약.

관제 PC에서 관제 담당자의 게이트웨이(src/aiot_central_control/gateway/ros_gateway_client.py)를 실행하면
`Authorization: Bearer <GATEWAY_TOKEN>` 헤더로 /ws/gateway 에 붙고 아래 형식으로 주고받는다.
  서버 → 관제: {"type": "charging_request" | "charging_cancel", "payload": {...}}
  관제 → 서버: {"type": "central_status", "payload": <contract.outbound_status 결과>}
               {"type": "request_result", "payload": <관제 HTTP 응답>, "request_id": "..."}

관제 쪽 규칙(관제 코드 기준):
  - 주차 지정은 구역(A/B/C) 단위다. 사용자가 고른 칸(PARKING_nn)은 그 칸이 속한 구역으로 바꿔 보내고, 칸은 관제가 고른다.
  - 칸 ID는 PARKING_5 처럼 0을 채우지 않는다 → 우리 PARKING_05 로 맞춘다.
  - 요청 COMPLETED = 최종 주차 도착, CANCELED = 취소 후 출차 구역 도착(관제 게이트웨이가 이미 우리 상태 이름으로 바꿔 보낸다).
  - battery_kwh, max_charge_kw 는 관제가 아직 쓰지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

from schemas.parking_map import AREA_ROWS, seat_no_of, seat_zone_id

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
NS = uuid.UUID("5b0c3f8e-2f1e-4a55-9a7e-6d1f0a0c1e01")  # 관제 task_id(UUID 아님) → 우리 UUID

REQUEST_STATES = {"REQUESTED", "ACCEPTED", "SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCEL_REQUESTED", "CANCELLED", "FAILED"}
VEHICLE_STATES = {"ARRIVED_AT_STATION", "WAITING", "ASSIGNED", "MOVING_TO_CHARGER", "ARRIVED_AT_CHARGER", "CHARGING",
                  "CHARGE_DONE", "MOVING_TO_PARKING", "PARKED", "FAULT"}
CHARGER_STATES = {"AVAILABLE", "IN_USE", "MAINTENANCE", "FAULT"}
_AREA_OF = {n: a for a, rows in AREA_ROWS.items() for row in rows for n in row}


def area_of_zone(zone_id: str | None) -> str | None:
    """PARKING_05 → 'B'. 구역이 없으면 None(관제가 A→B→C 순으로 고른다)."""
    n = seat_no_of(zone_id)
    return _AREA_OF.get(n) if n is not None else None


def our_zone_id(location_id) -> str | None:
    """관제 location_id(PARKING_5, CHARGER_01) → 우리 id(PARKING_05, CHARGER_01)."""
    if not location_id:
        return None
    m = re.fullmatch(r"PARKING_(\d+)", str(location_id))
    if m:
        return seat_zone_id(int(m.group(1)))
    return str(location_id) if ID_RE.match(str(location_id)) else None


def _task_uuid(raw: str) -> str:
    return str(uuid.uuid5(NS, raw))


def _iso(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).isoformat()


# ---------------- 서버 → 관제 ----------------
def to_controller(topic: str, data: str) -> dict | None:
    """우리 토픽 메시지 → 관제 게이트웨이 envelope. 관제가 받지 않는 토픽은 None."""
    d = json.loads(data)
    if topic == "/charging/request":
        area = d.get("parking_area") or area_of_zone(d.get("parking_zone_id"))  # 관제는 구역(A·B·C)만 받는다
        return {"type": "charging_request", "payload": {**d, "parking_zone_id": area}}
    if topic == "/charging/cancel":
        return {"type": "charging_cancel", "payload": {"request_id": d["request_id"], "vehicle_id": d.get("vehicle_id")}}
    if topic == "/admin/command" and d.get("action") == "cancel" and d.get("request_id"):
        return {"type": "charging_cancel", "payload": {"request_id": d["request_id"], "vehicle_id": d.get("vehicle_id")}}
    return None  # /emergency_stop, 그 밖의 관리자 명령: 관제 미지원


# ---------------- 관제 → 서버 ----------------
def status_from_controller(p: dict) -> dict:
    """관제 게이트웨이 central_status payload → 우리 CentralStatusMsg JSON."""
    reqs = [r for r in p.get("requests", []) if UUID_RE.match(str(r.get("request_id", ""))) and ID_RE.match(str(r.get("vehicle_id", "")))]
    vstate = {v.get("vehicle_id"): v.get("state") for v in p.get("vehicles", [])}
    out_reqs, tasks, current = [], [], {}
    for r in reqs:
        rid, vid, st = r["request_id"], r["vehicle_id"], r.get("status")
        out_reqs.append({"request_id": rid, "vehicle_id": vid, "status": st if st in REQUEST_STATES else "FAILED",
                         "reason": ", ".join(r.get("attention_reasons") or []) or None})
        if st in ("COMPLETED", "CANCELLED", "FAILED"):
            continue
        ret = r.get("return_task_id")
        if r.get("task_id") and r["task_id"] != ret:  # 충전기로 가는 작업
            tid = _task_uuid(r["task_id"])
            moving = not ret and vstate.get(vid) in ("ASSIGNED", "MOVING_TO_CHARGER")
            tasks.append(_task(tid, rid, vid, "MOVE_TO_CHARGER", "CHARGER_01", "RUNNING" if moving else "COMPLETED"))
            if moving:
                current[vid] = tid
        if ret:  # 주차(대기·최종·출차) 구역으로 가는 작업
            tid = _task_uuid(ret)
            arrived = bool(r.get("parking_arrived"))
            target = our_zone_id(r.get("assigned_parking_slot")) or "PARKING"
            tasks.append(_task(tid, rid, vid, "MOVE_TO_PARKING", target, "COMPLETED" if arrived else "RUNNING"))
            if not arrived:
                current[vid] = tid

    vehicles = []
    for v in p.get("vehicles", []):
        vid = v.get("vehicle_id")
        if not vid or not ID_RE.match(str(vid)):
            continue
        pose = v.get("pose") or {}
        item = {"vehicle_id": vid, "state": v.get("state") if v.get("state") in VEHICLE_STATES else "WAITING",
                "soc": max(0.0, min(100.0, float(v.get("soc") or 0)))}
        if all(isinstance(pose.get(k), (int, float)) for k in ("x", "y", "yaw")):
            item["pose"] = {"x": float(pose["x"]), "y": float(pose["y"]), "yaw": float(pose["yaw"])}
        zone = our_zone_id(v.get("zone_id") or v.get("location_id"))
        if zone:
            item["zone_id"] = zone
        if vid in current:
            item["current_task_id"] = current[vid]
        vehicles.append(item)

    chargers = []
    for c in p.get("chargers", []):
        cid = c.get("charger_id")
        if not cid or not ID_RE.match(str(cid)):
            continue
        item = {"charger_id": cid, "state": c.get("state") if c.get("state") in CHARGER_STATES else "MAINTENANCE",
                "power_kw": max(0.0, float(c.get("power_kw") or 0))}
        if c.get("vehicle_id") and ID_RE.match(str(c["vehicle_id"])):
            item["vehicle_id"] = c["vehicle_id"]
            for v in vehicles:
                if v["vehicle_id"] == c["vehicle_id"]:
                    v["charger_id"] = cid
        chargers.append(item)

    events = [{"event_id": hashlib.sha1(json.dumps(e, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
               "type": str(e.get("event_type") or e.get("type") or "EVENT"), "at": _iso(e.get("timestamp")),
               "vehicle_id": e.get("vehicle_id"), "charger_id": e.get("charger_id")}
              for e in p.get("events", []) if isinstance(e, dict)]

    return {"schema_version": 1, "at": p.get("at") or _iso(None), "vehicles": vehicles, "tasks": tasks, "chargers": chargers,
            "requests": out_reqs, "events": events,
            "scheduler": {"queue_length": sum(1 for r in out_reqs if r["status"] == "ACCEPTED")}, "emergency_stop_active": False}


def failure_from_result(item: dict, vehicle_of: dict[str, str]) -> dict | None:
    """관제가 요청을 거절한 request_result → 그 요청만 FAILED로 알리는 CentralStatusMsg JSON. 성공·수정 거절이면 None."""
    p = item.get("payload") or {}
    rid = item.get("request_id") or p.get("request_id")
    vid = vehicle_of.get(rid or "")
    if p.get("accepted", True) or not rid or not vid or not UUID_RE.match(rid):
        return None
    status = p.get("http_status")
    if status == 409:  # 진행 중이라 수정 불가: 요청은 그대로 진행
        return None
    if status == 404:  # 관제가 모르는 요청을 취소함 → 취소 완료로
        return {"schema_version": 1, "at": _iso(None), "requests": [{"request_id": rid, "vehicle_id": vid, "status": "CANCELLED"}]}
    reason = f"관제가 요청을 받지 못했어요: {_reason(p.get('error')) or status}"
    task = {**_task(_task_uuid("rejected:" + rid), rid, vid, "MOVE_TO_CHARGER", "CHARGER_01", "FAILED"), "error_message": reason}
    return {"schema_version": 1, "at": _iso(None), "tasks": [task],
            "requests": [{"request_id": rid, "vehicle_id": vid, "status": "FAILED", "reason": reason}]}


def _task(tid: str, rid: str, vid: str, kind: str, target: str, status: str) -> dict:
    return {"task_id": tid, "request_id": rid, "vehicle_id": vid, "type": kind, "status": status, "target_id": target,
            "target_pose": {"x": 0.0, "y": 0.0, "yaw": 0.0}}


def _reason(raw) -> str | None:
    if not raw:
        return None
    try:
        d = json.loads(raw) if isinstance(raw, str) else raw
        d = d.get("detail", d) if isinstance(d, dict) else d
        if isinstance(d, dict):
            return d.get("message") or d.get("error_code")
    except ValueError:
        pass
    return str(raw)[:200]
