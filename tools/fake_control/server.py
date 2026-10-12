"""가짜 관제(개발·시연용). 진짜 관제 게이트웨이처럼 서버 /ws/gateway 에 붙어 앱 요청을 받고, 웹 화면의 버튼으로 단계를 진행한다.

ROS(차량 주행·AVM·인식)는 생략하고 관제 상태를 직접 만든다. 상태는 관제 게이트웨이의 contract.outbound_status()를
그대로 거쳐 보내므로 서버가 받는 모양은 진짜 관제와 같다(관제 복사본 macaron8_AIOT-main 필요).
진짜 관제와 동시에 붙이지 말 것(서버는 게이트웨이 하나만 쓴다).

실행: backend/.venv/bin/python tools/fake_control/server.py [--backend WS_URL] [--token TOKEN] [--port 8090]
  기본 서버: ws://127.0.0.1:8000/ws/gateway, 토큰: --token > AIOT_WS_TOKEN > backend/.env 의 GATEWAY_TOKEN
  화면: http://127.0.0.1:8090
  --wait-slot 10: 충전기가 사용 중일 때 임시 대기 칸(시연용, 기본 10번. 막혀 있으면 B→A 첫 빈칸)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
import websockets
import yaml
from fastapi import Body, FastAPI
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parents[2]
CONTROL = ROOT / "macaron8_AIOT-main/src/aiot_central_control"
if not CONTROL.exists():
    raise SystemExit(f"관제 복사본이 없어요: {CONTROL}")
sys.path.insert(0, str(CONTROL / "gateway"))
from contract import outbound_status  # noqa: E402  관제 게이트웨이 변환 그대로

MAP = json.loads((CONTROL / "config/slots_final_ros.json").read_text(encoding="utf-8"))
_ZCFG = yaml.safe_load((CONTROL / "config/parking_zones.yaml").read_text(encoding="utf-8"))
_FLEET = yaml.safe_load((CONTROL / "config/fleet_locations.yaml").read_text(encoding="utf-8"))["/**"]["ros__parameters"]
ZONES: dict[str, list[int]] = {k: list(v) for k, v in _ZCFG["parking_zone_slots"].items()}
FALLBACK: dict[str, list[str]] = _ZCFG.get("zone_fallback", {})
WAIT_PRI: list[str] = _ZCFG.get("waiting_zone_priority", ["B", "A"])
CANCEL_PRI: list[str] = _ZCFG.get("exit_zone_priority", ["A", "B", "C"])
CHARGER = int(_FLEET["charger_01_slot_id"])
CENTER = {s["id"]: (sum(p[0] for p in s["corners"]) / 4, sum(p[1] for p in s["corners"]) / 4) for s in MAP["slots"]}
AREA_OF = {n: a for a, ns in ZONES.items() for n in ns}
TERMINAL = ("COMPLETED", "CANCELED", "FAILED")


class State:
    def __init__(self):
        self.vehicles: dict[str, dict] = {}
        self.requests: dict[str, dict] = {}
        self.blocked: set[int] = set()
        self.log: deque = deque(maxlen=150)
        self.ws = None
        self.connected = False
        self.paused = False  # 관제 전체 신호 끊기
        self.travel_s = 4.0
        self.charge_rate = 2.0  # %/초
        for i, key in enumerate(("ev01", "ev02", "ev03"), 1):
            self.add_vehicle(f"EV-0{i}", int(_FLEET[f"{key}_parking_slot_id"]), (35.0, 50.0, 20.0)[i - 1])

    def add_vehicle(self, vid, slot, soc=40.0):
        self.vehicles[vid] = dict(id=vid, slot=slot, soc=soc, drive=None, estop=False, online=True, auto=False,
                                  exit=None, task_id=None, auto_at=0.0)

    def note(self, kind, text):
        self.log.appendleft(dict(t=time.time(), kind=kind, text=text))


S = State()
ARGS = argparse.Namespace()


# ---------------- 차량·칸 ----------------
def loc(slot):
    return None if slot is None else ("CHARGER_01" if slot == CHARGER else f"PARKING_{slot}")


def xy(v):
    d = v["drive"]
    if not d:
        return CENTER[v["slot"]]
    k = min(1.0, max(0.0, (time.time() - d["depart"]) / max(0.01, d["arrive"] - d["depart"])))
    (x0, y0), (x1, y1) = d["from"], CENTER[d["to"]]
    return x0 + (x1 - x0) * k, y0 + (y1 - y0) * k


def taken(except_vid=None) -> set[int]:
    out = set(S.blocked) | {CHARGER}
    for v in S.vehicles.values():
        if v["id"] == except_vid:  # 자기 목적지는 비어 있는 것으로 보되, 지금 선 칸은 고르지 않는다(이동이 보이게)
            if v["slot"] is not None:
                out.add(v["slot"])
            continue
        if v["slot"] is not None:
            out.add(v["slot"])
        if v["drive"]:
            out.add(v["drive"]["to"])
    return out


def pick(zones: list[str], vid, fallback=True) -> int | None:
    order = []
    for z in zones:
        for zz in [z] + (FALLBACK.get(z, []) if fallback else []):
            if zz not in order:
                order.append(zz)
    busy = taken(vid)
    for z in order:
        for n in ZONES.get(z, []):
            if n in CENTER and n not in busy:
                return n
    return None


def active(vid):
    rs = [r for r in S.requests.values() if r["vehicle_id"] == vid and r["status"] not in TERMINAL]
    return rs[-1] if rs else None


def charger_user(except_vid=None):
    """충전기를 쓰는(가는 중·충전 중·아직 안 비운) 차량. 충전기 칸을 막아 두면 외부 차량이 점유한 것으로 본다."""
    if CHARGER in S.blocked:
        return "외부 차량"
    for v in S.vehicles.values():
        if v["id"] == except_vid:
            continue
        if v["slot"] == CHARGER or (v["drive"] and v["drive"]["to"] == CHARGER):
            return v["id"]
        r = active(v["id"])
        if r and r["status"] in ("DISPATCHED", "CHARGING") and not r["charger_released"]:
            return v["id"]
    return None


def drive(v, slot, purpose, task_id):
    v["drive"] = dict(**{"from": xy(v)}, to=slot, depart=time.time(), arrive=time.time() + S.travel_s, purpose=purpose)
    v["slot"], v["task_id"] = None, task_id


def arrive(v):
    d = v["drive"]
    v["slot"], v["drive"] = d["to"], None
    r, p = active(v["id"]), d["purpose"]
    if p == "WAIT" and r:
        r["parking_arrived"] = True
    elif p == "FINAL" and r:
        r.update(status="COMPLETED", parking_arrived=True, charger_released=True)
        S.note("info", f"{v['id']} 주차 완료 → 요청 완료")
    elif p == "CANCEL" and r:
        r.update(status="CANCELED", parking_arrived=True, charger_released=True)
        S.note("info", f"{v['id']} 취소 칸 도착 → 요청 취소 완료")
    elif p == "EXIT":
        v["exit"]["arrived"] = True
        if r:
            r.update(status="CANCELED", charger_released=True)
        S.note("info", f"{v['id']} 출차 칸 도착 → 출차 완료")
    if p in ("WAIT", "FINAL", "CANCEL", "EXIT"):
        v["task_id"] = None


# ---------------- 관제 상태(진짜 관제 central_status 모양) ----------------
def raw_status() -> dict:
    vehicles = []
    for v in S.vehicles.values():
        if not v["online"]:
            continue  # 신호 끊김: 상태를 안 보낸다 → 서버는 5초 뒤 오프라인
        x, y = xy(v)
        snap = dict(vehicle_id=v["id"], frame_id=MAP["frame_id"], x=x, y=y, yaw=0.0, speed=1.0 if v["drive"] else 0.0,
                    soc=round(v["soc"], 1), state="DRIVING" if v["drive"] else "PARKED", ready=not v["drive"],
                    control_mode="AUTO", estop=v["estop"], error_code=None, task_id=v["task_id"], location_id=loc(v["slot"]))
        ex = v["exit"]
        if ex and not ex.get("pending"):
            snap.update(state="EXITED" if ex["arrived"] else "EXITING", parking_purpose="EXIT", assigned_parking_zone="C",
                        assigned_parking_slot=f"PARKING_{ex['slot']}", parking_arrived=ex["arrived"])
        vehicles.append(snap)
    user = charger_user()
    at = next((v["id"] for v in S.vehicles.values() if v["slot"] == CHARGER), None)
    outside = CHARGER in S.blocked
    chargers = [dict(charger_id="CHARGER_01", state="OCCUPIED" if at or outside else "RESERVED" if user else "AVAILABLE",
                     vehicle_id=None if outside else at or user, power_kw=7.0, ready_to_charge=not user, aligned=None, error_code=None)]
    reqs = [{k: val for k, val in r.items() if not k.startswith("_")} for r in S.requests.values()]
    return dict(timestamp=time.time(), vehicles=vehicles, chargers=chargers, requests=reqs, access=[], events=[], errors=[])


async def send(env: dict, label: str | None = None):
    if S.ws is None:
        S.note("warn", f"서버 미연결이라 못 보냄: {label or env['type']}")
        return
    await S.ws.send(json.dumps(env, ensure_ascii=False))
    if label:
        S.note("out", label)


def result_ok(r, op):
    return dict(request_id=r["request_id"], operation=op, accepted=True, status=r["status"],
                attention_reasons=r["attention_reasons"], error_code=None)


def result_err(http, message, rid=None, vid=None):
    return dict(accepted=False, http_status=http, request_id=rid, vehicle_id=vid,
                error=json.dumps({"detail": {"error_code": "REQUEST_CONFLICT" if http == 409 else "REQUEST_NOT_FOUND", "message": message}}))


# ---------------- 서버에서 온 메시지 ----------------
async def on_message(item: dict):
    kind, p = item.get("type"), item.get("payload") or {}
    if kind == "charging_request":
        rid, vid = p.get("request_id"), p.get("vehicle_id")
        S.note("in", f"충전 요청 {vid} 목표 {p.get('target_soc')}% 구역 {p.get('parking_zone_id') or '자동'} ({str(rid)[:8]})")
        if vid not in S.vehicles:
            S.add_vehicle(vid, pick(["B"], vid) or 0)
            S.note("info", f"처음 보는 차량 {vid} 추가")
        v = S.vehicles[vid]
        if v["exit"] and not v["exit"].get("pending"):
            await send(dict(type="request_result", request_id=rid, payload=result_err(409, "VEHICLE_EXITING_OR_EXITED_REQUIRES_ENTER", rid, vid)),
                       f"충전 요청 거절(출차 차량, 재입차 필요) {vid}")
            return
        r = S.requests.get(rid)
        op = "UPDATE" if r else "CREATE"
        if r is None:
            r = S.requests[rid] = dict(request_id=rid, vehicle_id=vid, status="ACTIVE", attention_reasons=[], hold_reasons=[],
                                       cancel_requested=False, task_id=None, return_task_id=None, charger_released=False,
                                       parking_arrived=False, parking_purpose=None, assigned_parking_zone=None, assigned_parking_slot=None)
        r.update(target_soc=float(p.get("target_soc") or 80), required_soc_at_departure=float(p.get("min_soc") or 0),
                 preferred_parking_zone=p.get("parking_zone_id"))
        await send(dict(type="request_result", request_id=rid, payload=result_ok(r, op)), f"요청 {'수정' if op == 'UPDATE' else '접수'} 응답 {vid}")
    elif kind == "charging_cancel":
        rid = p.get("request_id")
        r = S.requests.get(rid)
        S.note("in", f"취소 요청 {p.get('vehicle_id')} ({str(rid)[:8]})")
        if r is None:
            await send(dict(type="request_result", request_id=rid, payload=result_err(404, "unknown request", rid)), "취소 응답: 모르는 요청(404)")
            return
        if r["status"] not in TERMINAL:
            r["cancel_requested"] = True
            v = S.vehicles[r["vehicle_id"]]
            if r["status"] == "ACTIVE" and not r["return_task_id"] and not v["drive"]:  # 출발 전: 제자리에서 바로 취소
                r["status"] = "CANCELED"
                S.note("info", f"{v['id']} 출발 전 취소 → 바로 취소 완료")
        await send(dict(type="request_result", request_id=rid, payload=result_ok(r, "CANCEL")), "취소 접수 응답")
    elif kind == "vehicle_exit":
        vid = p.get("vehicle_id")
        S.note("in", f"출차 요청 {vid} — 화면에서 수락/거절을 눌러 주세요")
        v = S.vehicles.get(vid)
        if v is None:
            await send(dict(type="request_result", vehicle_id=vid, payload=result_err(404, f"unknown vehicle: {vid}", None, vid)), "출차 거절(모르는 차량)")
        elif v["exit"] and not v["exit"].get("pending"):  # 이미 출차 중: 같은 작업으로 응답
            await exit_ok(v)
        else:
            v["exit"] = dict(pending=True)
    else:
        S.note("warn", f"모르는 메시지: {kind}")


async def exit_ok(v):
    ex = v["exit"]
    await send(dict(type="request_result", vehicle_id=v["id"], payload=dict(
        vehicle_id=v["id"], task_id=ex["task_id"], assigned_parking_zone="C", assigned_parking_slot=f"PARKING_{ex['slot']}",
        operation="EXIT", status="EXITED" if ex["arrived"] else "EXITING", accepted=True)), f"출차 수락 {v['id']} → PARKING_{ex['slot']}")


# ---------------- 버튼 ----------------
def actions(v) -> list[dict]:
    """지금 누를 수 있는 단계 버튼. enabled=False면 이유(why)를 보여 준다."""
    out, r, vid = [], active(v["id"]), v["id"]

    def add(a, label, ok=True, why=None, kind="step"):
        out.append(dict(action=a, label=label, enabled=bool(ok), why=None if ok else why, kind=kind))

    ex = v["exit"]
    if ex and ex.get("pending"):
        c = pick(["C"], vid, fallback=False)
        add("exit_accept", "출차 수락 (C구역으로)", c is not None, "C구역 빈칸 없음")
        add("exit_reject", "출차 거절 (C구역 만차)", kind="danger")
        return out
    if ex:
        if ex["arrived"]:
            add("enter", "재입차 (ENTER)")
        return out
    if r is None or v["drive"] and not r["cancel_requested"]:
        return out
    if r["cancel_requested"]:
        moving_cancel = v["drive"] and v["drive"]["purpose"] == "CANCEL"
        if not moving_cancel:
            add("cancel_move", "취소 처리: 취소 칸으로 이동", pick(CANCEL_PRI, vid) is not None, "빈칸 없음")
        return out
    st, user = r["status"], charger_user(vid)
    if st == "ACTIVE":
        add("to_charger", "충전소로 출발", user is None, f"충전기 사용 중({user})")
        if r["parking_purpose"] != "WAIT":
            w = wait_slot(vid)
            add("to_wait", f"대기 칸으로 (충전기 사용 중) → {w}번" if w is not None else "대기 칸으로 (충전기 사용 중)", w is not None, "빈칸 없음")
        add("reject", "요청 거절 (FAILED)", kind="danger")
    elif st == "DISPATCHED":
        add("start_charging", "충전 시작 (차량 인식·점유 확인)", v["slot"] == CHARGER)
    elif st == "CHARGING":
        done = v["soc"] >= r["target_soc"]
        if not done:
            add("finish_charging", f"목표 SOC({r['target_soc']:.0f}%) 바로 채우기")
        if not r["return_task_id"]:
            add("to_parking", f"주차 칸으로 출발 ({r['preferred_parking_zone'] or '자동'}구역)", done and pick(_pref(r), vid) is not None,
                "충전 중" if not done else "빈칸 없음")
    return out


def wait_slot(vid) -> int | None:
    """충전기가 사용 중일 때 임시 대기 칸. 시연용으로 정한 칸(--wait-slot, 기본 10번)이 비어 있으면 그 칸, 아니면 관제 규칙(B→A 첫 빈칸)."""
    if ARGS.wait_slot in CENTER and ARGS.wait_slot not in taken(vid):
        return ARGS.wait_slot
    return pick(WAIT_PRI, vid)


def _pref(r):
    z = r.get("preferred_parking_zone")
    return [z] if z in ZONES else ["A", "B", "C"]


async def do(vid: str, a: str, value=None):
    v = S.vehicles[vid]
    r = active(vid)
    tid = lambda p: f"{p}_{vid}_{uuid.uuid4().hex[:6]}"  # noqa: E731
    if a == "to_charger":
        r.update(status="DISPATCHED", task_id=tid("TASK"), return_task_id=None, parking_purpose=None, parking_arrived=False,
                 assigned_parking_zone=None, assigned_parking_slot=None)
        drive(v, CHARGER, "CHARGER", r["task_id"])
    elif a == "to_wait":
        n = wait_slot(vid)
        r.update(parking_purpose="WAIT", assigned_parking_zone=AREA_OF.get(n), assigned_parking_slot=f"PARKING_{n}",
                 return_task_id=tid("WAIT"), parking_arrived=False)
        drive(v, n, "WAIT", r["return_task_id"])
    elif a == "start_charging":
        r["status"] = "CHARGING"
    elif a == "finish_charging":
        v["soc"] = max(v["soc"], r["target_soc"])
    elif a == "to_parking":
        n = pick(_pref(r), vid)
        r.update(parking_purpose="FINAL", assigned_parking_zone=AREA_OF.get(n), assigned_parking_slot=f"PARKING_{n}",
                 return_task_id=tid("RETURN"), parking_arrived=False)
        drive(v, n, "FINAL", r["return_task_id"])
    elif a == "cancel_move":
        n = pick(CANCEL_PRI, vid)
        r.update(parking_purpose="EXIT", assigned_parking_zone=AREA_OF.get(n), assigned_parking_slot=f"PARKING_{n}",
                 return_task_id=tid("EXIT"), parking_arrived=False)
        drive(v, n, "CANCEL", r["return_task_id"])
    elif a == "reject":
        r.update(status="FAILED", attention_reasons=["REJECTED_BY_OPERATOR"])
    elif a == "exit_accept":
        n = pick(["C"], vid, fallback=False)
        v["exit"] = dict(slot=n, task_id=tid("EXIT"), arrived=False)
        drive(v, n, "EXIT", v["exit"]["task_id"])
        await exit_ok(v)
    elif a == "exit_reject":
        v["exit"] = None
        await send(dict(type="request_result", vehicle_id=vid, payload=result_err(409, "NO_EXIT_PARKING_AVAILABLE_IN_C", None, vid)),
                   f"출차 거절 {vid} (C구역 만차)")
    elif a == "enter":
        v["exit"] = None
        S.note("info", f"{vid} 재입차")
    elif a == "fault":
        v["estop"] = not v["estop"]
    elif a == "offline":
        v["online"] = not v["online"]
    elif a == "auto":
        v["auto"] = not v["auto"]
    elif a == "soc":
        v["soc"] = max(0.0, min(100.0, float(value)))
    else:
        raise ValueError(a)
    if a in ("to_charger", "to_wait", "start_charging", "finish_charging", "to_parking", "cancel_move", "reject",
             "exit_accept", "fault", "offline", "enter"):
        S.note("act", f"{vid}: {a}")


# ---------------- 반복 작업 ----------------
async def tick_loop():
    last = time.time()
    while True:
        await asyncio.sleep(0.2)
        now, dt = time.time(), time.time() - last
        last = now
        for v in S.vehicles.values():
            if v["drive"] and now >= v["drive"]["arrive"]:
                arrive(v)
            r = active(v["id"])
            if r and r["status"] == "CHARGING" and v["slot"] == CHARGER and not r["cancel_requested"] and v["soc"] < r["target_soc"]:
                v["soc"] = min(r["target_soc"], v["soc"] + S.charge_rate * dt)
            if v["auto"] and not v["drive"] and now >= v["auto_at"]:
                step = next((x for x in actions(v) if x["enabled"] and x["kind"] == "step"), None)
                if step and step["action"] not in ("finish_charging", "enter"):
                    await do(v["id"], step["action"])
                    v["auto_at"] = now + 1.0


async def status_loop(ws):
    while True:
        if not S.paused:
            await ws.send(json.dumps({"type": "central_status", "payload": outbound_status(raw_status())}, ensure_ascii=False))
        await asyncio.sleep(1.0)


async def gateway_loop():
    headers = {"Authorization": f"Bearer {ARGS.token}"} if ARGS.token else {}
    while True:
        try:
            async with websockets.connect(ARGS.backend, additional_headers=headers, open_timeout=10) as ws:
                S.ws, S.connected = ws, True
                S.note("info", f"서버 연결됨: {ARGS.backend}")
                sender = asyncio.create_task(status_loop(ws))
                try:
                    async for raw in ws:
                        try:
                            await on_message(json.loads(raw))
                        except Exception as e:  # noqa: BLE001  메시지 하나 때문에 연결을 끊지 않는다
                            S.note("warn", f"메시지 처리 오류: {e}")
                finally:
                    sender.cancel()
        except websockets.ConnectionClosed as e:
            code = e.rcvd.code if e.rcvd else None
            S.note("warn", {4401: "토큰이 틀려 서버가 거절했어요(4401)",
                            4409: "다른 관제(게이트웨이)가 서버에 붙어서 끊겼어요(4409). 진짜 관제를 꺼 주세요"}.get(code, f"연결 끊김: {e}"))
        except Exception as e:  # noqa: BLE001
            S.note("warn", f"연결 실패: {type(e).__name__} {e}")
        S.ws, S.connected = None, False
        await asyncio.sleep(3)


# ---------------- 웹 화면 ----------------
@asynccontextmanager
async def lifespan(_app):
    tasks = [asyncio.create_task(gateway_loop()), asyncio.create_task(tick_loop())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index():
    return FileResponse(Path(__file__).with_name("index.html"))


@app.get("/img/{name}")
async def image(name: str):
    if name not in ("ev01_top.png", "ev02_top.png", "ev03_top.png"):  # 관제 대시보드의 차량 위에서 본 그림만
        return FileResponse(Path(__file__).with_name("index.html"), status_code=404)
    return FileResponse(ROOT / "macaron8_AIOT-main/dashboard" / name)


@app.get("/api/map")
async def get_map():
    return dict(slots=[dict(id=s["id"], corners=s["corners"], area=AREA_OF.get(s["id"]), charger=s["id"] == CHARGER) for s in MAP["slots"]])


@app.get("/api/state")
async def get_state():
    gw = {v["vehicle_id"]: v["state"] for v in outbound_status(raw_status())["vehicles"]}
    vehicles = []
    for v in S.vehicles.values():
        d = v["drive"]
        r = active(v["id"])
        last = None if r else next((x for x in reversed(list(S.requests.values())) if x["vehicle_id"] == v["id"]), None)
        vehicles.append(dict(
            id=v["id"], slot=v["slot"], location=loc(v["slot"]), soc=round(v["soc"], 1), estop=v["estop"], online=v["online"], auto=v["auto"],
            pos=xy(v), drive=dict(**{"from": d["from"]}, to=CENTER[d["to"]], to_slot=d["to"], depart=d["depart"], arrive=d["arrive"], purpose=d["purpose"]) if d else None,
            gw_state=gw.get(v["id"], "OFFLINE"), exit=v["exit"], request=r, last_request=last and dict(status=last["status"], id=last["request_id"]),
            actions=actions(v)))
    return dict(now=time.time(), connected=S.connected, charger_slot=CHARGER, backend=ARGS.backend, paused=S.paused, travel_s=S.travel_s,
                charge_rate=S.charge_rate, blocked=sorted(S.blocked), vehicles=vehicles, log=list(S.log)[:60])


@app.post("/api/action")
async def post_action(body: dict = Body(...)):
    try:
        await do(body["vehicle"], body["action"], body.get("value"))
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        S.note("warn", f"버튼 처리 실패: {e}")
        return {"ok": False, "error": str(e)}


@app.post("/api/settings")
async def post_settings(body: dict = Body(...)):
    if "block" in body:
        n = int(body["block"])
        if n == CHARGER and n not in S.blocked and charger_user():
            return {"ok": False, "error": f"충전기를 {charger_user()}이(가) 쓰는 중이라 점유로 바꿀 수 없어요"}
        S.blocked.symmetric_difference_update({n})
        if n == CHARGER:
            S.note("act", "충전기 점유(외부 차량) " + ("시작" if n in S.blocked else "해제 → 충전기 비었음"))
    if "paused" in body:
        S.paused = bool(body["paused"])
        S.note("act", "관제 신호 " + ("중지" if S.paused else "재개"))
    if "travel_s" in body:
        S.travel_s = max(0.5, float(body["travel_s"]))
    if "charge_rate" in body:
        S.charge_rate = max(0.1, float(body["charge_rate"]))
    return {"ok": True}


def main():
    p = argparse.ArgumentParser(description="가짜 관제")
    p.add_argument("--backend", default=os.getenv("AIOT_WS_URL", "ws://127.0.0.1:8000/ws/gateway"))
    p.add_argument("--token", default=os.getenv("AIOT_WS_TOKEN"))
    p.add_argument("--port", type=int, default=8090)
    p.add_argument("--wait-slot", type=int, default=10, help="충전기 사용 중일 때 임시 대기 칸 번호(시연용, 기본 10). -1이면 관제 규칙대로")
    p.parse_args(namespace=ARGS)
    if not ARGS.token:
        try:
            from dotenv import dotenv_values

            ARGS.token = dotenv_values(ROOT / "backend/.env").get("GATEWAY_TOKEN")
        except ImportError:
            pass
    print(f"가짜 관제: http://127.0.0.1:{ARGS.port}  →  {ARGS.backend}  (토큰 {'있음' if ARGS.token else '없음'})")
    uvicorn.run(app, host="127.0.0.1", port=ARGS.port, log_level="warning")


if __name__ == "__main__":
    main()
