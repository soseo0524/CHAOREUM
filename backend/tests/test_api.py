import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import models as m
from database import Base, SessionLocal, engine
from main import app
from schemas.parking_map import ALL_SEAT_NUMBERS, AREA_ROWS, seat_no_of, seat_zone_id
from seed import seed_dev, sync_parking_zones
from state import ros

client = TestClient(app)
USER, ADMIN = uuid.uuid4(), uuid.uuid4()
H = lambda uid, role: {"Authorization": f"Bearer dev:{uid}:{role}"}
UH, AH = H(USER, "user"), H(ADMIN, "admin")
iso = lambda **k: (datetime.now(timezone.utc) + timedelta(**k)).isoformat()


@pytest.fixture(autouse=True)
def clean():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_dev(db)
    ros.published.clear()


def db_rows(model):
    with SessionLocal() as db:
        return list(db.scalars(__import__("sqlalchemy").select(model)))


def vehicle():
    r = client.post("/vehicles", headers=UH, json=dict(plate_no="12가3456", battery_kwh=60, max_charge_kw=11))
    assert r.status_code == 201, r.text
    assert "ros_vehicle_id" not in r.json() and r.json()["assigned"] is False
    return r.json()["id"]


def assign(vid, ros_id="CAR_01"):
    r = client.patch(f"/admin/vehicles/{vid}", headers=AH, json=dict(ros_vehicle_id=ros_id, reason="배정"))
    assert r.status_code == 200, r.text


def body(vid, **k):
    return dict(vehicle_id=vid, desired_finish_at=iso(hours=5), target_soc=80, **k)


def test_auth_and_roles():
    assert client.get("/me").status_code == 401
    assert client.get("/admin/overview", headers=UH).status_code == 403
    assert client.get("/vehicles", headers=AH).status_code == 403
    assert client.get("/admin/overview", headers=AH).status_code == 200


def test_plate_duplicate_and_validation_shape():
    vehicle()
    r = client.post("/vehicles", headers=UH, json=dict(plate_no="12가3456", battery_kwh=60, max_charge_kw=11))
    assert r.status_code == 409 and r.json()["code"] == "PLATE_DUPLICATED"
    r = client.post("/vehicles", headers=UH, json=dict(plate_no="x", battery_kwh=-1, max_charge_kw=11))
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"


def test_charge_request_gates_in_order():
    vid = vehicle()
    r = client.post("/charge-requests", headers=UH, json=body(vid))
    assert r.status_code == 422 and r.json()["code"] == "VEHICLE_NOT_ASSIGNED"
    assign(vid)
    r = client.post("/charge-requests", headers=UH, json=body(vid))
    assert r.status_code == 403 and r.json()["code"] == "CONSENT_REQUIRED"
    assert client.post("/consents", headers=UH, json=dict(version="v1")).status_code == 201


def test_full_flow_publishes_ros_and_blocks_duplicate():
    vid = vehicle(); assign(vid)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    dry = client.post("/charge-requests", headers=UH, json=body(vid, dry_run=True))
    assert dry.status_code == 200 and dry.json()["request"] is None and dry.json()["feasibility"]["feasible"]
    assert not ros.published
    r = client.post("/charge-requests", headers=UH, json=body(vid))
    assert r.status_code == 201, r.text
    rid = r.json()["request"]["id"]
    sent = ros.last("/charging/request")
    assert sent["vehicle_id"] == "CAR_01" and sent["request_id"] == rid and sent["battery_kwh"] == 60
    d = client.post("/charge-requests", headers=UH, json=body(vid))
    assert d.status_code == 409 and d.json()["code"] == "ACTIVE_REQUEST_EXISTS"
    # 수정 → 같은 request_id로 재발행
    p = client.patch(f"/charge-requests/{rid}", headers=UH, json=dict(target_soc=90))
    assert p.status_code == 200 and ros.last("/charging/request")["target_soc"] == 90
    # 취소
    c = client.patch(f"/charge-requests/{rid}", headers=UH, json=dict(cancel=True))
    assert c.json()["request"]["status"] == "CANCEL_REQUESTED" and ros.last("/charging/cancel")["request_id"] == rid
    assert client.delete(f"/vehicles/{vid}", headers=UH).status_code == 409  # 활성 요청 중 삭제 불가


def test_infeasible_deadline():
    vid = vehicle(); assign(vid)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    r = client.post("/charge-requests", headers=UH, json=dict(vehicle_id=vid, desired_finish_at=iso(seconds=30), target_soc=80))
    assert r.status_code == 422 and r.json()["code"] == "DEADLINE_INFEASIBLE"
    assert r.json()["details"]["feasibility"]["earliest_parked_at"]


def test_other_users_vehicle_hidden():
    vid = vehicle()
    other = H(uuid.uuid4(), "user")
    assert client.get(f"/vehicles/{vid}", headers=other).status_code == 404


def central(vehicle_id, state, rid=None, status=None, extra=None):
    now = datetime.now(timezone.utc).isoformat()
    d = dict(at=now, vehicles=[dict(vehicle_id=vehicle_id, state=state, soc=55, zone_id="CHARGE_01", last_seen_at=now)], chargers=[dict(charger_id="CHARGER_01", state="IN_USE", vehicle_id=vehicle_id, power_kw=7)], events=[dict(event_id="e1", type="CHARGE_STARTED", at=now)])
    if rid:
        d["requests"] = [dict(request_id=rid, vehicle_id=vehicle_id, status=status)]
    if extra:
        d.update(extra)
    ros.inject_central_status(json.dumps(d))


