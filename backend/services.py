from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import models as m
import repo
from config import settings
from ros_schemas.messages import CentralStatusMsg
from schemas.charge_requests import ChargeRequestOut, Feasibility, FeasibilityReason, TimeBreakdown
from schemas.common import ACTIVE_REQUEST_STATUSES, ChargeRequestStatus, ChargerState, TaskStatus, TaskType, VehicleState
from schemas.status import ChargeInfo, CurrentTask, Eta, EtaState, HomeState, LastRequest, LastSession, Pose, STATE_TO_STEP, STEP_LABELS, VehicleStatus

now = repo.now


# ---------- 가능 여부 추정 (단순 계산. 실제 스케줄러 연동 시 교체) ----------
def estimate(db: Session, vehicle: m.Vehicle, desired_finish_at: datetime, target_soc: int) -> Feasibility:
    st = db.get(m.VehicleStateRow, vehicle.id)
    soc = float(st.soc) if st else 20.0
    states = {s.charger_id: s for s in db.scalars(select(m.ChargerStateRow))}
    chargers = list(db.scalars(select(m.Charger)))
    usable = [c for c in chargers if (states.get(c.id).state if c.id in states else ChargerState.AVAILABLE) in (ChargerState.AVAILABLE, ChargerState.IN_USE) and not (states.get(c.id) and states[c.id].maintenance)]
    if not usable:
        return Feasibility(feasible=False, reason=FeasibilityReason.CHARGERS_UNAVAILABLE, message="사용 가능한 충전기가 없습니다.")
    energy = max(target_soc - soc, 0) / 100 * vehicle.battery_kwh
    charge_s = int(energy / vehicle.max_charge_kw * 3600)
    bd = TimeBreakdown(wait_s=0, move_to_charger_s=settings.move_to_charger_s, charge_s=charge_s, move_to_parking_s=settings.move_to_parking_s)
    eta = now() + timedelta(seconds=bd.wait_s + bd.move_to_charger_s + bd.charge_s + bd.move_to_parking_s)
    if eta <= desired_finish_at:
        return Feasibility(feasible=True, reason=FeasibilityReason.OK, estimated_parked_at=eta, breakdown=bd)
    return Feasibility(feasible=False, reason=FeasibilityReason.DEADLINE_TOO_EARLY, estimated_parked_at=eta, earliest_parked_at=eta, breakdown=bd, message="희망 시각까지 주차 완료가 어렵습니다.")


# ---------- 응답 조립 ----------
def zone_availability(db: Session, zone_id: str | None = None):
    """PARKING 구역별 (구역, 남은 자리). 남은 자리 = capacity - 주차 중 차량 - 이 구역을 고른 활성 요청(아직 도착 전)."""
    from schemas.common import ChargeRequestStatus as S, ParkingZoneKind, VehicleState
    q = select(m.ParkingZone).where(m.ParkingZone.kind == ParkingZoneKind.PARKING)
    if zone_id:
        q = q.where(m.ParkingZone.id == zone_id)
    active = (S.REQUESTED, S.ACCEPTED, S.SCHEDULED, S.IN_PROGRESS)
    # 구역마다 따로 세지 않고 한 번에 집계한다(원격 DB에서 구역 수 × 왕복이 되면 수십 초 걸림)
    parked = dict(db.execute(select(m.VehicleStateRow.zone_id, func.count()).where(m.VehicleStateRow.state == VehicleState.PARKED, m.VehicleStateRow.zone_id.is_not(None)).group_by(m.VehicleStateRow.zone_id)).all())
    held = dict(db.execute(select(m.ChargeRequest.parking_zone_id, func.count()).where(m.ChargeRequest.status.in_(active), m.ChargeRequest.parking_zone_id.is_not(None)).group_by(m.ChargeRequest.parking_zone_id)).all())
    return [(z, max(z.capacity - parked.get(z.id, 0) - held.get(z.id, 0), 0)) for z in db.scalars(q.order_by(m.ParkingZone.id))]


