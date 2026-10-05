"""토픽 이름 ↔ 메시지 모델 대응표와 직렬화 헬퍼."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from . import messages as m

Bridge = Literal["none", "0->vehicle", "vehicle->0"]


@dataclass(frozen=True)
class TopicSpec:
    name: str
    model: type[BaseModel]
    publisher: str
    subscriber: str
    bridge: Bridge  # docs/AIOT_DOMAIN_CONFIG.md의 안과 동일(확정 전)


TOPICS: dict[str, TopicSpec] = {
    t.name: t
    for t in [
        TopicSpec("/charging/request", m.ChargingRequestMsg, "fastapi", "central", "none"),
        TopicSpec("/charging/cancel", m.ChargingCancelMsg, "fastapi", "central", "none"),
        TopicSpec("/admin/command", m.AdminCommandMsg, "fastapi", "central", "none"),
        TopicSpec("/emergency_stop", m.EmergencyStopMsg, "fastapi", "central+vehicle", "0->vehicle"),
        TopicSpec("/vehicle_task", m.VehicleTaskMsg, "central", "vehicle", "0->vehicle"),
        TopicSpec("/vehicle_task_status", m.VehicleTaskStatusMsg, "vehicle", "central", "vehicle->0"),
        TopicSpec("/vehicle_command", m.VehicleCommandMsg, "central", "charger_sim", "none"),
        TopicSpec("/charging_status", m.ChargingStatusMsg, "charger_sim", "central", "none"),
        TopicSpec("/central_status", m.CentralStatusMsg, "central", "fastapi", "none"),
    ]
}


def to_ros_json(msg: BaseModel) -> str:
    """std_msgs/String.data 에 넣을 JSON 문자열."""
    return msg.model_dump_json(exclude_none=False)


def parse_topic(topic: str, data: str) -> BaseModel:
    """수신한 String.data 를 해당 토픽 모델로 검증·변환. 실패 시 ValidationError."""
    return TOPICS[topic].model.model_validate_json(data)