def test_central_status_updates_me_status_and_admin():
    vid = vehicle(); assign(vid)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    rid = client.post("/charge-requests", headers=UH, json=body(vid)).json()["request"]["id"]
    central("CAR_01", "CHARGING", rid, "IN_PROGRESS")
    st = client.get("/me/status", headers=UH).json()["vehicles"][0]
    assert st["state"] == "CHARGING" and st["step"] == 2 and st["step_label"] == "충전중" and st["online"]
    assert st["active_request"]["status"] == "IN_PROGRESS"
    central("CAR_01", "PARKED", rid, "COMPLETED")
    st = client.get("/me/status", headers=UH).json()["vehicles"][0]
    assert st["step"] == 5 and st["active_request"] is None
    central("CAR_01", "PARKED")  # 같은 event_id 재수신 → 중복 저장 안 됨
    assert len(client.get("/admin/events", headers=AH).json()) == 1
    ov = client.get("/admin/overview", headers=AH).json()
    assert ov["vehicles_by_state"]["PARKED"] == 1 and ov["chargers_by_state"]["IN_USE"] == 1 and ov["central_online"]


def test_admin_ros_id_rules_and_audit():
    v1 = vehicle(); assign(v1)
    v2 = client.post("/vehicles", headers=UH, json=dict(plate_no="99나9999", battery_kwh=50, max_charge_kw=7)).json()["id"]
    r = client.patch(f"/admin/vehicles/{v2}", headers=AH, json=dict(ros_vehicle_id="CAR_01", reason="중복"))
    assert r.status_code == 409 and r.json()["code"] == "ROS_ID_DUPLICATED"
    assert client.patch(f"/admin/vehicles/{v2}", headers=AH, json=dict(ros_vehicle_id="CAR_02")).status_code == 422  # reason 누락
    audits = db_rows(m.AuditLog)
    assert len(audits) == 1 and audits[0].reason == "배정" and audits[0].action == "vehicle.assign_ros_id"


def test_emergency_stop_and_audit():
    r = client.post("/admin/emergency-stop", headers=AH, json=dict(action="STOP", reason="장애물"))
    assert r.json()["active"] is True
    m = ros.last("/emergency_stop")
    assert m["action"] == "STOP" and m["vehicle_id"] == "ALL"


def test_withdraw_blocked_then_ok():
    vid = vehicle(); assign(vid)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    client.post("/charge-requests", headers=UH, json=body(vid))
    assert client.request("DELETE", "/me", headers=UH, json=dict(confirm=True)).status_code == 409
    with SessionLocal() as db:
        r = db.scalars(__import__("sqlalchemy").select(m.ChargeRequest)).one()
        r.status = "CANCELLED"
        db.commit()
    assert client.request("DELETE", "/me", headers=UH, json=dict(confirm=True)).status_code == 200
    assert all(v.deleted_at is not None and v.owner_id is None for v in db_rows(m.Vehicle))
    assert USER not in {p.id for p in db_rows(m.Profile)} and db_rows(m.Consent) == []


def test_websocket_auth_and_push():
    vid = vehicle(); assign(vid)
    with client.websocket_connect("/ws/status") as ws:
        ws.send_json(dict(type="auth", token=f"dev:{USER}:user"))
        assert ws.receive_json() == {"type": "auth_ok", "role": "user"}
        central("CAR_01", "MOVING_TO_CHARGER")
        m = ws.receive_json()
        assert m["type"] == "vehicle_status" and m["data"]["step"] == 1
    with client.websocket_connect("/ws/status") as ws:
        ws.send_json(dict(type="auth", token="bad"))
        with pytest.raises(Exception):
            ws.receive_json()


def test_unknown_zone_is_ignored_not_crash():
    vid = vehicle(); assign(vid)
    now = datetime.now(timezone.utc).isoformat()
    d = dict(at=now, vehicles=[dict(vehicle_id="CAR_01", state="PARKED", soc=100, zone_id="NOT_A_ZONE", charger_id="NOPE", last_seen_at=now)])
    ros.inject_central_status(json.dumps(d))
    st = client.get("/me/status", headers=UH).json()["vehicles"][0]
    assert st["state"] == "PARKED" and st["zone_id"] is None


def test_tasks_upsert_and_admin_cancel():
    vid = vehicle(); assign(vid)
    tid, rid = str(uuid.uuid4()), str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    task = dict(task_id=tid, request_id=rid, vehicle_id="CAR_01", type="MOVE_TO_CHARGER", status="RUNNING", target_id="CHARGER_01", target_pose=dict(x=1, y=2, yaw=0.5), progress=0.3)
    d = dict(at=now, tasks=[task], vehicles=[dict(vehicle_id="CAR_01", state="MOVING_TO_CHARGER", soc=40, current_task_id=tid, progress=0.3, last_seen_at=now)])
    ros.inject_central_status(json.dumps(d))
    st = client.get("/me/status", headers=UH).json()["vehicles"][0]
    assert st["current_task"]["id"] == tid and st["current_task"]["status"] == "RUNNING" and st["step"] == 1
    t = db_rows(m.VehicleTask)[0]
    assert t.request_id is None and t.started_at is not None  # 알 수 없는 request_id는 NULL로
    r = client.post(f"/admin/tasks/{tid}/cancel", headers=AH, json=dict(reason="수동 취소"))
    assert r.status_code == 200 and ros.last("/admin/command")["task_id"] == tid


