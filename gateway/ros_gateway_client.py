"""관제 PC에서 실행하는 게이트웨이(참고 구현, ROS 2 환경에서 아직 시험하지 않음).

서버(FastAPI, ROS_MODE=gateway)의 /ws/gateway 로 먼저 연결해 두고,
  서버 → 관제: /charging/request, /charging/cancel, /admin/command ... 를 ROS 토픽으로 발행
  관제 → 서버: ROS 토픽 /central_status 를 구독해 그대로 전달
한다. 모든 토픽은 std_msgs/String(JSON 문자열)이며 계약은 backend/ros_schemas/, docs/AIOT_CENTRAL_INTERFACE.md.

실행:  pip install websockets   (rclpy는 ROS 2 설치에 포함)
       GATEWAY_URL=wss://서버주소/ws/gateway GATEWAY_TOKEN=서버와 같은 값 python3 ros_gateway_client.py
"""
import asyncio
import json
import os
import threading

import rclpy
import websockets
from rclpy.node import Node
from std_msgs.msg import String

URL = os.environ["GATEWAY_URL"]
TOKEN = os.environ["GATEWAY_TOKEN"]
# 서버가 관제로 보내는 토픽(발행). 새 토픽이 생기면 여기에 추가한다.
OUT_TOPICS = ["/charging/request", "/charging/cancel", "/admin/command", "/emergency_stop"]
IN_TOPICS = ["/central_status"]  # 관제가 서버로 보내는 토픽(구독)


class Gateway(Node):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__("aiot_gateway")
        self.loop, self.out_q = loop, asyncio.Queue()
        self.pubs = {t: self.create_publisher(String, t, 10) for t in OUT_TOPICS}
        for t in IN_TOPICS:
            self.create_subscription(String, t, lambda m, t=t: self._to_server(t, m.data), 10)

    def _to_server(self, topic: str, data: str):  # ROS 스레드에서 호출
        self.loop.call_soon_threadsafe(self.out_q.put_nowait, json.dumps({"topic": topic, "data": data}, ensure_ascii=False))

    def publish(self, topic: str, data: str):
        if topic in self.pubs:
            self.pubs[topic].publish(String(data=data))


async def run(node: Gateway):
    while True:  # 끊기면 3초 뒤 다시 연결
        try:
            async with websockets.connect(URL, ping_interval=20) as ws:
                await ws.send(json.dumps({"type": "auth", "token": TOKEN}))
                assert json.loads(await ws.recv()).get("type") == "auth_ok"
                print("connected to server")

                async def up():
                    while True:
                        await ws.send(await node.out_q.get())

                up_task = asyncio.create_task(up())
                try:
                    async for raw in ws:
                        d = json.loads(raw)
                        node.publish(d["topic"], d["data"])
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
    loop.run_until_complete(run(node))


if __name__ == "__main__":
    main()