def request_out(r: m.ChargeRequest) -> ChargeRequestOut:
    return ChargeRequestOut.model_validate(r)


_WAITING = (ChargeRequestStatus.REQUESTED, ChargeRequestStatus.ACCEPTED, ChargeRequestStatus.SCHEDULED)


def queue_order(db: Session) -> list[UUID]:
    """대기 중인 요청 id를 접수 순서로. 같은 시각이면 id로 고정(DB별 시각 비교 차이를 피하려 파이썬에서 정렬)."""
    rows = list(db.scalars(select(m.ChargeRequest).where(m.ChargeRequest.status.in_(_WAITING))))
    rows.sort(key=lambda x: (x.created_at, str(x.id)))
    return [r.id for r in rows]


def notify_queue_changes(db: Session, before: list[UUID], outbox: list | None) -> None:
    """앞 순서가 줄어든 대기 요청의 주인에게 알린다(순번이 뒤로 밀리는 일은 없다: 새 요청은 항상 맨 뒤)."""
    after = queue_order(db)
    for idx, rid in enumerate(after):
        if rid in before and before.index(rid) > idx:
            r = db.get(m.ChargeRequest, rid)
            v = db.get(m.Vehicle, r.vehicle_id) if r else None
            body = "다음 차례예요." if idx == 0 else f"지금 {idx + 1}번째예요."
            notice(db, v.owner_id if v else None, "QUEUE_CHANGED", "queue_change", "대기 순번이 앞당겨졌어요", body,
                   {"request_id": str(rid), "queue_position": idx + 1}, outbox)


def _with_queue(db: Session, r: m.ChargeRequest) -> ChargeRequestOut:
    out = request_out(r)
    if r.status in (ChargeRequestStatus.REQUESTED, ChargeRequestStatus.ACCEPTED, ChargeRequestStatus.SCHEDULED):
        ahead = max(queue_order(db).index(r.id) if r.id in queue_order(db) else 0, 0)
        out.queue_position, out.estimated_wait_min = ahead + 1, ahead * settings.avg_service_min
    return out


def is_online(st: m.VehicleStateRow | None) -> bool:
    return st is not None and (now() - st.last_seen_at).total_seconds() <= settings.offline_after_s


def cost_of(energy_kwh: float, unit_price_won: int | None) -> int:
    return round(energy_kwh * (settings.unit_price_won_per_kwh if unit_price_won is None else unit_price_won))


_CHARGE_SHOWN = (VehicleState.CHARGING, VehicleState.CHARGE_DONE, VehicleState.MOVING_TO_PARKING, VehicleState.PARKED)


def charge_info(db: Session, v: m.Vehicle, st: m.VehicleStateRow | None) -> ChargeInfo | None:
    """차량의 가장 최근 충전 세션으로 충전량·금액을 만든다. 충전 전(이동 중)·미수신이면 None."""
    if st is None or st.state not in _CHARGE_SHOWN:
        return None
    sess = db.scalar(select(m.ChargeSession).join(m.ChargeRequest, m.ChargeRequest.id == m.ChargeSession.request_id)
                     .where(m.ChargeRequest.vehicle_id == v.id).order_by(m.ChargeSession.start_at.desc()))
    if sess is None:
        return None
    running = sess.end_at is None
    energy = round(max(st.soc - sess.start_soc, 0) / 100 * v.battery_kwh, 3) if running else float(sess.energy_kwh or 0)
    price = sess.unit_price_won if sess.unit_price_won is not None else settings.unit_price_won_per_kwh
    return ChargeInfo(energy_kwh=energy, cost_won=cost_of(energy, price), unit_price_won=price, in_progress=running)