def test_charger_maintenance_rules():
    assert client.get("/admin/chargers", headers=AH).json()[0]["state"] is None  # 아직 상태 미수신
    vid = vehicle(); assign(vid)
    central("CAR_01", "CHARGING")  # CHARGER_01 IN_USE
    r = client.patch("/admin/chargers/CHARGER_01", headers=AH, json=dict(state="MAINTENANCE", reason="점검 예약"))
    assert r.status_code == 200 and r.json()["state"] == "IN_USE" and r.json()["maintenance"] is True
    r = client.patch("/admin/chargers/CHARGER_02", headers=AH, json=dict(state="MAINTENANCE", reason="점검"))
    assert r.json()["state"] == "MAINTENANCE"
    r = client.patch("/admin/chargers/CHARGER_02", headers=AH, json=dict(max_power_kw=7, reason="출력 제한"))
    assert r.json()["max_power_kw"] == 7
    assert client.get("/admin/overview", headers=AH).json()["chargers_by_state"]["MAINTENANCE"] == 1


def test_db_blocks_second_active_request_even_if_app_check_skipped():
    from sqlalchemy.exc import IntegrityError
    vid = vehicle(); assign(vid)
    with SessionLocal() as db:
        f = datetime.now(timezone.utc) + timedelta(hours=5)
        db.add(m.ChargeRequest(vehicle_id=uuid.UUID(vid), desired_finish_at=f, target_soc=80, min_soc=0))
        db.commit()
        db.add(m.ChargeRequest(vehicle_id=uuid.UUID(vid), desired_finish_at=f, target_soc=80, min_soc=0))
        with pytest.raises(IntegrityError):
            db.commit()


def test_dev_simulator_walks_five_steps_to_completed():
    vid = vehicle(); assign(vid)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    rid = client.post("/charge-requests", headers=UH, json=body(vid)).json()["request"]["id"]
    seen = []
    orig = ros._cb
    def spy(msg):
        orig(msg)
        seen.append(client.get("/me/status", headers=UH).json()["vehicles"][0]["step"])
    ros.on_central_status(spy)
    try:
        assert client.post("/dev/simulate?step_s=0&wait=true", headers=UH).status_code == 200
    finally:
        ros.on_central_status(orig)
    steps = [x for x in seen if x]
    assert steps[0] == 1 and steps[-1] == 5 and steps == sorted(steps) and {1, 2, 3, 4, 5} <= set(steps)
    st = client.get("/me/status", headers=UH).json()["vehicles"][0]
    assert st["state"] == "PARKED" and st["zone_id"] == "PARKING_01" and st["active_request"] is None
    r = db_rows(m.ChargeRequest)[0]
    assert str(r.id) == rid and r.status == "COMPLETED" and r.completed_at is not None
    assert len(db_rows(m.VehicleTask)) == 2


def test_parking_zone_pick_list_full_and_edit():
    vid = vehicle(); assign(vid)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    zs = client.get("/parking-zones", headers=UH).json()
    assert {z["id"] for z in zs} == {seat_zone_id(n) for n in ALL_SEAT_NUMBERS} and len(zs) == 57
    assert all(z["is_available"] and z["capacity"] == 1 for z in zs)
    bad = client.post("/charge-requests", headers=UH, json=body(vid, parking_zone_id="CHARGE_01"))  # PARKING 아님
    assert bad.status_code == 422
    r = client.post("/charge-requests", headers=UH, json=body(vid, parking_zone_id="PARKING_01"))
    assert r.status_code == 201 and r.json()["request"]["parking_zone_id"] == "PARKING_01"
    assert ros.last("/charging/request")["parking_zone_id"] == "PARKING_01"
    z1 = next(z for z in client.get("/parking-zones", headers=UH).json() if z["id"] == "PARKING_01")
    assert z1["available"] == z1["capacity"] - 1
    rid = r.json()["request"]["id"]
    p = client.patch(f"/charge-requests/{rid}", headers=UH, json=dict(parking_zone_id="PARKING_02"))
    assert p.status_code == 200 and ros.last("/charging/request")["parking_zone_id"] == "PARKING_02"
    # 자동 배정은 null
    client.patch(f"/charge-requests/{rid}", headers=UH, json=dict(cancel=True))


