"""ROS 2 토픽 JSON 계약. 모든 토픽은 std_msgs/String(data = JSON 문자열).

규칙
- vehicle_id = vehicles.ros_vehicle_id (예: CAR_01). request_id/task_id = UUID 문자열.
  DB id ↔ ROS id 변환은 FastAPI가 한다.
- 시각은 UTC ISO 8601('Z' 또는 +00:00). timezone 없는 시각은 거부한다.
- 모든 메시지에 schema_version(현재 1)이 있다. 하위 호환 필드 추가는 버전 유지, 의미 변경은 올린다.
- 수신은 모르는 필드를 무시(extra=ignore)해 노드별 배포 시점이 달라도 깨지지 않게 하고,
  발행은 to_ros_json()으로 모델을 거쳐서만 만든다.
"""
from .messages import *  # noqa: F401,F403
from .topics import TOPICS, TopicSpec, parse_topic, to_ros_json  # noqa: F401
