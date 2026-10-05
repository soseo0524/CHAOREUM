import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ros_schemas import TOPICS, parse_topic, to_ros_json
from ros_schemas.messages import *

U = lambda: str(uuid.uuid4())
NOW = datetime.now(timezone.utc)

SAMPLES = {
    "/charging/request": dict(request_id=U(), vehicle_id="CAR_01", desired_finish_at=(NOW + timedelta(hours=3)).isoformat(), target_soc=80, min_soc=60, battery_kwh=60, max_charge_kw=11),
    "/charging/cancel": dict(request_id=U(), vehicle_id="CAR_01", requested_by="user"),
    "/admin/command": dict(command_id=U(), action="reassign", vehicle_id="CAR_01", request_id=U(), charger_id="CHARGER_02", reason="점검", admin_id=U()),
    "/emergency_stop": dict(action="STOP", reason="장애물", issued_by=U(), issued_at=NOW.isoformat()),
    "/vehicle_task": dict(task_id=U(), request_id=U(), vehicle_id="CAR_01", type="MOVE_TO_PARKING", target_id="PARKING_02", target_pose=dict(x=12.3, y=4.8, yaw=1.57)),
    "/vehicle_task_status": dict(task_id=U(), vehicle_id="CAR_01", status="RUNNING", progress=0.4),
    "/vehicle_command": dict(command="START_CHARGING", vehicle_id="CAR_01", charger_id="CHARGER_01", request_id=U(), target_soc=80),
    "/charging_status": dict(vehicle_id="CAR_01", charger_id="CHARGER_01", soc=55.5, power_kw=7.2, charging=True),
    "/central_status": dict(at=NOW.isoformat(), vehicles=[dict(vehicle_id="CAR_01", state="CHARGING", soc=55, last_seen_at=NOW.isoformat())], chargers=[dict(charger_id="CHARGER_01", state="IN_USE", vehicle_id="CAR_01", power_kw=7.2)], requests=[dict(request_id=U(), vehicle_id="CAR_01", status="IN_PROGRESS")], tasks=[dict(task_id=U(), vehicle_id="CAR_01", type="MOVE_TO_CHARGER", status="RUNNING", target_id="CHARGER_01", target_pose=dict(x=1, y=2, yaw=0.1), progress=0.5)], events=[dict(event_id="e1", type="CHARGE_STARTED", at=NOW.isoformat())]),
}


def test_every_topic_has_sample():
    assert set(SAMPLES) == set(TOPICS) and len(TOPICS) == 9


@pytest.mark.parametrize("topic", list(SAMPLES))
def test_roundtrip(topic):
    msg = parse_topic(topic, json.dumps(SAMPLES[topic]))
    again = parse_topic(topic, to_ros_json(msg))
    assert again == msg and json.loads(to_ros_json(msg))["schema_version"] == 1


def test_unknown_field_ignored():
    d = dict(SAMPLES["/charging_status"], new_field=1)
    parse_topic("/charging_status", json.dumps(d))


def test_naive_datetime_rejected():
    d = dict(SAMPLES["/charging/request"], desired_finish_at="2030-01-01T00:00:00")
    with pytest.raises(ValidationError):
        parse_topic("/charging/request", json.dumps(d))


def test_bad_uuid_and_soc():
    with pytest.raises(ValidationError):
        parse_topic("/charging/cancel", json.dumps(dict(SAMPLES["/charging/cancel"], request_id="req_001")))
    with pytest.raises(ValidationError):
        parse_topic("/charging/request", json.dumps(dict(SAMPLES["/charging/request"], min_soc=90)))


def test_status_rules():
    with pytest.raises(ValidationError):
        parse_topic("/vehicle_task_status", json.dumps(dict(SAMPLES["/vehicle_task_status"], status="FAILED")))
    with pytest.raises(ValidationError):
        parse_topic("/vehicle_command", json.dumps(dict(SAMPLES["/vehicle_command"], target_soc=None)))
    with pytest.raises(ValidationError):  # reassign인데 charger_id 없음
        parse_topic("/admin/command", json.dumps({k: v for k, v in SAMPLES["/admin/command"].items() if k != "charger_id"}))


def test_emergency_default_all():
    assert parse_topic("/emergency_stop", json.dumps(SAMPLES["/emergency_stop"])).vehicle_id == "ALL"