def test_parking_zone_full_returns_409():
    with SessionLocal() as db:
        z = db.get(m.ParkingZone, "PARKING_02"); z.capacity = 1
        db.commit()
    other = uuid.uuid4()
    oh = H(other, "user")
    r = client.post("/vehicles", headers=oh, json=dict(plate_no="99나9999", battery_kwh=60, max_charge_kw=11)).json()
    client.patch(f"/admin/vehicles/{r['id']}", headers=AH, json=dict(ros_vehicle_id="CAR_02", reason="배정"))
    client.post("/consents", headers=oh, json=dict(version="v1"))
    assert client.post("/charge-requests", headers=oh, json=body(r["id"], parking_zone_id="PARKING_02")).status_code == 201
    vid = vehicle(); assign(vid)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    full = client.post("/charge-requests", headers=UH, json=body(vid, parking_zone_id="PARKING_02"))
    assert full.status_code == 409 and full.json()["code"] == "PARKING_ZONE_UNAVAILABLE"
    assert client.post("/charge-requests", headers=UH, json=body(vid)).status_code == 201  # 자동 배정은 가능


def test_queue_position_and_wait_in_status():
    # 다른 사용자의 요청이 먼저 있으면 내 순번은 2번째, 예상 대기 = 앞선 1대 × avg_service_min
    other = uuid.uuid4(); oh = H(other, "user")
    ov = client.post("/vehicles", headers=oh, json=dict(plate_no="99허9999", battery_kwh=60, max_charge_kw=11)).json()["id"]
    assign(ov, "CAR_02"); client.post("/consents", headers=oh, json=dict(version="v1"))
    assert client.post("/charge-requests", headers=oh, json=body(ov)).status_code == 201
    vid = vehicle(); assign(vid); client.post("/consents", headers=UH, json=dict(version="v1"))
    assert client.post("/charge-requests", headers=UH, json=body(vid)).status_code == 201
    with SessionLocal() as db:  # 시각 해상도(초)와 무관하게 순서를 고정: 다른 사용자의 요청을 1분 먼저 접수한 것으로
        r0 = db.scalar(__import__("sqlalchemy").select(m.ChargeRequest).where(m.ChargeRequest.vehicle_id == uuid.UUID(ov)))
        r0.created_at = r0.created_at - timedelta(minutes=1); db.commit()
    ar = client.get("/me/status", headers=UH).json()["vehicles"][0]["active_request"]
    assert ar["queue_position"] == 2 and ar["estimated_wait_min"] == 12
    first = client.get("/me/status", headers=oh).json()["vehicles"][0]["active_request"]
    assert first["queue_position"] == 1 and first["estimated_wait_min"] == 0


def test_notification_settings_push_token_and_read():
    s = client.get("/me/notification-settings", headers=UH).json()
    assert s == dict(charge_done=True, parked=True, fault=True, queue_change=False)
    s = client.patch("/me/notification-settings", headers=UH, json=dict(queue_change=True, parked=False)).json()
    assert s == dict(charge_done=True, parked=False, fault=True, queue_change=True)
    assert client.get("/me/notification-settings", headers=UH).json() == s  # 저장됨
    tok = dict(token="ExponentPushToken[abc]", platform="ios")
    assert client.post("/me/push-tokens", headers=UH, json=tok).status_code == 201
    assert client.post("/me/push-tokens", headers=UH, json=tok).status_code == 201  # 중복 등록은 갱신
    assert len(db_rows(m.PushToken)) == 1
    assert client.request("DELETE", "/me/push-tokens", headers=UH, json=tok).status_code == 200 and not db_rows(m.PushToken)
    with SessionLocal() as db:
        n = m.Notification(user_id=USER, type="PARKED", title="t", body="b", data={}); db.add(n); db.commit(); nid = str(n.id)
    assert client.post(f"/me/notifications/{nid}/read", headers=UH).json()["read_at"] is not None
    assert client.post(f"/me/notifications/{uuid.uuid4()}/read", headers=UH).status_code == 404
    with SessionLocal() as db:
        db.add_all([m.Notification(user_id=USER, type="PARKED", title="t", body="b", data={}) for _ in range(2)]); db.commit()
    assert client.post("/me/notifications/read-all", headers=UH).status_code == 200
    assert all(n["read_at"] for n in client.get("/me/notifications", headers=UH).json())


def test_simulated_run_creates_sessions_notifications_and_push():
    import push
    push.sent.clear()
    vid = vehicle(); assign(vid)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    client.post("/me/push-tokens", headers=UH, json=dict(token="ExponentPushToken[x]", platform="android"))
    client.patch("/me/notification-settings", headers=UH, json=dict(parked=False))  # 주차 완료 푸시는 끈다
    client.post("/charge-requests", headers=UH, json=body(vid))
    assert client.post("/dev/simulate?step_s=0&wait=true", headers=UH).status_code == 200
    kinds = [n["type"] for n in client.get("/me/notifications", headers=UH).json()]
    assert "CHARGE_DONE" in kinds and "PARKED" in kinds  # 알림함에는 둘 다 쌓인다
    titles = [p["title"] for p in push.sent]
    assert "충전이 끝났어요" in titles and "주차가 끝났어요" not in titles  # 설정이 꺼진 종류는 푸시하지 않는다
    sessions = client.get("/me/sessions", headers=UH).json()
    assert len(sessions) == 1 and sessions[0]["end_at"] and sessions[0]["end_soc"] >= sessions[0]["start_soc"] and sessions[0]["energy_kwh"] > 0
    assert sessions[0]["vehicle_id"] == vid