_MOVING_1 = (VehicleState.ASSIGNED, VehicleState.MOVING_TO_CHARGER, VehicleState.ARRIVED_AT_CHARGER)
RESULT_TTL = timedelta(hours=24)  # 실패·취소 결과를 홈에 남겨 두는 시간
DEFAULT_FAIL_REASON = "차량 또는 충전기 문제로 중단됐어요."


def last_request(db: Session, v: m.Vehicle) -> m.ChargeRequest | None:
    """활성 요청이 없을 때, 24시간 안에 끝난 가장 최근 요청."""
    r = db.scalars(select(m.ChargeRequest).where(m.ChargeRequest.vehicle_id == v.id).order_by(m.ChargeRequest.created_at.desc(), m.ChargeRequest.updated_at.desc())).first()
    if r is None or r.status in ACTIVE_REQUEST_STATUSES or now() - r.updated_at > RESULT_TTL:
        return None
    return r


def failure_reason(db: Session, r: m.ChargeRequest) -> str:
    t = db.scalars(select(m.VehicleTask).where(m.VehicleTask.request_id == r.id, m.VehicleTask.status == TaskStatus.FAILED, m.VehicleTask.error_message.is_not(None)).order_by(m.VehicleTask.updated_at.desc())).first()
    return (t.error_message if t and t.error_message else DEFAULT_FAIL_REASON)


def home_state(v: m.Vehicle, st: m.VehicleStateRow | None, ar: m.ChargeRequest | None, lr: m.ChargeRequest | None) -> HomeState:
    """우선순위: 미배정 > 상태 없음 > 취소 처리 중 > 차량 문제 > 연결 끊김 > 진행 단계 > 직전 결과(실패·취소·완료) > 요청 없음."""
    if v.ros_vehicle_id is None:
        return HomeState.WAITING_ASSIGNMENT
    if st is None or st.state is None:
        return HomeState.NO_DATA
    if ar and ar.status == ChargeRequestStatus.CANCEL_REQUESTED:
        return HomeState.CANCELING
    if st.state == VehicleState.FAULT:
        return HomeState.FAULT
    if not is_online(st):
        return HomeState.VEHICLE_OFFLINE
    if ar:
        if st.state in _MOVING_1:
            return HomeState.MOVING_TO_CHARGER
        return {VehicleState.CHARGING: HomeState.CHARGING, VehicleState.CHARGE_DONE: HomeState.CHARGE_DONE,
                VehicleState.MOVING_TO_PARKING: HomeState.MOVING_TO_PARKING, VehicleState.PARKED: HomeState.PARKED}.get(st.state, HomeState.QUEUED)
    if lr:
        if lr.status == ChargeRequestStatus.FAILED:
            return HomeState.REQUEST_FAILED
        if lr.status == ChargeRequestStatus.CANCELLED:
            return HomeState.CANCELLED
        if lr.status == ChargeRequestStatus.COMPLETED and st.state == VehicleState.PARKED:
            return HomeState.PARKED
    return HomeState.NO_REQUEST


def eta_of(hs: HomeState, st: m.VehicleStateRow | None, db: Session | None = None, v: m.Vehicle | None = None,
           ar: m.ChargeRequest | None = None) -> Eta:
    """관제가 보낸 예상 완료 시각이 있으면 그것(KNOWN). 없으면 서버가 대략 계산(KNOWN, approx), 그것도 못 하면 '계산 중'.
    진행 중이 아니면 '—'."""
    if hs in (HomeState.QUEUED, HomeState.MOVING_TO_CHARGER, HomeState.CHARGING, HomeState.CHARGE_DONE, HomeState.MOVING_TO_PARKING):
        if st is not None and st.estimated_completion is not None:
            return Eta(state=EtaState.KNOWN, at=st.estimated_completion)
        at = _estimate_parked_at(db, hs, st, v, ar) if db is not None and v is not None and ar is not None else None
        if at is not None:
            return Eta(state=EtaState.KNOWN, at=at, approx=True)
        return Eta(state=EtaState.CALCULATING)
    return Eta(state=EtaState.NONE)


