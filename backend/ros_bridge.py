"""FastAPI ↔ ROS 2. mock 모드는 발행 기록만 남기고, 수신은 inject()로 시험한다."""
from __future__ import annotations

from typing import Callable, Protocol

from pydantic import BaseModel

from ros_schemas import parse_topic, to_ros_json


class RosBridge(Protocol):
    def publish(self, topic: str, msg: BaseModel) -> None: ...
    def on_central_status(self, cb: Callable) -> None: ...


class MockRosBridge:
    def __init__(self):
        self.published: list[tuple[str, str]] = []  # (topic, JSON 문자열) — 실제 발행과 같은 직렬화
        self._cb: Callable | None = None

    def publish(self, topic: str, msg: BaseModel) -> None:
        self.published.append((topic, to_ros_json(msg)))

    def on_central_status(self, cb: Callable) -> None:
        self._cb = cb

    def inject_central_status(self, data: str) -> None:
        """중앙관제가 /central_status를 보낸 것처럼 수신 처리."""
        if self._cb:
            self._cb(parse_topic("/central_status", data))

    def last(self, topic: str) -> dict | None:
        import json

        items = [d for t, d in self.published if t == topic]
        return json.loads(items[-1]) if items else None


class GatewayRosBridge:
    """관제 PC가 서버로 먼저 WebSocket(/ws/gateway)을 연결해 두고, 서버가 그 선으로 토픽을 주고받는다.

    관제가 노트북·집 네트워크에 있어 서버가 접속할 수 없을 때 쓴다(관제 → 서버 방향 연결만 필요).
    게이트웨이 종류(연결할 때 정해진다):
      - "aiot"   : gateway/ros_gateway_client.py. 첫 메시지 auth. {"topic": "/charging/request", "data": "<JSON 문자열>"}
      - "macaron": 관제 담당 게이트웨이. Authorization 헤더. {"type": "charging_request", "payload": {...}} (macaron.py에서 번역)
    게이트웨이가 끊겨 있는 동안 서버가 보낸 메시지는 최근 500개까지 모아 두었다가 다시 연결되면 보낸다.
    """

    def __init__(self):
        from collections import deque

        self.pending: deque[tuple[str, str]] = deque(maxlen=500)  # (topic, JSON 문자열)
        self.connected = False
        self.protocol = "aiot"
        self.vehicle_of: dict[str, str] = {}  # request_id → ros vehicle_id (관제 거절 응답을 요청에 붙이려고)
        self._ws = None
        self._loop = None
        self._cb: Callable | None = None

    def publish(self, topic: str, msg: BaseModel) -> None:
        data = to_ros_json(msg)
        rid, vid = getattr(msg, "request_id", None), getattr(msg, "vehicle_id", None)
        if rid and vid:
            self.vehicle_of[str(rid)] = vid
        if not self._send(topic, data):
            self.pending.append((topic, data))

    def on_central_status(self, cb: Callable) -> None:
        self._cb = cb

    # --- /ws/gateway 라우트가 쓰는 부분 ---
    def _wire(self, topic: str, data: str) -> str | None:
        import json

        if self.protocol == "macaron":
            from macaron import to_controller

            env = to_controller(topic, data)
            return json.dumps(env, ensure_ascii=False) if env else None  # 관제 미지원 토픽은 버린다
        return json.dumps({"topic": topic, "data": data}, ensure_ascii=False)

    def _send(self, topic: str, data: str) -> bool:
        import asyncio

        if not (self.connected and self._ws and self._loop and not self._loop.is_closed()):
            return False
        item = self._wire(topic, data)
        if item is not None:
            asyncio.run_coroutine_threadsafe(self._ws.send_text(item), self._loop)
        return True

    async def attach(self, ws, loop, protocol: str = "aiot") -> None:
        self._ws, self._loop, self.connected, self.protocol = ws, loop, True, protocol
        while self.pending:  # 끊겨 있던 동안 쌓인 것 먼저 전달
            item = self._wire(*self.pending.popleft())
            if item is not None:
                await ws.send_text(item)

    def detach(self, ws) -> None:
        if self._ws is ws:
            self._ws, self.connected = None, False

    def receive(self, raw: str) -> None:
        import json

        d = json.loads(raw)
        if not self._cb:
            return
        if self.protocol == "macaron":
            from macaron import failure_from_result, status_from_controller

            if d.get("type") == "central_status":
                self._cb(parse_topic("/central_status", json.dumps(status_from_controller(d.get("payload") or {}))))
            elif d.get("type") == "request_result":
                msg = failure_from_result(d, self.vehicle_of)
                if msg:
                    self._cb(parse_topic("/central_status", json.dumps(msg)))
            return
        if d.get("topic") == "/central_status":  # 그 밖의 토픽은 무시
            self._cb(parse_topic("/central_status", d["data"]))


class RclpyBridge:  # ROS 2 노드 연결 단계에서 구현 (rclpy: ROS 터미널 환경에서만 import)
    def __init__(self):
        raise NotImplementedError("ROS_MODE=rclpy 는 아직 구현 전. ROS_MODE=mock 사용")