def test_queue_change_notice_when_someone_ahead_cancels():
    import push
    push.sent.clear()
    other = uuid.uuid4(); oh = H(other, "user")
    ov = client.post("/vehicles", headers=oh, json=dict(plate_no="99허9999", battery_kwh=60, max_charge_kw=11)).json()["id"]
    assign(ov, "CAR_02"); client.post("/consents", headers=oh, json=dict(version="v1"))
    first = client.post("/charge-requests", headers=oh, json=body(ov)).json()["request"]["id"]
    vid = vehicle(); assign(vid); client.post("/consents", headers=UH, json=dict(version="v1"))
    client.post("/charge-requests", headers=UH, json=body(vid))
    with SessionLocal() as db:  # 순서 고정: 다른 사용자가 1분 먼저
        r0 = db.get(m.ChargeRequest, uuid.UUID(first)); r0.created_at = r0.created_at - timedelta(minutes=1); db.commit()
    client.post("/me/push-tokens", headers=UH, json=dict(token="ExponentPushToken[q]", platform="ios"))
    client.patch("/me/notification-settings", headers=UH, json=dict(queue_change=True))
    assert client.patch(f"/charge-requests/{first}", headers=oh, json=dict(cancel=True)).status_code == 200
    n = [x for x in client.get("/me/notifications", headers=UH).json() if x["type"] == "QUEUE_CHANGED"]
    assert len(n) == 1 and n[0]["body"] == "다음 차례예요." and n[0]["data"]["queue_position"] == 1
    assert [p["title"] for p in push.sent] == ["대기 순번이 앞당겨졌어요"]
    assert not [x for x in client.get("/me/notifications", headers=oh).json() if x["type"] == "QUEUE_CHANGED"]  # 취소한 본인에게는 없다


def test_charge_energy_and_cost_follow_the_flow_and_history():
    from config import settings
    price = settings.unit_price_won_per_kwh
    vid = vehicle(); assign(vid)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    assert client.post("/charge-requests", headers=UH, json=body(vid)).status_code == 201
    assert client.get("/me/status", headers=UH).json()["vehicles"][0]["charge"] is None  # 충전 전엔 없음
    seen = []
    orig = ros._cb
    def spy(msg):
        orig(msg)
        v = client.get("/me/status", headers=UH).json()["vehicles"][0]
        if v["charge"]:
            seen.append((v["state"], v["charge"]))
    ros.on_central_status(spy)
    try:
        assert client.post("/dev/simulate?step_s=0&wait=true", headers=UH).status_code == 200
    finally:
        ros.on_central_status(orig)
    assert seen and seen[0][1]["in_progress"] is True  # 충전 중에는 값이 늘어나는 중
    final = client.get("/me/status", headers=UH).json()["vehicles"][0]
    ch = final["charge"]
    assert final["state"] == "PARKED" and ch["in_progress"] is False  # 주차 완료 뒤에도 금액이 보인다
    assert ch["energy_kwh"] > 0 and ch["unit_price_won"] == price and ch["cost_won"] == round(ch["energy_kwh"] * price)
    s = client.get("/me/sessions", headers=UH).json()[0]  # 이력·상세에도 같은 값
    assert s["energy_kwh"] == ch["energy_kwh"] and s["unit_price_won"] == price and s["cost_won"] == ch["cost_won"]
    energies = [c["energy_kwh"] for st, c in seen if st == "CHARGING"]
    assert energies == sorted(energies)  # 충전 중 값은 줄지 않는다


def test_cost_keeps_the_price_at_session_start(monkeypatch):
    import config
    import services
    vid = vehicle(); assign(vid)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    client.post("/charge-requests", headers=UH, json=body(vid))
    client.post("/dev/simulate?step_s=0&wait=true", headers=UH)
    before = client.get("/me/status", headers=UH).json()["vehicles"][0]["charge"]
    import dataclasses
    monkeypatch.setattr(services, "settings", dataclasses.replace(services.settings, unit_price_won_per_kwh=999))
    after = client.get("/me/status", headers=UH).json()["vehicles"][0]["charge"]
    assert after["unit_price_won"] == before["unit_price_won"] and after["cost_won"] == before["cost_won"]  # 단가를 바꿔도 지난 세션 금액은 그대로


def test_parking_seat_numbering_is_0_to_65_with_57_seats():
    missing = {12, 14, 27, 30, 31, 34, 35, 39, 44}
    assert ALL_SEAT_NUMBERS == [n for n in range(66) if n not in missing] and len(ALL_SEAT_NUMBERS) == 57
    assert [len(sum(AREA_ROWS[a], [])) for a in "ABC"] == [17, 26, 14] and [len(AREA_ROWS[a]) for a in "ABC"] == [1, 2, 1]
    assert seat_zone_id(0) == "PARKING_00" and seat_zone_id(65) == "PARKING_65"
    assert seat_no_of("PARKING_00") == 0 and seat_no_of("PARKING_65") == 65 and seat_no_of("CHARGE_01") is None and seat_no_of(None) is None
    assert sorted(z.id for z in db_rows(m.ParkingZone) if z.kind == "PARKING") == [seat_zone_id(n) for n in ALL_SEAT_NUMBERS]