def _estimate_parked_at(db: Session, hs: HomeState, st: m.VehicleStateRow | None, v: m.Vehicle, ar: m.ChargeRequest) -> datetime | None:
    """관제가 예상 시각을 안 줄 때의 대략 계산. 단계마다 이미 끝난 부분은 뺀다.
    예상 주차 완료 = 지금 + (대기) + (충전기까지 이동) + 남은 충전 + 주차구역 이동.
    배터리 %를 모르면(관제 정보 없음) 계산하지 않는다."""
    if st is None or st.soc is None:
        return None
    power = float(v.max_charge_kw)
    cs = db.get(m.ChargerStateRow, st.charger_id) if st.charger_id else None
    if cs is not None and cs.output_kw:  # 실제 충전기 출력이 더 낮으면 그 값으로
        power = min(power, float(cs.output_kw))
    charge_s = max(ar.target_soc - float(st.soc), 0) / 100 * float(v.battery_kwh) / power * 3600 if power > 0 else 0
    move_c, move_p = settings.move_to_charger_s, settings.move_to_parking_s
    if hs == HomeState.QUEUED:
        wait_s = _with_queue(db, ar).estimated_wait_min or 0
        secs = wait_s * 60 + move_c + charge_s + move_p
    elif hs == HomeState.MOVING_TO_CHARGER:
        secs = move_c * (1 - (st.progress or 0)) + charge_s + move_p
    elif hs == HomeState.CHARGING:
        secs = charge_s + move_p
    elif hs == HomeState.CHARGE_DONE:
        secs = move_p
    else:  # MOVING_TO_PARKING
        secs = move_p * (1 - (st.progress or 0))
    return now() + timedelta(seconds=int(secs))


def last_session(db: Session, v: m.Vehicle) -> LastSession | None:
    sess = db.scalar(select(m.ChargeSession).join(m.ChargeRequest, m.ChargeRequest.id == m.ChargeSession.request_id)
                     .where(m.ChargeRequest.vehicle_id == v.id, m.ChargeSession.end_at.is_not(None)).order_by(m.ChargeSession.end_at.desc()))
    if sess is None:
        return None
    e = float(sess.energy_kwh or 0)
    return LastSession(ended_at=sess.end_at, energy_kwh=e, cost_won=cost_of(e, sess.unit_price_won), end_soc=sess.end_soc)


def vehicle_status(db: Session, v: m.Vehicle) -> VehicleStatus:
    st = db.get(m.VehicleStateRow, v.id)
    state = st.state if st else None
    step = STATE_TO_STEP.get(state) if state else None
    ar = repo.active_request(db, v.id)
    task = None
    if st and st.current_task_id:
        t = db.get(m.VehicleTask, st.current_task_id)
        if t:
            task = CurrentTask(id=t.id, type=t.type, status=t.status, progress=t.progress)
    lr = None if ar else last_request(db, v)
    hs = home_state(v, st, ar, lr)
    return VehicleStatus(
        home_state=hs, eta=eta_of(hs, st, db, v, ar),
        last_request=LastRequest(id=lr.id, status=lr.status, ended_at=lr.updated_at, failure_reason=failure_reason(db, lr) if lr.status == ChargeRequestStatus.FAILED else None) if lr else None,
        last_session=last_session(db, v) if ar is None else None,
        vehicle_id=v.id, plate_no=v.plate_no, assigned=v.ros_vehicle_id is not None,
        state=state, online=is_online(st), step=step, step_label=STEP_LABELS.get(step) if step else None,
        soc=st.soc if st else None, zone_id=st.zone_id if st else None,
        pose=Pose(x=st.pose_x, y=st.pose_y, yaw=st.pose_yaw) if st and st.pose_x is not None and st.pose_y is not None and st.pose_yaw is not None else None, charger_id=st.charger_id if st else None,
        progress=st.progress if st else None, current_task=task, estimated_completion=st.estimated_completion if st else None,
        active_request=_with_queue(db, ar) if ar else None, charge=charge_info(db, v, st), last_seen_at=st.last_seen_at if st else None, updated_at=st.updated_at if st else None)


