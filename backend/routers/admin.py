import uuid
from collections import Counter
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

import models as m
import repo
from database import get_db
from deps import CurrentUser, require_admin
from errors import ApiError
from ros_schemas.messages import AdminAction, AdminCommandMsg, EmergencyAction, EmergencyStopMsg
from schemas.admin import (AdminActionResponse, AdminOverview, AdminOwner, AdminVehicleOut, AdminVehiclePatch, ChargerOut, ChargerPatch, EmergencyStopRequest, EmergencyStopState, EventOut, QueueActionRequest, QueueItem, QueueResponse, SettingOut, SettingsPatch, TaskCancelRequest)
from schemas.common import ACTIVE_REQUEST_STATUSES, ChargeRequestStatus as S, ChargerState, ErrorCode, VehicleState
from services import is_online, request_out, vehicle_status
from state import ros, runtime

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _vehicle_out(db: Session, v: m.Vehicle) -> AdminVehicleOut:
    vs = vehicle_status(db, v)
    p = db.get(m.Profile, v.owner_id) if v.owner_id else None
    return AdminVehicleOut(
        id=v.id, ros_vehicle_id=v.ros_vehicle_id, plate_no=v.plate_no, model=v.model, battery_kwh=v.battery_kwh, max_charge_kw=v.max_charge_kw,
        owner=AdminOwner(id=p.id, name=p.name) if p else None, state=vs.state, online=vs.online, soc=vs.soc, zone_id=vs.zone_id, pose=vs.pose,
        charger_id=vs.charger_id, current_task=vs.current_task, active_request=vs.active_request, last_seen_at=vs.last_seen_at)


def _emergency(db: Session) -> bool:
    return bool(repo.get_setting(db, "emergency_stop", {"active": False}).get("active"))


@router.get("/overview", response_model=AdminOverview)
def overview(db: Session = Depends(get_db)):
    vehicles = repo.live_vehicles(db)
    states = {s.vehicle_id: s for s in db.scalars(select(m.VehicleStateRow))}
    by_state = Counter(states[v.id].state for v in vehicles if v.id in states)
    ch_states = {s.charger_id: s.state for s in db.scalars(select(m.ChargerStateRow))}
    chargers = list(db.scalars(select(m.Charger)))
    active = db.scalars(select(m.ChargeRequest.id).where(m.ChargeRequest.status.in_(ACTIVE_REQUEST_STATUSES))).all()
    return AdminOverview(
        server_time=repo.now(), vehicles_by_state=dict(by_state), vehicles_offline=sum(1 for v in vehicles if not is_online(states.get(v.id))),
        chargers_by_state=dict(Counter(ch_states.get(c.id) for c in chargers if ch_states.get(c.id))), active_requests=len(active),
        queue_length=runtime.queue_length, fault_count=by_state.get(VehicleState.FAULT, 0), emergency_stop_active=_emergency(db),
        central_online=runtime.last_central_at is not None and (repo.now() - runtime.last_central_at).total_seconds() <= 5)


@router.get("/vehicles", response_model=list[AdminVehicleOut])
def vehicles(db: Session = Depends(get_db)):
    return [_vehicle_out(db, v) for v in repo.live_vehicles(db)]


@router.patch("/vehicles/{vehicle_id}", response_model=AdminVehicleOut)
def patch_vehicle(vehicle_id: UUID, body: AdminVehiclePatch, a: CurrentUser = Depends(require_admin), db: Session = Depends(get_db)):
    v = repo.live_vehicle(db, vehicle_id)
    if not v:
        raise ApiError(404, ErrorCode.NOT_FOUND, "차량을 찾을 수 없습니다.")
    new = body.ros_vehicle_id
    if new is not None:
        other = repo.vehicle_by_ros(db, new)
        if other and other.id != v.id:
            raise ApiError(409, ErrorCode.ROS_ID_DUPLICATED, "이미 다른 차량에 배정된 ROS 차량입니다.")
    if new is None and repo.active_request(db, v.id):
        raise ApiError(409, ErrorCode.HAS_ACTIVE_WORK, "진행 중인 요청이 있어 배정을 해제할 수 없습니다.")
    before = v.ros_vehicle_id
    v.ros_vehicle_id, v.updated_at = new, repo.now()
    repo.log_audit(db, a.id, "vehicle.assign_ros_id", "vehicle", v.id, body.reason, {"ros_vehicle_id": before}, {"ros_vehicle_id": new})
    db.commit()
    return _vehicle_out(db, v)


def _charger_out(db: Session, c: m.Charger) -> ChargerOut:
    st = db.get(m.ChargerStateRow, c.id)
    return ChargerOut(id=c.id, name=c.name, max_power_kw=c.max_power_kw, state=st.state if st else None, maintenance=bool(st and st.maintenance),
                      vehicle_id=st.assigned_vehicle_id if st else None, power_kw=st.output_kw if st else None, updated_at=st.updated_at if st else None)


@router.get("/chargers", response_model=list[ChargerOut])
def chargers(db: Session = Depends(get_db)):
    return [_charger_out(db, c) for c in db.scalars(select(m.Charger).order_by(m.Charger.id))]