def test_seed_sync_replaces_old_21_seat_layout():
    from schemas.common import ParkingZoneKind
    with SessionLocal() as db:
        db.add(m.ParkingZone(id="PARKING_14", name="14번 자리", kind=ParkingZoneKind.PARKING, capacity=1, pose_x=0.0, pose_y=0.0, pose_yaw=0.0))  # 옛 지도의 자리
        db.delete(db.get(m.ParkingZone, "PARKING_65"))
        db.commit()
        sync_parking_zones(db); db.commit()
        sync_parking_zones(db); db.commit()  # 반복 실행해도 같다
        assert db.get(m.ParkingZone, "PARKING_14") is None and db.get(m.ParkingZone, "PARKING_65") is not None
    assert len([z for z in db_rows(m.ParkingZone) if z.kind == "PARKING"]) == 57


def test_parked_notice_says_seat_number_including_zero():
    vid = vehicle(); assign(vid)
    now = datetime.now(timezone.utc).isoformat()
    for zone, text in (("PARKING_00", "0번 자리에 도착했어요."), ("PARKING_65", "65번 자리에 도착했어요.")):
        ros.inject_central_status(json.dumps(dict(at=now, vehicles=[dict(vehicle_id="CAR_01", state="CHARGE_DONE", soc=80, zone_id="CHARGE_01", last_seen_at=now)])))
        ros.inject_central_status(json.dumps(dict(at=now, vehicles=[dict(vehicle_id="CAR_01", state="PARKED", soc=80, zone_id=zone, last_seen_at=now)])))
        assert text in [n["body"] for n in client.get("/me/notifications", headers=UH).json()]


def test_parking_areas_overview_and_detail():
    r = client.get("/parking-zones/areas", headers=UH).json()["areas"]
    assert [a["area_id"] for a in r] == ["A", "B", "C"] and [a["name"] for a in r] == ["A구역", "B구역", "C구역"]
    assert [a["seat_total"] for a in r] == [17, 26, 14] and [a["free_count"] for a in r] == [17, 26, 14]
    assert all(a["state"] == "OPEN" and not a["has_mine"] for a in r)
    assert [x["seat_no"] for x in r[0]["seats"]] == [61, 45, 43, 42, 40, 41, 38, 37, 36, 58, 33, 32, 59, 29, 28, 62, 26]  # 실제 배치 순서
    assert r[1]["seats"][0]["zone_id"] == "PARKING_00" and r[2]["seats"][0]["zone_id"] == "PARKING_57" and r[2]["seats"][-1]["zone_id"] == "PARKING_64"
    d = client.get("/parking-zones/areas/a", headers=UH).json()  # 대소문자 무관
    assert d["area_id"] == "A" and d["rows"] == 1 and d["cols"] == 17 and d["entrance"] is None
    pos = {x["seat_no"]: (x["row"], x["col"]) for x in d["seats"]}
    assert pos[61] == (0, 0) and pos[33] == (0, 10) and pos[26] == (0, 16) and len(pos) == 17  # 한 줄 17칸
    assert d["selected_ok"] is None and all(x["state"] == "FREE" for x in d["seats"])
    b = client.get("/parking-zones/areas/B", headers=UH).json()
    assert b["rows"] == 2 and b["cols"] == 13 and b["seat_total"] == 26
    pos = {x["seat_no"]: (x["row"], x["col"]) for x in b["seats"]}
    assert pos[0] == (0, 0) and pos[60] == (0, 12) and pos[25] == (1, 0) and pos[63] == (1, 12) and pos[13] == (1, 11)  # 두 줄 13칸씩
    c = client.get("/parking-zones/areas/C", headers=UH).json()
    assert c["rows"] == 1 and c["cols"] == 14 and {x["seat_no"] for x in c["seats"]} == set(AREA_ROWS["C"][0])
    assert client.get("/parking-zones/areas/Z", headers=UH).status_code == 404
    assert client.get("/parking-zones/areas").status_code in (401, 403)
    # 고르는 중인 자리는 MINE, 구역 밖 자리를 보내도 이 구역은 그대로
    sel = client.get("/parking-zones/areas/A?selected=PARKING_33", headers=UH).json()
    assert [x["state"] for x in sel["seats"] if x["seat_no"] == 33] == ["MINE"] and sel["selected_ok"] is True
    outside = client.get("/parking-zones/areas/A?selected=PARKING_03", headers=UH).json()  # 3번은 B구역
    assert all(x["state"] == "FREE" for x in outside["seats"])
    # 다른 사용자가 33번을 선정하면 TAKEN(02-A.02), 내 쪽 selected_ok=false. 주인 화면에서는 MINE
    other = uuid.uuid4(); oh = H(other, "user")
    ov = client.post("/vehicles", headers=oh, json=dict(plate_no="99허9999", battery_kwh=60, max_charge_kw=11)).json()["id"]
    assign(ov, "CAR_02"); client.post("/consents", headers=oh, json=dict(version="v1"))
    assert client.post("/charge-requests", headers=oh, json=body(ov, parking_zone_id="PARKING_33")).status_code == 201
    mine_view = client.get("/parking-zones/areas/A?selected=PARKING_33", headers=UH).json()
    assert [x["state"] for x in mine_view["seats"] if x["seat_no"] == 33] == ["TAKEN"] and mine_view["selected_ok"] is False and mine_view["free_count"] == 16
    owner_view = client.get("/parking-zones/areas/A", headers=oh).json()
    assert [x["state"] for x in owner_view["seats"] if x["seat_no"] == 33] == ["MINE"]
    ov_all = client.get("/parking-zones/areas", headers=oh).json()["areas"]
    assert ov_all[0]["has_mine"] is True and ov_all[0]["free_count"] == 17 and ov_all[1]["has_mine"] is False  # 내 자리는 내 화면에서 빈자리로 세지 않는 TAKEN이 아님
    assert client.get("/parking-zones/areas", headers=UH).json()["areas"][0]["free_count"] == 16