# ---------- WebSocket 허브 ----------
class Hub:
    def __init__(self):
        self.clients: list[tuple[object, UUID, str]] = []  # (ws, user_id, role)
        self.loop = None

    async def send_vehicle(self, owner_id: UUID | None, payload: dict):
        for ws, uid, role in list(self.clients):
            if role == "admin" or (owner_id is not None and uid == owner_id):
                try:
                    await ws.send_json(payload)
                except Exception:
                    self.clients = [c for c in self.clients if c[0] is not ws]


# ---------- 상태 전이 → 충전 세션·알림 ----------
# (알림 종류, 설정 키, 제목, 본문)
_NOTICE = {
    VehicleState.CHARGE_DONE: ("CHARGE_DONE", "charge_done", "충전이 끝났어요", "곧 주차 구역으로 이동해요."),
    VehicleState.PARKED: ("PARKED", "parked", "주차가 끝났어요", "차량이 주차 구역에 도착했어요."),
    VehicleState.FAULT: ("FAULT", "fault", "차량에 문제가 생겼어요", "관리자가 확인하고 있어요."),
}


def notice(db: Session, user_id: UUID | None, ntype: str, pref: str, title: str, body: str, data: dict, outbox: list | None) -> None:
    """알림함에 저장하고(항상), 설정이 켜져 있으면 푸시 대상으로 outbox에 넣는다."""
    if user_id is None:
        return
    n = m.Notification(user_id=user_id, type=ntype, title=title, body=body, data=data)
    db.add(n)
    if outbox is not None:
        p = db.get(m.Profile, user_id)
        on = {"charge_done": True, "parked": True, "fault": True, "queue_change": False, **((p.notification_prefs if p else None) or {})}.get(pref, True)
        outbox.append((n, on))


def _on_transition(db: Session, v: m.Vehicle, st: m.VehicleStateRow, prev, outbox: list | None) -> None:
    ar = repo.active_request(db, v.id)
    # 충전 세션: CHARGING 진입 시 열고, 벗어나면 닫는다
    if st.state == VehicleState.CHARGING and st.charger_id and ar:
        db.add(m.ChargeSession(request_id=ar.id, charger_id=st.charger_id, start_at=now(), start_soc=st.soc, unit_price_won=settings.unit_price_won_per_kwh))
    elif prev == VehicleState.CHARGING:
        sess = db.scalar(select(m.ChargeSession).where(m.ChargeSession.end_at.is_(None), m.ChargeSession.request_id == (ar.id if ar else None)).order_by(m.ChargeSession.start_at.desc()))
        if sess:
            sess.end_at, sess.end_soc = now(), st.soc
            sess.energy_kwh = round(max(st.soc - sess.start_soc, 0) / 100 * v.battery_kwh, 3)
    if st.state in _NOTICE:
        ntype, pref, title, body = _NOTICE[st.state]
        if st.state == VehicleState.PARKED and st.zone_id:
            from schemas.parking_map import seat_no_of
            seat_no = seat_no_of(st.zone_id)  # PARKING_00 → 0번(앞의 0을 지우면 안 된다)
            if seat_no is not None:
                body = f"{seat_no}번 자리에 도착했어요."
        notice(db, v.owner_id, ntype, pref, title, body, {"vehicle_id": str(v.id), "request_id": str(ar.id) if ar else None}, outbox)


# ---------- /central_status 반영 ----------
def _uuid(s: str | None) -> UUID | None:
    return UUID(s) if s else None