@router.patch("/chargers/{charger_id}", response_model=ChargerOut)
def patch_charger(charger_id: str, body: ChargerPatch, a: CurrentUser = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.get(m.Charger, charger_id)
    if not c:
        raise ApiError(404, ErrorCode.NOT_FOUND, "충전기를 찾을 수 없습니다.")
    st = db.get(m.ChargerStateRow, charger_id)
    before = dict(state=st.state.value if st else None, maintenance=bool(st and st.maintenance), max_power_kw=c.max_power_kw)
    if body.state == ChargerState.MAINTENANCE:
        if st and st.state == ChargerState.IN_USE:
            st.maintenance = True  # 현재 작업 종료 후 점검 진입
        else:
            st = st or m.ChargerStateRow(charger_id=charger_id, state=ChargerState.MAINTENANCE, last_seen_at=repo.now())
            st.state = ChargerState.MAINTENANCE
            db.merge(st)
    elif body.state == ChargerState.AVAILABLE:
        if st:
            st.maintenance = False
            if st.state == ChargerState.MAINTENANCE:
                st.state = ChargerState.AVAILABLE
    if body.max_power_kw:
        c.max_power_kw = body.max_power_kw
    c.updated_at = repo.now()
    repo.log_audit(db, a.id, "charger.update", "charger", charger_id, body.reason, before, body.model_dump(mode="json", exclude={"reason"}, exclude_none=True))
    db.commit()
    return _charger_out(db, c)


@router.get("/queue", response_model=QueueResponse)
def queue(db: Session = Depends(get_db)):
    rows = db.scalars(select(m.ChargeRequest).where(m.ChargeRequest.status.in_([S.REQUESTED, S.ACCEPTED, S.SCHEDULED])).order_by(m.ChargeRequest.created_at))
    items = []
    for i, r in enumerate(rows, 1):
        v = db.get(m.Vehicle, r.vehicle_id)
        items.append(QueueItem(request=request_out(r), vehicle_id=v.id, plate_no=v.plate_no, position=i, planned_charger_id=None, planned_start_at=None, planned_parked_at=None))
    return QueueResponse(items=items)


@router.post("/queue", response_model=AdminActionResponse)
def queue_action(body: QueueActionRequest, a: CurrentUser = Depends(require_admin), db: Session = Depends(get_db)):
    r = db.get(m.ChargeRequest, body.request_id)
    if not r:
        raise ApiError(404, ErrorCode.NOT_FOUND, "요청을 찾을 수 없습니다.")
    v = db.get(m.Vehicle, r.vehicle_id)
    if not v.ros_vehicle_id:
        raise ApiError(422, ErrorCode.VEHICLE_NOT_ASSIGNED, "ROS 차량이 배정되지 않았습니다.")
    audit_id = repo.log_audit(db, a.id, f"queue.{body.action.value}", "charge_request", r.id, body.reason, {"status": r.status.value})
    db.commit()
    ros.publish("/admin/command", AdminCommandMsg(command_id=str(uuid.uuid4()), action=AdminAction(body.action.value), vehicle_id=v.ros_vehicle_id, request_id=str(r.id), charger_id=body.charger_id, reason=body.reason, admin_id=str(a.id)))
    return AdminActionResponse(audit_log_id=audit_id)


@router.post("/tasks/{task_id}/cancel", response_model=AdminActionResponse)
def cancel_task(task_id: UUID, body: TaskCancelRequest, a: CurrentUser = Depends(require_admin), db: Session = Depends(get_db)):
    t = db.get(m.VehicleTask, task_id)
    v = db.get(m.Vehicle, t.vehicle_id) if t else None
    if not t or not v or not v.ros_vehicle_id:
        raise ApiError(404, ErrorCode.NOT_FOUND, "작업을 찾을 수 없습니다.")
    audit_id = repo.log_audit(db, a.id, "task.cancel", "vehicle_task", task_id, body.reason, {"status": t.status.value})
    db.commit()
    ros.publish("/admin/command", AdminCommandMsg(command_id=str(uuid.uuid4()), action=AdminAction.CANCEL, vehicle_id=v.ros_vehicle_id, task_id=str(task_id), reason=body.reason, admin_id=str(a.id)))
    return AdminActionResponse(audit_log_id=audit_id)


@router.post("/emergency-stop", response_model=EmergencyStopState)
def emergency_stop(body: EmergencyStopRequest, a: CurrentUser = Depends(require_admin), db: Session = Depends(get_db)):
    active = body.action.value == "STOP"
    repo.log_audit(db, a.id, f"emergency.{body.action.value.lower()}", "system", "ALL", body.reason, {"active": _emergency(db)}, {"active": active})
    repo.set_setting(db, "emergency_stop", {"active": active}, a.id)  # 이후 /central_status가 확정값으로 덮어씀
    db.commit()
    ros.publish("/emergency_stop", EmergencyStopMsg(action=EmergencyAction(body.action.value), reason=body.reason, issued_by=str(a.id), issued_at=repo.now()))
    return EmergencyStopState(active=active, changed_at=repo.now())


@router.get("/events", response_model=list[EventOut])
def events(type: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    q = select(m.Event).order_by(m.Event.id.desc()).limit(min(limit, 500))
    if type:
        q = q.where(m.Event.type == type)
    return [EventOut.model_validate(e) for e in db.scalars(q)]


_HIDDEN = {"emergency_stop"}  # 내부 상태 키는 설정 목록에서 숨김


@router.get("/settings", response_model=list[SettingOut])
def get_settings(db: Session = Depends(get_db)):
    return [SettingOut.model_validate(s, from_attributes=True) for s in db.scalars(select(m.Setting).order_by(m.Setting.key)) if s.key not in _HIDDEN]


@router.patch("/settings", response_model=list[SettingOut])
def patch_settings(body: SettingsPatch, a: CurrentUser = Depends(require_admin), db: Session = Depends(get_db)):
    if _HIDDEN & set(body.values):
        raise ApiError(422, ErrorCode.VALIDATION_ERROR, "변경할 수 없는 설정 키입니다.")
    for k, val in body.values.items():
        repo.set_setting(db, k, val, a.id)
    repo.log_audit(db, a.id, "settings.update", "settings", ",".join(body.values), body.reason, None, body.values)
    db.commit()
    return get_settings(db)