def test_full_area_is_marked_full():
    with SessionLocal() as db:
        for n in sum(AREA_ROWS["B"], []):
            z = db.get(m.ParkingZone, seat_zone_id(n))
            z.capacity = 0
        db.commit()
    areas = {a["area_id"]: a for a in client.get("/parking-zones/areas", headers=UH).json()["areas"]}
    assert areas["B"]["state"] == "FULL" and areas["B"]["free_count"] == 0 and areas["B"]["seat_total"] == 26 and areas["A"]["state"] == "OPEN"
    assert client.get("/parking-zones/areas/B", headers=UH).json()["state"] == "FULL"


def hs():
    return client.get("/me/status", headers=UH).json()


def test_home_state_covers_every_screen():
    # 등록 차량 없음
    j = hs()
    assert j["vehicles"] == [] and j["empty_reason"] == "NO_VEHICLE"
    # 배정 대기(2-9)
    vid = vehicle()
    v = hs()["vehicles"][0]
    assert v["home_state"] == "WAITING_ASSIGNMENT" and v["eta"]["state"] == "NONE" and hs()["empty_reason"] is None
    # 배정됐지만 상태 미수신(로딩/데이터 없음, 2-10)
    assign(vid)
    v = hs()["vehicles"][0]
    assert v["home_state"] == "NO_DATA" and v["soc"] is None and v["eta"]["state"] == "NONE"
    client.post("/consents", headers=UH, json=dict(version="v1"))
    # 요청 없음(2-0)
    central("CAR_01", "WAITING")
    v = hs()["vehicles"][0]
    assert v["home_state"] == "NO_REQUEST" and v["last_request"] is None
    # 접수·대기(2-0b): 예상 시간 없으면 '계산 중'
    rid = client.post("/charge-requests", headers=UH, json=body(vid)).json()["request"]["id"]
    v = hs()["vehicles"][0]
    assert v["home_state"] == "QUEUED" and v["eta"]["state"] == "CALCULATING"
    # 진행 단계
    for state, want in [("MOVING_TO_CHARGER", "MOVING_TO_CHARGER"), ("CHARGING", "CHARGING"), ("CHARGE_DONE", "CHARGE_DONE"), ("MOVING_TO_PARKING", "MOVING_TO_PARKING")]:
        central("CAR_01", state, rid, "IN_PROGRESS")
        assert hs()["vehicles"][0]["home_state"] == want
    # 예상 완료시간이 오면 KNOWN
    fin = iso(minutes=20)
    central("CAR_01", "CHARGING", rid, "IN_PROGRESS")
    d = dict(at=iso(), vehicles=[dict(vehicle_id="CAR_01", state="CHARGING", soc=60, zone_id="CHARGE_01", last_seen_at=iso(), estimated_completion=fin)])
    ros.inject_central_status(json.dumps(d))
    v = hs()["vehicles"][0]
    assert v["eta"]["state"] == "KNOWN" and v["eta"]["at"]
    # 연결 끊김(2-11): 마지막 값은 유지, last_seen_at 으로 시각 표시
    with SessionLocal() as db:
        st = db.get(m.VehicleStateRow, uuid.UUID(vid))
        st.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=3)
        db.commit()
    v = hs()["vehicles"][0]
    assert v["home_state"] == "VEHICLE_OFFLINE" and v["online"] is False and v["soc"] == 60 and v["last_seen_at"] and v["eta"]["state"] == "NONE"  # 끊기면 예상 시간은 '—'
    # 완료(5단계)
    central("CAR_01", "PARKED", rid, "COMPLETED")
    v = hs()["vehicles"][0]
    assert v["home_state"] == "PARKED" and v["eta"]["state"] == "NONE"
    # 차량 문제
    central("CAR_01", "FAULT")
    assert hs()["vehicles"][0]["home_state"] == "FAULT"