# 진행 단계 → 그 단계를 대표하는 차량 상태(뒤로 가는 신호를 무시할 때 유지할 상태)
_STEP_STATE = {1: VehicleState.MOVING_TO_CHARGER, 2: VehicleState.CHARGING, 3: VehicleState.CHARGE_DONE,
               4: VehicleState.MOVING_TO_PARKING, 5: VehicleState.PARKED}


def _no_backward(db: Session, v: m.Vehicle, state: VehicleState, finished: set[str]) -> VehicleState:
    """진행 중인 요청은 이미 지난 단계로 돌아가지 않는다(관제 차량 신호가 이동 중↔서 있음으로 흔들릴 때).

    요청마다 도달한 가장 높은 단계(progress_step)를 기억하고, 그보다 낮은 상태가 오면 그 단계의 상태를 유지한다.
    차량 이상(FAULT)은 그대로 보여 준다. 취소·새 요청은 요청 상태나 새 행(0단계)으로 따로 처리된다.
    """
    ar = repo.active_request(db, v.id)
    if ar is None or str(ar.id) in finished:  # 같은 메시지에서 요청이 끝났다고 왔으면 그대로(예: COMPLETED + PARKED)
        return state
    if state == VehicleState.FAULT or ar.status == ChargeRequestStatus.CANCEL_REQUESTED:
        return state  # 취소 중에는 관제가 차를 옮기는 실제 상태를 그대로 보여 준다
    if state == VehicleState.PARKED and ar.progress_step < 4:
        # 주차구역 이동(4단계) 전의 PARKED는 '주차 완료'가 아니라 그냥 서 있는 것: 대기 중이면 대기, 진행 중이면 현재 단계 유지
        return _STEP_STATE[ar.progress_step] if ar.progress_step else VehicleState.WAITING
    step = STATE_TO_STEP.get(state, 0)
    if step < ar.progress_step:
        return _STEP_STATE[ar.progress_step]
    if step > ar.progress_step:
        ar.progress_step = step
    return state


