import asyncio
import hmac
import logging

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
    """ROS_MODE=gateway 에서 관제 쪽 게이트웨이가 연결하는 선. 첫 메시지 {"type":"auth","token":GATEWAY_TOKEN}."""
    await ws.accept()
    try:
        msg = await asyncio.wait_for(ws.receive_json(), settings.ws_auth_timeout_s)
        ok = msg.get("type") == "auth" and bool(settings.gateway_token) and hmac.compare_digest(str(msg.get("token", "")), settings.gateway_token)
    except (asyncio.TimeoutError, ValueError, WebSocketDisconnect):
        ok = False
    if not ok or not hasattr(ros, "attach"):
        await ws.close(code=4401)
        return
    await ws.send_json({"type": "auth_ok"})
    await ros.attach(ws, asyncio.get_running_loop())
    try:
        while True:
            raw = await ws.receive_text()
            try:
                await asyncio.to_thread(ros.receive, raw)  # DB 작업이 있으므로 이벤트 루프 밖에서
            except Exception:  # 잘못된 메시지 하나가 연결을 끊지 않게
                logging.getLogger("gateway").exception("gateway message rejected")
    except WebSocketDisconnect:
        pass
    finally:
        ros.detach(ws)
