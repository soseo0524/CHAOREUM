"""우리 계약(docs/AIOT_CENTRAL_INTERFACE.md) ↔ 관제(macaron8_AIOT-main, COMMUNICATION_UPDATE.md) 번역.

ROS·네트워크 없이 돌아가는 순수 함수/클래스라 테스트(backend/tests/test_macaron_adapter.py)로 검증한다.
게이트웨이(ros_gateway_client.py)가 CONTROLLER_API를 받으면 이 번역을 거친다.

  서버 → 관제: /charging/request, /charging/cancel  →  HTTP POST /api/charging/requests (CREATE/UPDATE/CANCEL)
  관제 → 서버: 관제 /central_status  →  우리 /central_status 형식

담당자와 아직 합의하지 않아 임시로 정한 규칙(합의되면 여기만 고친다):
  - 주차 완료 = 관제 요청 COMPLETED(충전 끝) 이후 hold_reasons에서 WAITING_FOR_PARKING_ARRIVAL이 사라진 때
  - 진행 중 취소 = 관제가 접수만 하므로 CANCEL_REQUESTED로 두고, 끝까지 가면 COMPLETED로 보낸다
  - 사용자가 고른 주차 구역(parking_zone_id)은 관제가 받지 않는다(차량별 고정 주차칸)
  - /emergency_stop, /admin/command(cancel 제외)는 관제에 기능이 없어 기록만 하고 버린다
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
NS = uuid.UUID("5b0c3f8e-2f1e-4a55-9a7e-6d1f0a0c1e01")  # 관제 task_id(UUID 아님) → 우리 UUID 변환용

# 관제 충전기 상태 → 우리 ChargerState
CHARGER_STATE = {
    "AVAILABLE": "AVAILABLE",
    "PREPARING": "IN_USE",
    "CHARGING": "IN_USE",
    "CHARGE_COMPLETE": "IN_USE",
    "STOPPED": "MAINTENANCE",
    "FAULT": "FAULT",
}

# 관제 요청 hold_reasons
WAIT_ARRIVAL = "WAITING_FOR_CHARGER_ARRIVAL"
WAIT_RETURN = "WAITING_FOR_RETURN_MOVEMENT"
WAIT_PARKING = "WAITING_FOR_PARKING_ARRIVAL"
CANCEL_PREFIX = "CANCEL_REQUESTED_DURING_"


def _iso(ts: float | None) -> str:
    t = datetime.fromtimestamp(ts, tz=timezone.utc) if ts is not None else datetime.now(timezone.utc)
    return t.isoformat()


def task_uuid(raw: str) -> str:
    return str(uuid.uuid5(NS, raw))


@dataclass
class HttpCall:
    """관제 HTTP API로 보낼 요청 하나. retry_as_update: CREATE가 409(같은 id)면 UPDATE로 다시 보낸다."""

    body: dict
    retry_as_update: bool = False


@dataclass
class Translator:
    rejected: dict[str, tuple[str, str]] = field(default_factory=dict)  # request_id → (vehicle_id, 사유)
    cancelled_unknown: dict[str, str] = field(default_factory=dict)  # 관제가 모르는 요청을 취소함 → vehicle_id
    vehicle_of: dict[str, str] = field(default_factory=dict)  # request_id → vehicle_id
    log: list[str] = field(default_factory=list)

    # ---------------- 서버 → 관제 ----------------
    def outbound(self, topic: str, data: str) -> list[HttpCall]:
        d = json.loads(data)
        if topic == "/charging/request":
            rid = d["request_id"]
            self.vehicle_of[rid] = d["vehicle_id"]
            self.rejected.pop(rid, None)
            if d.get("parking_zone_id"):
                self.log.append(f"parking_zone_id {d['parking_zone_id']} 무시(관제 미지원)")
            body = {
                "request_id": rid,
                "operation": "CREATE",
                "vehicle_id": d["vehicle_id"],
                "departure_at": d["desired_finish_at"],  # 우리: PARKED 희망 시각 / 관제: 출발(=사용 가능) 시각
                "target_soc": float(d["target_soc"]),
                "required_soc_at_departure": float(min(d.get("min_soc", 0), d["target_soc"])),
                "not_before": None,
                "start_if_soc_below": None,
            }
            return [HttpCall(body, retry_as_update=True)]
        if topic == "/charging/cancel":
            self.vehicle_of.setdefault(d["request_id"], d["vehicle_id"])
            return [HttpCall({"request_id": d["request_id"], "operation": "CANCEL"})]
        if topic == "/admin/command" and d.get("action") == "cancel" and d.get("request_id"):
            return [HttpCall({"request_id": d["request_id"], "operation": "CANCEL"})]
        self.log.append(f"{topic} 무시(관제 미지원): {data[:200]}")
        return []

    def on_http_result(self, call: HttpCall, status: int, body: dict | None) -> HttpCall | None:
        """HTTP 응답 처리. 다시 보낼 요청이 있으면 돌려준다."""
        rid, op = call.body["request_id"], call.body["operation"]
        if status in (200, 201):
            return None
        if status == 409 and op == "CREATE" and call.retry_as_update:
            return HttpCall({**call.body, "operation": "UPDATE"})  # 같은 request_id 재발행 = 수정
        if op == "CANCEL" and status == 404:  # 관제에 도착하지 못한 요청 → 우리 쪽은 취소 완료로
            self.cancelled_unknown[rid] = self.vehicle_of.get(rid, "")
            return None
        if op == "UPDATE" and status == 409:  # 이미 진행 중이라 수정 불가: 요청은 그대로 진행
            self.log.append(f"{rid} 수정 거절(진행 중)")
            return None
        reason = f"관제가 요청을 받지 못했어요: {_reason(body) or status}"
        if op in ("CREATE", "UPDATE"):
            self.rejected[rid] = (self.vehicle_of.get(rid, call.body.get("vehicle_id", "")), reason)
        self.log.append(f"{rid} {op} 실패 {status}: {reason}")
        return None

    # ---------------- 관제 → 서버 ----------------
    def central_status(self, raw: str | dict) -> dict:
        s = json.loads(raw) if isinstance(raw, str) else raw
        reqs = [r for r in s.get("requests", []) if UUID_RE.match(str(r.get("request_id", "")))]
        chargers = s.get("chargers", [])
        charger_of = {c.get("vehicle_id"): c.get("charger_id") for c in chargers if c.get("vehicle_id")}

        out_reqs, tasks, current = [], [], {}
        live_by_vehicle: dict[str, dict] = {}
        for r in reqs:
            rid, vid = r["request_id"], r["vehicle_id"]
            holds = set(r.get("hold_reasons") or [])
            cancel_req = any(a.startswith(CANCEL_PREFIX) for a in r.get("attention_reasons") or [])
            st = r.get("status")
            parked = st == "COMPLETED" and WAIT_RETURN not in holds and WAIT_PARKING not in holds
            if st == "ACTIVE":
                ours = "ACCEPTED"
            elif st in ("DISPATCHED", "CHARGING") or (st == "COMPLETED" and not parked):
                ours = "CANCEL_REQUESTED" if cancel_req else "IN_PROGRESS"
            elif st == "COMPLETED":
                ours = "COMPLETED"
            elif st == "CANCELED":
                ours = "CANCELLED"
            else:
                continue
            out_reqs.append({"request_id": rid, "vehicle_id": vid, "status": ours})
            if ours not in ("COMPLETED", "CANCELLED"):
                live_by_vehicle[vid] = {**r, "_holds": holds, "_parked": parked}

            charger_id = charger_of.get(vid) or "CHARGER_01"
            if r.get("task_id"):
                running = st == "DISPATCHED" and WAIT_ARRIVAL in holds
                tid = task_uuid(r["task_id"])
                tasks.append(_task(tid, rid, vid, "MOVE_TO_CHARGER", charger_id, "RUNNING" if running else "COMPLETED"))
                if running:
                    current[vid] = tid
            if r.get("return_task_id"):
                running = WAIT_RETURN in holds or WAIT_PARKING in holds
                tid = task_uuid(r["return_task_id"])
                tasks.append(_task(tid, rid, vid, "MOVE_TO_PARKING", "PARKING", "RUNNING" if running else "COMPLETED"))
                if running:
                    current[vid] = tid

        # 게이트웨이가 관제 HTTP에서 거절당한 요청: 실패로 알리고 사유는 FAILED 작업의 error_message로 전달
        for rid, (vid, reason) in list(self.rejected.items()):  # 다른 스레드가 바꿀 수 있어 복사본으로
            if any(x["request_id"] == rid for x in out_reqs) or not ID_RE.match(vid or ""):
                continue
            out_reqs.append({"request_id": rid, "vehicle_id": vid, "status": "FAILED", "reason": reason})
            t = _task(task_uuid("rejected:" + rid), rid, vid, "MOVE_TO_CHARGER", "CHARGER_01", "FAILED")
            tasks.append({**t, "error_message": reason})
        for rid, vid in list(self.cancelled_unknown.items()):
            if ID_RE.match(vid or "") and not any(x["request_id"] == rid for x in out_reqs):
                out_reqs.append({"request_id": rid, "vehicle_id": vid, "status": "CANCELLED"})

        vehicles = []
        for v in s.get("vehicles", []):
            vid = v.get("vehicle_id")
            if not vid or not ID_RE.match(vid):
                continue
            item = {
                "vehicle_id": vid,
                "state": _vehicle_state(v, live_by_vehicle.get(vid)),
                "soc": max(0.0, min(100.0, float(v.get("soc") or 0))),
                "pose": {"x": float(v.get("x") or 0), "y": float(v.get("y") or 0), "yaw": float(v.get("yaw") or 0)},
            }
            loc = v.get("location_id")
            if loc and ID_RE.match(str(loc)):
                item["zone_id"] = str(loc)  # 관제 PARKING_nn(nn=슬롯 번호 0~65) / CHARGER_01 은 우리 id와 같은 형식
            if vid in charger_of:
                item["charger_id"] = charger_of[vid]
            if vid in current:
                item["current_task_id"] = current[vid]
            vehicles.append(item)

        out_chargers = []
        for c in chargers:
            cid = c.get("charger_id")
            if not cid or not ID_RE.match(cid):
                continue
            state = "FAULT" if c.get("error_code") else CHARGER_STATE.get(c.get("state"), "MAINTENANCE")
            item = {"charger_id": cid, "state": state, "power_kw": max(0.0, float(c.get("power_kw") or 0))}
            if c.get("vehicle_id") and ID_RE.match(c["vehicle_id"]):
                item["vehicle_id"] = c["vehicle_id"]
            out_chargers.append(item)

        events = []
        for e in s.get("events", []):
            key = json.dumps(e, sort_keys=True, ensure_ascii=False)
            events.append({
                "event_id": hashlib.sha1(key.encode()).hexdigest(),
                "type": str(e.get("event_type") or "EVENT"),
                "at": _iso(e.get("timestamp")),
                "vehicle_id": e.get("vehicle_id"),
                "charger_id": e.get("charger_id"),
            })

        return {
            "schema_version": 1,
            "at": _iso(s.get("timestamp")),
            "vehicles": vehicles,
            "tasks": tasks,
            "chargers": out_chargers,
            "requests": out_reqs,
            "events": events,
            "scheduler": {"queue_length": sum(1 for r in reqs if r.get("status") == "ACTIVE")},
            "emergency_stop_active": False,
        }


def _task(tid: str, rid: str, vid: str, kind: str, target: str, status: str) -> dict:
    return {
        "task_id": tid,
        "request_id": rid,
        "vehicle_id": vid,
        "type": kind,
        "status": status,
        "target_id": target,
        "target_pose": {"x": 0.0, "y": 0.0, "yaw": 0.0},  # 관제가 상태에 목표 좌표를 싣지 않음
    }


def _vehicle_state(v: dict, req: dict | None) -> str:
    """관제 차량 상태(IDLE/DRIVING/PARKING/PARKED/ERROR) + 진행 중 요청 → 우리 VehicleState."""
    if v.get("state") == "ERROR" or v.get("error_code") or v.get("estop"):
        return "FAULT"
    if not req:
        return "WAITING" if v.get("state") == "DRIVING" else "PARKED"
    st, holds = req.get("status"), req["_holds"]
    if st == "ACTIVE":
        return "WAITING"  # 대기열(우리 계약: 대기 중 차량은 WAITING)
    if st == "DISPATCHED":
        return "MOVING_TO_CHARGER" if WAIT_ARRIVAL in holds else "ARRIVED_AT_CHARGER"
    if st == "CHARGING":
        return "CHARGING"
    if st == "COMPLETED":
        if WAIT_RETURN in holds:
            return "CHARGE_DONE"
        if WAIT_PARKING in holds:
            return "MOVING_TO_PARKING"
    return "PARKED"


def _reason(body: dict | None) -> str | None:
    if not isinstance(body, dict):
        return None
    d = body.get("detail", body)
    if isinstance(d, dict):
        return d.get("message") or d.get("error_code") or d.get("error")
    return str(d) if d else None