def apply_central_status(db: Session, msg: CentralStatusMsg, runtime, outbox: list | None = None) -> set[UUID]:
    """중앙관제 상태를 DB에 반영하고 변경된 차량 id 집합을 돌려준다(WS 방송용). 호출자가 commit한다.

    outbox를 넘기면 상태 전이로 만든 알림(DB에 저장된 Notification 목록)을 담아 준다(푸시·WS 전송용).
    """
    changed: set[UUID] = set()
    queue_before = queue_order(db)
    runtime.last_central_at = now()
    runtime.queue_length = msg.scheduler.queue_length
    repo.set_setting(db, "emergency_stop", {"active": msg.emergency_stop_active})
    ros_to_v = {v.ros_vehicle_id: v for v in repo.live_vehicles(db) if v.ros_vehicle_id}
    chargers = {c.id for c in db.scalars(select(m.Charger))}
    zones = {z.id for z in db.scalars(select(m.ParkingZone))}

    for it in msg.tasks:  # 작업이 먼저(차량 상태가 current_task_id로 참조)
        v = ros_to_v.get(it.vehicle_id)
        if not v:
            continue
        tid = UUID(it.task_id)
        t = db.get(m.VehicleTask, tid)
        rid = _uuid(it.request_id)
        if rid and not db.get(m.ChargeRequest, rid):
            rid = None
        if t is None:
            t = m.VehicleTask(id=tid, vehicle_id=v.id, request_id=rid, type=it.type, target_id=it.target_id, target_pose_x=it.target_pose.x, target_pose_y=it.target_pose.y, target_pose_yaw=it.target_pose.yaw, status=it.status)
            db.add(t)
        if t.status != it.status or t.progress is None:
            t.status = it.status
            if it.status == TaskStatus.ACCEPTED and not t.accepted_at:
                t.accepted_at = now()
            if it.status == TaskStatus.RUNNING and not t.started_at:
                t.started_at = now()
            if it.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                t.completed_at = now()
        t.progress = it.progress if it.progress is not None else (t.progress or 0)
        t.error_message, t.updated_at = it.error_message, now()
        changed.add(v.id)
    db.flush()

    finished = {it.request_id for it in msg.requests if it.status not in ACTIVE_REQUEST_STATUSES}
    for it in msg.vehicles:
        v = ros_to_v.get(it.vehicle_id)
        if not v:
            continue  # 배정되지 않은 ROS 차량은 무시
        st = db.get(m.VehicleStateRow, v.id) or m.VehicleStateRow(vehicle_id=v.id)
        prev = st.state if st.state is not None else None
        tid = _uuid(it.current_task_id)
        state = _no_backward(db, v, it.state, finished)
        st.state, st.soc = state, round(it.soc)
        st.zone_id = it.zone_id if it.zone_id in zones else None
        st.pose_x, st.pose_y, st.pose_yaw = (it.pose.x, it.pose.y, it.pose.yaw) if it.pose else (None, None, None)
        st.progress, st.estimated_completion = it.progress, it.estimated_completion
        st.charger_id = it.charger_id if it.charger_id in chargers else None
        st.current_task_id = tid if tid and db.get(m.VehicleTask, tid) else None
        st.last_seen_at, st.updated_at = it.last_seen_at or now(), now()
        db.merge(st)
        changed.add(v.id)
        if prev != state:
            _on_transition(db, v, st, prev, outbox)

    for it in msg.chargers:
        if it.charger_id not in chargers:
            continue
        row = db.get(m.ChargerStateRow, it.charger_id) or m.ChargerStateRow(charger_id=it.charger_id, maintenance=False)
        av = ros_to_v.get(it.vehicle_id) if it.vehicle_id else None
        row.state, row.output_kw, row.assigned_vehicle_id = it.state, it.power_kw, av.id if av else None
        row.last_seen_at, row.updated_at = now(), now()
        db.merge(row)

    for it in msg.requests:
        r = db.get(m.ChargeRequest, UUID(it.request_id))
        if r and r.status != it.status:
            r.status, r.updated_at = it.status, now()
            if it.status == ChargeRequestStatus.COMPLETED:
                r.completed_at = now()
            if it.status == ChargeRequestStatus.FAILED:
                rv = db.get(m.Vehicle, r.vehicle_id)
                notice(db, rv.owner_id if rv else None, "REQUEST_FAILED", "fault", "충전 요청이 실패했어요", failure_reason(db, r), {"request_id": str(r.id)}, outbox)
            changed.add(r.vehicle_id)

    seen = set(db.scalars(select(m.Event.source_event_id).where(m.Event.source_event_id.in_([e.event_id for e in msg.events]))))
    for e in msg.events:
        if e.event_id in seen:
            continue
        v = ros_to_v.get(e.vehicle_id) if e.vehicle_id else None
        rid, tid = _uuid(e.request_id), _uuid(e.task_id)
        db.add(m.Event(source_event_id=e.event_id, at=e.at, type=e.type, vehicle_id=v.id if v else None, charger_id=e.charger_id if e.charger_id in chargers else None,
                       request_id=rid if rid and db.get(m.ChargeRequest, rid) else None, task_id=tid if tid and db.get(m.VehicleTask, tid) else None, payload=e.payload))
    db.flush()
    notify_queue_changes(db, queue_before, outbox)
    return changed


