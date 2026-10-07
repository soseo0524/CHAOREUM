"""관제 PC에서 실행하는 게이트웨이(ROS 2 환경에서 아직 시험하지 않음).

서버(FastAPI, ROS_MODE=gateway)의 /ws/gateway 로 먼저 연결해 두고 그 한 줄로 관제와 서버를 잇는다.

두 가지 방식:
  1) 기본(우리 계약을 그대로 따르는 관제):
       서버 → 관제: /charging/request, /charging/cancel, /admin/command, /emergency_stop 를 ROS 토픽으로 발행
       관제 → 서버: ROS 토픽 /central_status 를 구독해 그대로 전달
  2) CONTROLLER_API 설정 시(macaron8_AIOT-main 관제):
       서버 → 관제: 요청·취소를 관제 HTTP API(POST /api/charging/requests)로 바꿔 호출
       관제 → 서버: 관제 /central_status 를 우리 형식으로 바꿔 전달
     번역 규칙은 macaron_adapter.py.

실행(관제 PC, ROS 2 환경을 source 한 터미널):
  pip install websockets
  GATEWAY_URL=ws://<서버 IP>:8000/ws/gateway GATEWAY_TOKEN=<서버와 같은 값> \\
  CONTROLLER_API=http://127.0.0.1:8081 python3 ros_gateway_client.py
"""
import asyncio
import json
import os
import threading
import urllib.error
import urllib.request

import rclpy
import websockets
from rclpy.node import Node
from std_msgs.msg import String

from macaron_adapter import HttpCall, Translator

URL = os.environ["GATEWAY_URL"]
TOKEN = os.environ["GATEWAY_TOKEN"]
CONTROLLER_API = os.environ.get("CONTROLLER_API", "").rstrip("/")  # 비우면 1) 기본 방식
# 서버가 관제로 보내는 토픽(발행). 새 토픽이 생기면 여기에 추가한다.
OUT_TOPICS = ["/charging/request", "/charging/cancel", "/admin/command", "/emergency_stop"]
IN_TOPICS = ["/central_status"]  # 관제가 서버로 보내는 토픽(구독)


class Gateway(Node):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__("aiot_gateway")
        self.loop, self.out_q = loop, asyncio.Queue()
        self.translator = Translator() if CONTROLLER_API else None
        self.http_q: asyncio.Queue = asyncio.Queue()  # 관제 HTTP 호출은 순서대로 하나씩
        self.pubs = {} if self.translator else {t: self.create_publisher(String, t, 10) for t in OUT_TOPICS}
        for t in IN_TOPICS:
            self.create_subscription(String, t, lambda m, t=t: self._to_server(t, m.data), 10)

    def _to_server(self, topic: str, data: str):  # ROS 스레드에서 호출
        if self.translator:
            try:
                data = json.dumps(self.translator.central_status(data), ensure_ascii=False)
            except Exception as e:  # noqa: BLE001  번역 실패 한 건이 게이트웨이를 멈추지 않게
                self.get_logger().error(f"central_status 번역 실패: {e}")
                return
        self.loop.call_soon_threadsafe(self.out_q.put_nowait, json.dumps({"topic": topic, "data": data}, ensure_ascii=False))

    def from_server(self, topic: str, data: str):
        if self.translator:
            for call in self.translator.outbound(topic, data):
                self.http_q.put_nowait(call)
            self.flush_log()
        elif topic in self.pubs:
            self.pubs[topic].publish(String(data=data))

    def flush_log(self):
        while self.translator and self.translator.log:
            self.get_logger().info(self.translator.log.pop(0))


def _post(body: dict) -> tuple[int, dict | None]:
    req = urllib.request.Request(
        f"{CONTROLLER_API}/api/charging/requests",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, None


async def http_worker(node: Gateway):
    """관제 HTTP 호출. 관제가 꺼져 있거나 503/504면 같은 내용으로 다시 시도한다(관제가 같은 request_id 재시도를 안전하게 처리)."""
    while True:
        call: HttpCall | None = await node.http_q.get()
        delay = 1
        while call:
            try:
                status, body = await asyncio.to_thread(_post, call.body)
            except OSError as e:  # 연결 거부·시간 초과
                node.get_logger().warning(f"관제 API 연결 실패, {delay}초 뒤 재시도: {e}")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            if status in (503, 504):
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            call = node.translator.on_http_result(call, status, body)
            node.flush_log()


async def run(node: Gateway):
    while True:  # 끊기면 3초 뒤 다시 연결
        try:
            async with websockets.connect(URL, ping_interval=20) as ws:
                await ws.send(json.dumps({"type": "auth", "token": TOKEN}))
                assert json.loads(await ws.recv()).get("type") == "auth_ok"
                print("connected to server" + (f" (관제 API {CONTROLLER_API})" if CONTROLLER_API else ""))

                async def up():
                    while True:
                        await ws.send(await node.out_q.get())

                up_task = asyncio.create_task(up())
                try:
                    async for raw in ws:
                        d = json.loads(raw)
                        node.from_server(d["topic"], d["data"])
                finally:
                    up_task.cancel()
        except Exception as e:  # noqa: BLE001
            print("disconnected:", e)
            await asyncio.sleep(3)


def main():
    rclpy.init()
    loop = asyncio.new_event_loop()
    node = Gateway(loop)
    threading.Thread(target=rclpy.spin, args=(node,), daemon=True).start()
    if CONTROLLER_API:
        loop.create_task(http_worker(node))
    loop.run_until_complete(run(node))


if __name__ == "__main__":
    main()