def test_request_failed_cancelling_cancelled_states():
    vid = vehicle(); assign(vid)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    rid = client.post("/charge-requests", headers=UH, json=body(vid)).json()["request"]["id"]
    central("CAR_01", "MOVING_TO_CHARGER", rid, "IN_PROGRESS")
    # 취소 처리 중(2-6)
    assert client.patch(f"/charge-requests/{rid}", headers=UH, json=dict(cancel=True)).status_code == 200
    v = hs()["vehicles"][0]
    assert v["home_state"] == "CANCELING" and v["active_request"]["status"] == "CANCEL_REQUESTED"
    # 취소 완료(2-7): 관제가 CANCELLED 보고
    central("CAR_01", "WAITING", rid, "CANCELLED")
    v = hs()["vehicles"][0]
    assert v["home_state"] == "CANCELLED" and v["last_request"]["status"] == "CANCELLED" and v["active_request"] is None
    # 새 요청을 넣으면 결과 화면은 사라진다
    rid2 = client.post("/charge-requests", headers=UH, json=body(vid)).json()["request"]["id"]
    assert hs()["vehicles"][0]["last_request"] is None
    # 실패(2-5): 작업 실패 사유가 그대로 내려간다
    tid = str(uuid.uuid4())
    task = dict(task_id=tid, vehicle_id="CAR_01", request_id=rid2, type="MOVE_TO_CHARGER", target_id="CHARGER_01", target_pose=dict(x=0, y=0, yaw=0), status="FAILED", error_message="충전기 통신 오류")
    central("CAR_01", "WAITING", rid2, "FAILED", extra=dict(tasks=[task]))
    v = hs()["vehicles"][0]
    assert v["home_state"] == "REQUEST_FAILED" and v["last_request"]["failure_reason"] == "충전기 통신 오류"
    assert any(n["type"] == "REQUEST_FAILED" and "충전기 통신 오류" in n["body"] for n in client.get("/me/notifications", headers=UH).json())
    # 24시간이 지나면 결과 화면은 '요청 없음'으로 돌아간다
    with SessionLocal() as db:
        for r in db.scalars(__import__("sqlalchemy").select(m.ChargeRequest)):
            r.updated_at = datetime.now(timezone.utc) - timedelta(hours=25)
        db.commit()
    assert hs()["vehicles"][0]["home_state"] == "NO_REQUEST"


def test_last_session_summary_shows_only_without_active_request():
    vid = vehicle(); assign(vid)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    client.post("/charge-requests", headers=UH, json=body(vid))
    assert client.post("/dev/simulate?step_s=0&wait=true", headers=UH).status_code == 200
    v = hs()["vehicles"][0]
    assert v["last_session"]["energy_kwh"] > 0 and v["last_session"]["cost_won"] == v["charge"]["cost_won"]
    client.post("/charge-requests", headers=UH, json=body(vid))
    assert hs()["vehicles"][0]["last_session"] is None  # 새 요청이 있으면 숨김


def test_auto_assign_on_register(monkeypatch):
    import dataclasses

    import config

    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, auto_assign_ros_ids=("EV-01", "EV-02")))
    mk = lambda plate: client.post("/vehicles", headers=UH, json=dict(plate_no=plate, battery_kwh=60, max_charge_kw=11)).json()
    a, b, c = mk("11가1111"), mk("22가2222"), mk("33가3333")
    assert a["assigned"] and b["assigned"] and not c["assigned"]  # ID 두 개뿐이라 세 번째는 배정 대기
    ids = {v.plate_no: v.ros_vehicle_id for v in db_rows(m.Vehicle)}
    assert ids == {"11가1111": "EV-01", "22가2222": "EV-02", "33가3333": None}
    assert client.delete(f"/vehicles/{a['id']}", headers=UH).status_code == 200  # 삭제하면 ID가 풀린다
    st = client.get("/me/status", headers=UH).json()["vehicles"]
    assert [v["assigned"] for v in st] == [True, True] and {v.ros_vehicle_id for v in db_rows(m.Vehicle) if v.deleted_at is None} == {"EV-01", "EV-02"}


def test_parking_area_selection():
    vid = vehicle(); assign(vid)
    client.post("/consents", headers=UH, json=dict(version="v1"))
    assert client.post("/charge-requests", headers=UH, json=body(vid, parking_area="D")).status_code == 422  # A·B·C만
    r = client.post("/charge-requests", headers=UH, json=body(vid, parking_area="B"))
    assert r.status_code == 201 and r.json()["request"]["parking_area"] == "B"
    assert ros.last("/charging/request")["parking_area"] == "B"
    mine = {a["area_id"]: a for a in client.get("/parking-zones/areas", headers=UH).json()["areas"]}
    assert mine["B"]["has_mine"] is True and mine["B"]["free_count"] == 26  # 내 화면에서는 내 요청을 빼지 않는다
    other = uuid.uuid4(); oh = H(other, "user")
    theirs = {a["area_id"]: a for a in client.get("/parking-zones/areas", headers=oh).json()["areas"]}
    assert theirs["B"]["free_count"] == 25 and not theirs["B"]["has_mine"]  # 남의 요청이 한 자리를 잡는다
    rid = r.json()["request"]["id"]
    p = client.patch(f"/charge-requests/{rid}", headers=UH, json=dict(parking_area="C"))
    assert p.status_code == 200 and p.json()["request"]["parking_area"] == "C" and ros.last("/charging/request")["parking_area"] == "C"
    with SessionLocal() as db:  # A구역을 가득 채우면 그 구역은 고를 수 없다
        for n in sum(AREA_ROWS["A"], []):
            db.get(m.ParkingZone, seat_zone_id(n)).capacity = 0
        db.commit()
    full = client.patch(f"/charge-requests/{rid}", headers=UH, json=dict(parking_area="A"))
    assert full.status_code == 409 and full.json()["code"] == "PARKING_ZONE_UNAVAILABLE"
