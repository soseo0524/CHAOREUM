"""관제 담당 게이트웨이(macaron8_AIOT-main/.../gateway) 프로토콜로 /ws/gateway 연동.

관제 PC의 게이트웨이처럼 Authorization 헤더로 붙어 {type, payload} 메시지를 주고받는다.
관제 폴더가 있으면 관제의 contract.outbound_status()로 실제와 같은 payload를 만들고, 없으면 그 결과를 흉내 낸 값을 쓴다.
"""
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from starlette.websockets import WebSocketDisconnect

import main
import ws as ws_mod
from macaron import area_of_zone, our_zone_id, status_from_controller, to_controller
from ros_bridge import GatewayRosBridge
from ros_schemas import parse_topic
from tests.test_api import AH, UH, assign, body, clean, client, vehicle  # noqa: F401  (clean: 매 테스트 DB 초기화)

EV = "EV-01"
TOKEN = "secret-token"
CONTRACT_DIR = Path(__file__).resolve().parents[2] / "macaron8_AIOT-main/src/aiot_central_control/gateway"
try:
    sys.path.insert(0, str(CONTRACT_DIR))
    from contract import outbound_status  # 관제 담당 코드 그대로
except ImportError:  # 관제 폴더가 없는 환경
    outbound_status = None


@pytest.fixture
def gw(monkeypatch):
    bridge = GatewayRosBridge()
    bridge.on_central_status(main._on_central)
    import routers.admin
    import routers.charge_requests

    for mod in (ws_mod, routers.charge_requests, routers.admin):  # 요청 API가 이 게이트웨이로 발행하게
        monkeypatch.setattr(mod, "ros", bridge)
    monkeypatch.setattr(ws_mod, "settings", replace(ws_mod.settings, gateway_token=TOKEN))
    return bridge


def raw_status(rid, status, vehicle_state="IDLE", soc=40.0, location="PARKING_33", charger_state="AVAILABLE", **req):
    """관제 CentralControlAdapter.central_status() 모양(게이트웨이 변환 전)."""
    return {
        "timestamp": 1791176400.0,
        "vehicles": [{"vehicle_id": EV, "x": 1.0, "y": 2.0, "yaw": 0.5, "speed": 0.0, "frame_id": "camera_map", "soc": soc,
                      "state": vehicle_state, "ready": True, "control_mode": "AUTO", "estop": False, "error_code": None,
                      "task_id": None, "location_id": location}],
        "chargers": [{"charger_id": "CHARGER_01", "power_kw": 7.0, "state": charger_state,
                      "vehicle_id": EV if charger_state != "AVAILABLE" else None, "ready_to_charge": True, "aligned": None, "error_code": None}],
        "requests": [{"request_id": rid, "vehicle_id": EV, "status": status, "attention_reasons": [], "hold_reasons": [],
                      "target_soc": 80.0, "required_soc_at_departure": 20.0, "preferred_parking_zone": "B",
                      "assigned_parking_zone": None, "assigned_parking_slot": None, "cancel_requested": False,
                      "task_id": None, "return_task_id": None, "charger_released": False, "parking_arrived": False,
                      "parking_purpose": None, **req},
                     {"request_id": "REQUEST_001", "vehicle_id": "EV-02", "status": "ACTIVE"}],  # 대시보드가 만든 요청(UUID 아님)
        "access": [],
        "events": [{"timestamp": 1791176400.0, "event_type": "VEHICLE_TASK_DISPATCHED", "vehicle_id": EV, "charger_id": "CHARGER_01"}],
        "errors": [],
    }


def payload(raw):
    if outbound_status:
        return outbound_status(raw)
    pytest.skip("관제 폴더(macaron8_AIOT-main)가 없어 관제 변환 함수를 쓸 수 없음")


def start():
    vid = vehicle()
    assign(vid, EV)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    r = client.post("/charge-requests", headers=UH, json=body(vid, min_soc=20, parking_area="B"))
    assert r.status_code == 201, r.text
    return r.json()["request"]["id"]


def home():
    return client.get("/me/status", headers=UH).json()["vehicles"][0]


