import asyncio
import hmac
import json
import logging
from collections import deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import settings
from deps import authenticate_token
from errors import ApiError
from schemas.status import WsAuthOk
from state import hub, ros

router = APIRouter()


@router.websocket("/ws/status")
async def ws_status(ws: WebSocket):
    await ws.accept()
    try:  # 첫 메시지는 5초 안에 {"type":"auth","token":...} (토큰을 URL에 넣지 않는다)
        msg = await asyncio.wait_for(ws.receive_json(), settings.ws_auth_timeout_s)
        if msg.get("type") != "auth":
            raise ApiError(401, "UNAUTHENTICATED", "auth required")
        user = authenticate_token(msg.get("token", ""))
    except (asyncio.TimeoutError, ApiError, ValueError, WebSocketDisconnect):
        await ws.close(code=4401)
        return
    hub.loop = asyncio.get_running_loop()
    await ws.send_json(WsAuthOk(role=user.role).model_dump(mode="json"))
    hub.clients.append((ws, user.id, user.role.value))
    try:
        while True:
            await ws.receive_text()  # 클라이언트 ping 등은 무시
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients = [c for c in hub.clients if c[0] is not ws]


@router.websocket("/ws/gateway")
async def ws_gateway(ws: WebSocket):
    """ROS_MODE=gateway 에서 관제 담당 게이트웨이(macaron8)가 연결하는 선.
    인증은 `Authorization: Bearer <GATEWAY_TOKEN>` 헤더, 메시지는 {type, payload} 형식(macaron.py가 번역)."""
    await ws.accept()
    header = ws.headers.get("authorization", "")
    ok = header.lower().startswith("bearer ") and bool(settings.gateway_token) and hmac.compare_digest(header[7:].strip(), settings.gateway_token)
    if not ok or not hasattr(ros, "attach"):
        await ws.close(code=4401)
        return
    await ros.attach(ws, asyncio.get_running_loop())
    # 관제는 1초마다 상태를 보내는데 반영(DB)이 그보다 느리면 메시지가 쌓여 앱이 점점 지난 상태를 보여 준다.
    # 받기와 반영을 나눠, 반영이 밀렸으면 지난 상태는 건너뛰고 가장 최근 상태만 반영한다(요청 응답은 모두 순서대로).
    inbox: deque[tuple[bool, str]] = deque()  # (관제 상태 메시지인지, 원문)
    wake = asyncio.Event()

    async def apply():
        while True:
            await wake.wait()
            wake.clear()
            while inbox:
                is_status, raw = inbox.popleft()
                if is_status and any(s for s, _ in inbox):
                    continue
                try:
                    await asyncio.to_thread(ros.receive, raw)  # DB 작업이 있으므로 이벤트 루프 밖에서
                except Exception:  # 잘못된 메시지 하나가 연결을 끊지 않게
                    logging.getLogger("gateway").exception("gateway message rejected")

    worker = asyncio.create_task(apply())
    try:
        while True:
            raw = await ws.receive_text()
            inbox.append((_is_status(raw), raw))  # 받는 즉시 차량 신호 시각을 남긴다(_is_status)
            wake.set()
    except WebSocketDisconnect:
        pass
    finally:
        worker.cancel()  # 끊긴 선에 쌓인 지난 메시지는 반영하지 않는다
        ros.detach(ws)


def _is_status(raw: str) -> bool:
    try:
        d = json.loads(raw)
    except ValueError:
        return False
    if not isinstance(d, dict) or d.get("type") != "central_status":
        return False
    ros.mark_heard(d.get("payload") or {})
    return True