# ---------- 주차 구역 지도(02.02 전체 지도, 02.03 구역 안 맵) ----------
def _seat_states(db: Session, user_id: UUID, selected: str | None) -> tuple[dict[str, str], dict[str, int]]:
    """모든 자리의 (zone_id → 상태), (zone_id → 남은 자리). 내 자리·고르는 중인 자리는 MINE, 남이 잡았으면 TAKEN."""
    from schemas.parking_map import SeatState
    avail = {z.id: a for z, a in zone_availability(db)}  # 0 = 차 있음/남이 선정
    mine: set[str] = set()
    for v in repo.live_vehicles(db, user_id):
        ar = repo.active_request(db, v.id)
        if ar and ar.parking_zone_id:
            mine.add(ar.parking_zone_id)
        st = db.get(m.VehicleStateRow, v.id)
        if st and st.state == VehicleState.PARKED and st.zone_id:
            mine.add(st.zone_id)
    out: dict[str, str] = {}
    for zid, a in avail.items():
        if zid in mine:
            out[zid] = SeatState.MINE
        elif a <= 0:
            out[zid] = SeatState.TAKEN
        elif selected == zid:
            out[zid] = SeatState.MINE  # 지금 고르는 중인 자리
        else:
            out[zid] = SeatState.FREE
    return out, avail


def _seat_numbers(area_id: str) -> list[int]:
    from schemas.parking_map import area_seat_numbers
    return area_seat_numbers(area_id)


def parking_areas(db: Session, user_id: UUID):
    from schemas.parking_map import AREA_ROWS, AreasOut, AreaState, AreaSummary, Seat, SeatState, seat_zone_id
    states, _ = _seat_states(db, user_id, None)
    # 구역만 고른 활성 요청(아직 주차 전)은 그 구역의 빈자리 하나를 잡는다. 내 요청은 내 화면에서 has_mine으로 표시
    active = (ChargeRequestStatus.REQUESTED, ChargeRequestStatus.ACCEPTED, ChargeRequestStatus.SCHEDULED, ChargeRequestStatus.IN_PROGRESS)
    rows = db.execute(select(m.ChargeRequest.parking_area, m.Vehicle.owner_id).join(m.Vehicle, m.Vehicle.id == m.ChargeRequest.vehicle_id)
                      .where(m.ChargeRequest.status.in_(active), m.ChargeRequest.parking_area.is_not(None))).all()
    held = {a: sum(1 for x, o in rows if x == a and o != user_id) for a in AREA_ROWS}
    mine_area = {x for x, o in rows if o == user_id}
    out = []
    for aid in AREA_ROWS:
        seats = [Seat(seat_no=n, zone_id=seat_zone_id(n), state=states.get(seat_zone_id(n), SeatState.TAKEN)) for n in _seat_numbers(aid)]
        free = max(sum(1 for x in seats if x.state != SeatState.TAKEN) - held[aid], 0)
        out.append(AreaSummary(area_id=aid, name=f"{aid}구역", seat_total=len(seats), free_count=free, state=AreaState.OPEN if free else AreaState.FULL,
                               has_mine=aid in mine_area or any(x.state == SeatState.MINE for x in seats), seats=seats))
    return AreasOut(areas=out)


def parking_area_detail(db: Session, user_id: UUID, area_id: str, selected: str | None):
    from schemas.parking_map import AREA_ROWS, AreaDetailOut, AreaState, DetailSeat, SeatState, seat_zone_id
    area_id = area_id.upper()
    if area_id not in AREA_ROWS:
        return None
    states, avail = _seat_states(db, user_id, selected)
    seats = []
    for row, numbers in enumerate(AREA_ROWS[area_id]):
        for col, n in enumerate(numbers):
            zid = seat_zone_id(n)
            seats.append(DetailSeat(seat_no=n, zone_id=zid, state=states.get(zid, SeatState.TAKEN), row=row, col=col))
    free = sum(1 for x in seats if x.state != SeatState.TAKEN)
    sel_ok = None
    if selected:
        sel_ok = states.get(selected) in (SeatState.MINE, SeatState.FREE)
    return AreaDetailOut(area_id=area_id, name=f"{area_id}구역", seat_total=len(seats), free_count=free, state=AreaState.OPEN if free else AreaState.FULL,
                         rows=len(AREA_ROWS[area_id]), cols=max(len(r) for r in AREA_ROWS[area_id]), entrance=None,
                         seats=seats, selected_zone_id=selected, selected_ok=sel_ok)
