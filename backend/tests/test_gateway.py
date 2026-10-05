import json
from dataclasses import replace

import pytest
from starlette.websockets import WebSocketDisconnect

import main
import ws as ws_mod
from dev_sim import _msg
from ros_bridge import GatewayRosBridge
from ros_schemas.messages import ChargingCancelMsg
from tests.test_api import UH, assign, body, client, clean, vehicle  # noqa: F401  (clean은 autouse 픽스처)


@pytest.fixture
def gw(monkeypatch):
    bridge = GatewayRosBridge()
    bridge.on_central_status(main._on_central)
    monkeypatch.setattr(ws_mod, "ros", bridge)
    monkeypatch.setattr(ws_mod, "settings", replace(ws_mod.settings, gateway_token="secret-token"))
    return bridge


def test_gateway_rejects_bad_token(gw):
    with client.websocket_connect("/ws/gateway") as s:
        s.send_json({"type": "auth", "token": "wrong"})
        with pytest.raises(WebSocketDisconnect):
            s.receive_json()


def test_gateway_queues_while_offline_then_delivers_and_applies_status(gw):
    msg = ChargingCancelMsg(request_id="7d5d0b8a-0000-4000-8000-000000000001", vehicle_id="CAR_01", requested_by="user")
    gw.publish("/charging/cancel", msg)  # 게이트웨이가 아직 없다 → 대기열
    assert len(gw.pending) == 1 and not gw.connected
    vid = vehicle(); assign(vid)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    rid = client.post("/charge-requests", headers=UH, json=body(vid)).json()["request"]["id"]
    with client.websocket_connect("/ws/gateway") as s:
        s.send_json({"type": "auth", "token": "secret-token"})
        assert s.receive_json()["type"] == "auth_ok"
        got = json.loads(s.receive_text())  # 쌓여 있던 메시지가 먼저 온다
        assert got["topic"] == "/charging/cancel" and json.loads(got["data"])["vehicle_id"] == "CAR_01"
        assert gw.connected and not gw.pending
        s.send_text(json.dumps({"topic": "/central_status", "data": _msg("CAR_01", rid, "IN_PROGRESS", "CHARGING", 40, charger="CHARGER_01", zone="CHARGE_01")}))
        s.send_text("not json")  # 잘못된 메시지는 무시하고 연결 유지
        s.send_text(json.dumps({"topic": "/central_status", "data": _msg("CAR_01", rid, "IN_PROGRESS", "CHARGING", 41, charger="CHARGER_01", zone="CHARGE_01")}))
        import time

        for _ in range(40):  # 메시지는 별도 스레드에서 처리되므로 반영될 때까지 잠깐 기다린다
            st = client.get("/me/status", headers=UH).json()["vehicles"][0]
            if st["soc"] == 41:
                break
            time.sleep(0.05)
    assert st["state"] == "CHARGING" and st["soc"] == 41
    assert not gw.connected  # 연결이 끊기면 다시 대기열 모드
