"""게이트웨이 번역(gateway/macaron_adapter.py): 관제(macaron8_AIOT-main) 형식 ↔ 우리 계약.

관제가 실제로 내보내는 /central_status 모양을 흉내 내 번역한 뒤 우리 백엔드에 넣어, 앱 홈 상태가 제대로 바뀌는지 본다.
"""
import json
import sys
from pathlib import Path

from ros_schemas import parse_topic
from state import ros
from tests.test_api import UH, assign, body, clean, client, vehicle  # noqa: F401  (clean: 매 테스트 DB 초기화)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "gateway"))
from macaron_adapter import Translator  # noqa: E402

EV = "EV-01"


def controller_status(rid, status, holds=(), attention=(), vehicle_state="PARKED", task=True, ret=False, soc=40.0):
    """관제 CentralControlAdapter.central_status() 와 같은 모양."""
    return {
        "timestamp": 1791176400.0,
        "vehicles": [{"vehicle_id": EV, "x": 1.0, "y": 2.0, "yaw": 0.5, "speed": 0.0, "frame_id": "map", "soc": soc,
                      "state": vehicle_state, "ready": True, "control_mode": "AUTO", "estop": False, "error_code": None,
                      "task_id": None, "location_id": "PARKING_01"}],
        "chargers": [{"charger_id": "CHARGER_01", "power_kw": 7.0, "state": "CHARGING" if status == "CHARGING" else "AVAILABLE",
                      "vehicle_id": EV if status == "CHARGING" else None, "ready_to_charge": True, "aligned": None, "error_code": None}],
        "requests": [{"request_id": rid, "vehicle_id": EV, "status": status, "attention_reasons": list(attention),
                      "hold_reasons": list(holds), "task_id": "TASK_EV-01_001" if task else None,
                      "return_task_id": "TASK_EV-01_002" if ret else None, "command_id": None,
                      "departure_at": "2026-10-05T17:00:00+09:00", "target_soc": 80.0, "required_soc_at_departure": 0.0},
                     {"request_id": "REQUEST_001", "vehicle_id": "EV-02", "status": "ACTIVE", "attention_reasons": [],
                      "hold_reasons": [], "task_id": None, "return_task_id": None}],  # 대시보드가 만든 요청(UUID 아님)은 무시
        "access": [],
        "events": [{"timestamp": 1791176400.0, "event_type": "VEHICLE_TASK_DISPATCHED", "vehicle_id": EV, "charger_id": "CHARGER_01"}],
        "errors": [],
    }


def push(t: Translator, raw: dict):
    msg = t.central_status(json.dumps(raw))
    parse_topic("/central_status", json.dumps(msg))  # 우리 계약 검증을 통과해야 한다
    ros.inject_central_status(json.dumps(msg))
    return client.get("/me/status", headers=UH).json()["vehicles"][0]


def start():
    vid = vehicle()
    assign(vid, EV)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    r = client.post("/charge-requests", headers=UH, json=body(vid, min_soc=20, parking_zone_id="PARKING_03"))
    assert r.status_code == 201, r.text
    return r.json()["request"]["id"]


def test_outbound_request_becomes_controller_create_then_update():
    rid = start()
    t = Translator()
    calls = t.outbound("/charging/request", json.dumps(ros.last("/charging/request")))
    b = calls[0].body
    assert b["operation"] == "CREATE" and b["request_id"] == rid and b["vehicle_id"] == EV
    assert b["target_soc"] == 80.0 and b["required_soc_at_departure"] == 20.0 and b["departure_at"]
    assert any("parking_zone_id" in x for x in t.log)  # 관제 미지원 필드는 기록만
    # 같은 request_id 재발행(수정)은 관제에서 409 → UPDATE로 다시 보낸다
    again = t.on_http_result(calls[0], 409, {"detail": {"error_code": "REQUEST_CONFLICT", "message": "x"}})
    assert again.body["operation"] == "UPDATE"
    assert t.on_http_result(again, 200, {}) is None
    cancel = t.outbound("/charging/cancel", json.dumps({"schema_version": 1, "request_id": rid, "vehicle_id": EV, "requested_by": "user"}))
    assert cancel[0].body == {"request_id": rid, "operation": "CANCEL"}
    assert t.outbound("/emergency_stop", json.dumps({"action": "STOP"})) == []


def test_full_progress_maps_to_app_home_states():
    rid = start()
    t = Translator()
    v = push(t, controller_status(rid, "ACTIVE", task=False))
    assert v["home_state"] == "QUEUED" and v["state"] == "WAITING" and v["zone_id"] == "PARKING_01"
    v = push(t, controller_status(rid, "DISPATCHED", holds=["WAITING_FOR_CHARGER_ARRIVAL"], vehicle_state="DRIVING"))
    assert v["home_state"] == "MOVING_TO_CHARGER" and v["current_task"]["type"] == "MOVE_TO_CHARGER"
    v = push(t, controller_status(rid, "DISPATCHED", holds=["WAITING_FOR_VEHICLE_IDENTIFICATION"]))
    assert v["state"] == "ARRIVED_AT_CHARGER"
    v = push(t, controller_status(rid, "CHARGING", soc=60.0))
    assert v["home_state"] == "CHARGING" and v["charger_id"] == "CHARGER_01"
    # 관제 COMPLETED(충전만 끝) → 우리는 아직 진행 중
    v = push(t, controller_status(rid, "COMPLETED", holds=["WAITING_FOR_RETURN_MOVEMENT", "WAITING_FOR_PARKING_ARRIVAL"], ret=True, soc=80.0))
    assert v["home_state"] == "CHARGE_DONE" and v["active_request"]["status"] == "IN_PROGRESS"
    v = push(t, controller_status(rid, "COMPLETED", holds=["WAITING_FOR_PARKING_ARRIVAL"], ret=True, vehicle_state="DRIVING", soc=80.0))
    assert v["home_state"] == "MOVING_TO_PARKING" and v["current_task"]["type"] == "MOVE_TO_PARKING"
    # 주차 도착(hold 없음) → 우리 COMPLETED
    v = push(t, controller_status(rid, "COMPLETED", ret=True, soc=80.0))
    assert v["home_state"] == "PARKED" and v["active_request"] is None and v["last_request"]["status"] == "COMPLETED"


def test_cancel_and_rejection_and_fault():
    rid = start()
    t = Translator()
    v = push(t, controller_status(rid, "CHARGING", attention=["CANCEL_REQUESTED_DURING_CHARGING"]))
    assert v["home_state"] == "CANCELING"
    v = push(t, controller_status(rid, "CANCELED", task=False))
    assert v["home_state"] == "CANCELLED"


def test_controller_rejection_shows_failure_reason():
    rid = start()
    t = Translator()
    calls = t.outbound("/charging/request", json.dumps(ros.last("/charging/request")))
    t.on_http_result(calls[0], 422, {"detail": {"error_code": "INVALID_SOC", "message": "target_soc invalid"}})
    raw = controller_status(rid, "ACTIVE", task=False)
    raw["requests"] = []  # 관제는 이 요청을 모른다
    v = push(t, raw)
    assert v["home_state"] == "REQUEST_FAILED" and "target_soc invalid" in v["last_request"]["failure_reason"]


def test_vehicle_error_is_fault_and_unknown_charger_state_is_safe():
    rid = start()
    t = Translator()
    raw = controller_status(rid, "ACTIVE", task=False, vehicle_state="ERROR")
    raw["chargers"][0]["state"] = "UNCONFIGURED"
    v = push(t, raw)
    assert v["home_state"] == "FAULT"