def wait_home(pred):
    for _ in range(60):  # 게이트웨이 메시지는 별도 스레드에서 반영된다
        v = home()
        if pred(v):
            return v
        time.sleep(0.05)
    return v


def test_ids_and_areas():
    assert area_of_zone("PARKING_05") == "B" and area_of_zone("PARKING_26") == "A" and area_of_zone("PARKING_57") == "C"
    assert area_of_zone(None) is None and area_of_zone("CHARGE_01") is None
    assert our_zone_id("PARKING_5") == "PARKING_05" and our_zone_id("CHARGER_01") == "CHARGER_01" and our_zone_id(None) is None
    env = to_controller("/charging/request", json.dumps({"request_id": "r", "vehicle_id": EV, "desired_finish_at": "2026-10-09T08:00:00Z",
                                                         "target_soc": 80, "min_soc": 20, "parking_zone_id": "PARKING_05"}))
    assert env["type"] == "charging_request" and env["payload"]["parking_zone_id"] == "B"  # 이전 방식(칸)도 구역으로 바꿔 보낸다
    env = to_controller("/charging/request", json.dumps({"request_id": "r", "vehicle_id": EV, "desired_finish_at": "2026-10-09T08:00:00Z",
                                                         "target_soc": 80, "min_soc": 20, "parking_area": "C"}))
    assert env["payload"]["parking_zone_id"] == "C"  # 관제 게이트웨이가 preferred_parking_zone으로 넘긴다
    assert to_controller("/charging/cancel", json.dumps({"request_id": "r", "vehicle_id": EV}))["type"] == "charging_cancel"
    assert to_controller("/emergency_stop", json.dumps({"action": "STOP"})) is None


def test_header_auth_required(gw):
    with client.websocket_connect("/ws/gateway", headers={"Authorization": "Bearer wrong"}) as s:
        with pytest.raises(WebSocketDisconnect):
            s.receive_text()


def test_full_flow_over_controller_gateway(gw):
    rid = start()  # 게이트웨이가 없을 때 만든 요청은 대기열에 쌓인다
    with client.websocket_connect("/ws/gateway", headers={"Authorization": f"Bearer {TOKEN}"}) as s:
        got = json.loads(s.receive_text())
        assert got["type"] == "charging_request" and got["payload"]["request_id"] == rid
        assert got["payload"]["vehicle_id"] == EV and got["payload"]["parking_zone_id"] == "B"

        def send(raw):
            s.send_text(json.dumps({"type": "central_status", "payload": payload(raw)}))

        send(raw_status(rid, "ACTIVE"))
        v = wait_home(lambda v: v["home_state"] == "QUEUED")
        assert v["state"] == "WAITING" and v["zone_id"] == "PARKING_33"
        av = client.get("/admin/vehicles", headers=AH).json()[0]
        assert av["pose"] == {"x": 1.0, "y": 2.0, "yaw": 0.5}

        send(raw_status(rid, "DISPATCHED", vehicle_state="DRIVING", location=None, task_id="TASK_EV-01_1"))
        v = wait_home(lambda v: v["home_state"] == "MOVING_TO_CHARGER")
        assert v["home_state"] == "MOVING_TO_CHARGER" and v["current_task"]["type"] == "MOVE_TO_CHARGER"

        send(raw_status(rid, "CHARGING", vehicle_state="PARKED", location="CHARGER_01", charger_state="CHARGING", soc=60, task_id="TASK_EV-01_1"))
        v = wait_home(lambda v: v["home_state"] == "CHARGING")
        assert v["home_state"] == "CHARGING" and v["charger_id"] == "CHARGER_01"

        send(raw_status(rid, "CHARGING", vehicle_state="DRIVING", location=None, charger_state="CHARGE_COMPLETE", soc=80,
                        task_id="TASK_EV-01_1", return_task_id="RETURN_EV-01_2", parking_purpose="FINAL", assigned_parking_slot="PARKING_5"))
        v = wait_home(lambda v: v["home_state"] == "MOVING_TO_PARKING")
        assert v["home_state"] == "MOVING_TO_PARKING" and v["active_request"]["status"] == "IN_PROGRESS"

        send(raw_status(rid, "COMPLETED", vehicle_state="PARKED", location="PARKING_5", soc=80, task_id="TASK_EV-01_1",
                        return_task_id="RETURN_EV-01_2", parking_purpose="FINAL", parking_arrived=True, assigned_parking_slot="PARKING_5"))
        v = wait_home(lambda v: v["home_state"] == "PARKED")
        assert v["home_state"] == "PARKED" and v["zone_id"] == "PARKING_05" and v["last_request"]["status"] == "COMPLETED"


