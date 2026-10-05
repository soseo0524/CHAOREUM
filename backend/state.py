"""프로세스 전역 객체: ROS 브리지, WS 허브, 휘발성 런타임 상태."""
from dataclasses import dataclass
from datetime import datetime

from config import settings
from ros_bridge import GatewayRosBridge, MockRosBridge, RclpyBridge
import asyncio

import push
from schemas.status import NotificationOut
from services import Hub

hub = Hub()
ros = {"mock": MockRosBridge, "gateway": GatewayRosBridge}.get(settings.ros_mode, RclpyBridge)()


@dataclass
class Runtime:
    last_central_at: datetime | None = None
    queue_length: int = 0


runtime = Runtime()


def dispatch(db, outbox: list) -> None:
    """저장된 알림을 보낸다: 설정이 켜진 것만 푸시, 접속 중이면 WebSocket으로도. 커밋 뒤에 부른다."""
    for n, push_on in outbox:
        if push_on:
            push.send(db, n.user_id, n.title, n.body, n.data)
        if hub.loop and not hub.loop.is_closed() and hub.clients:
            payload = {"type": "notification", "data": NotificationOut.model_validate(n).model_dump(mode="json")}
            asyncio.run_coroutine_threadsafe(hub.send_vehicle(n.user_id, payload), hub.loop)