def test_cancel_and_controller_rejection(gw):
    rid = start()
    with client.websocket_connect("/ws/gateway", headers={"Authorization": f"Bearer {TOKEN}"}) as s:
        s.receive_text()  # 대기열의 charging_request
        assert client.patch(f"/charge-requests/{rid}", headers=UH, json={"cancel": True}).status_code == 200
        assert json.loads(s.receive_text())["type"] == "charging_cancel"
        s.send_text(json.dumps({"type": "central_status", "payload": payload(raw_status(rid, "ACTIVE", cancel_requested=True))}))
        assert wait_home(lambda v: v["home_state"] == "CANCELING")["home_state"] == "CANCELING"
        s.send_text(json.dumps({"type": "central_status", "payload": payload(raw_status(rid, "CANCELED", parking_purpose="EXIT", parking_arrived=True))}))
        assert wait_home(lambda v: v["home_state"] == "CANCELLED")["home_state"] == "CANCELLED"

    rid2 = client.post("/charge-requests", headers=UH, json=body(home()["vehicle_id"])).json()["request"]["id"]
    with client.websocket_connect("/ws/gateway", headers={"Authorization": f"Bearer {TOKEN}"}) as s:
        s.receive_text()
        # 관제 게이트웨이의 submit_command 실패 응답 모양
        s.send_text(json.dumps({"type": "request_result", "request_id": rid2, "payload": {
            "accepted": False, "http_status": 422, "request_id": rid2,
            "error": json.dumps({"detail": {"error_code": "INVALID_SOC", "message": "target_soc invalid"}})}}))
        v = wait_home(lambda v: v["home_state"] == "REQUEST_FAILED")
        assert v["home_state"] == "REQUEST_FAILED" and "target_soc invalid" in v["last_request"]["failure_reason"]


def test_translated_status_always_passes_our_contract():
    raw = raw_status("11111111-1111-4111-8111-111111111111", "CHARGING", charger_state="RESERVED", location="PARKING_63")
    raw["vehicles"][0]["state"] = "ERROR"
    msg = status_from_controller(payload(raw))
    parse_topic("/central_status", json.dumps(msg))  # 형식 오류로 메시지 전체가 버려지지 않아야 한다
    assert msg["vehicles"][0]["state"] == "FAULT" and msg["vehicles"][0]["zone_id"] == "PARKING_63"
    assert [r["request_id"] for r in msg["requests"]] == ["11111111-1111-4111-8111-111111111111"]  # UUID 아닌 요청 제외
    assert msg["events"][0]["event_id"] and msg["events"][0]["type"] == "VEHICLE_TASK_DISPATCHED"


def test_cancel_of_request_unknown_to_controller_completes(gw, monkeypatch):
    rid = start()  # 관제 연결 전에 만든 요청(관제는 모른다)
    gw.pending.clear()
    monkeypatch.setattr(GatewayRosBridge, "CANCEL_GRACE_S", 0.0)
    with client.websocket_connect("/ws/gateway", headers={"Authorization": f"Bearer {TOKEN}"}) as s:
        assert client.patch(f"/charge-requests/{rid}", headers=UH, json={"cancel": True}).status_code == 200
        assert json.loads(s.receive_text())["type"] == "charging_cancel"
        again = client.patch(f"/charge-requests/{rid}", headers=UH, json={"cancel": True})  # 취소 중 다시 누르면 재전송
        assert again.status_code == 200 and json.loads(s.receive_text())["type"] == "charging_cancel"
        raw = raw_status(rid, "ACTIVE")
        raw["requests"] = []  # 관제 요청 목록에 없음
        s.send_text(json.dumps({"type": "central_status", "payload": payload(raw)}))
        assert wait_home(lambda v: v["home_state"] == "CANCELLED")["home_state"] == "CANCELLED"
