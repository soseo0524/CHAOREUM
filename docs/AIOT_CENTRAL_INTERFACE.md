# AIOT 중앙관제 인터페이스 (관제 담당자용)

관제시스템은 다른 담당자가 만든다. 사용자 앱·FastAPI는 아래 ROS 2 토픽 계약으로만 관제와 통신한다. 코드 기준은 `backend/ros_schemas/messages.py`(Pydantic)이며, 이 문서는 그 요약이다. 도메인 배치는 `docs/AIOT_DOMAIN_CONFIG.md`(초안).

## 공통 규칙

- 모든 토픽은 `std_msgs/String`이고 `data`는 JSON 문자열이다.
- `vehicle_id`는 `ros_vehicle_id`(예: CAR_01). `request_id`·`task_id`는 UUID 문자열(`req_001` 같은 값은 거부).
- 시각은 timezone이 있는 UTC ISO 8601. timezone 없는 시각은 거부된다.
- 모든 메시지에 `schema_version`(현재 1). 수신 측은 모르는 필드를 무시한다.
- ROS Action은 쓰지 않는다(Domain Bridge가 토픽만 넘김). 요청·작업의 진행은 `request_id`/`task_id`로 추적한다.

## 서버 연결 방식 (ROS_MODE)

- `mock`: 관제 없이 개발. `POST /dev/simulate`로 `/central_status`를 흉내 낸다.
- `gateway`: **관제가 노트북·집 네트워크에 있어 서버가 접속할 수 없을 때.** 관제 PC에서 `gateway/ros_gateway_client.py`를 실행하면 서버의 `/ws/gateway`로 먼저 연결하고, 그 한 줄로 토픽을 양방향 전달한다. 서버에서는 `ROS_MODE=gateway`, `GATEWAY_TOKEN=<비밀값>`을 설정하고 게이트웨이에도 같은 값을 준다.
  - 서버 → 관제: `/charging/request`, `/charging/cancel`, `/admin/command`, `/emergency_stop`. 연결이 끊긴 동안 쌓인 메시지(최대 500개)는 재연결 시 순서대로 전달된다.
  - 관제 → 서버: `/central_status`만 받는다. 메시지 형식은 `{"topic": "...", "data": "<JSON 문자열>"}`.
  - 게이트웨이 스크립트는 ROS 2 환경에서 아직 시험하지 않았다. 서버 쪽은 자동 테스트(`backend/tests/test_gateway.py`)가 있다.
- `rclpy`: 서버가 ROS 2 노드로 직접 붙는 방식. 아직 구현하지 않았다.

## 토픽 목록

| 토픽 | 방향 | 도메인 |
| --- | --- | --- |
| `/charging/request` | fastapi → central | 중앙 도메인 내부 |
| `/charging/cancel` | fastapi → central | 중앙 도메인 내부 |
| `/admin/command` | fastapi → central | 중앙 도메인 내부 |
| `/emergency_stop` | fastapi → central+vehicle | 0↔차량 도메인 브리지 |
| `/vehicle_task` | central → vehicle | 0↔차량 도메인 브리지 |
| `/vehicle_task_status` | vehicle → central | 0↔차량 도메인 브리지 |
| `/vehicle_command` | central → charger_sim | 중앙 도메인 내부 |
| `/charging_status` | charger_sim → central | 중앙 도메인 내부 |
| `/central_status` | central → fastapi | 중앙 도메인 내부 |

## 관제가 지켜야 할 동작

1. `/charging/request`를 받으면 `request_id`로 요청을 등록한다. **같은 `request_id`가 다시 오면 수정**(희망 시각·SOC 변경)으로 보고 덮어쓴다.
2. `/charging/cancel`을 받으면 해당 요청을 취소하고, `/central_status`의 `requests`에 `CANCELLED`로 알린다.
3. 요청 상태는 `REQUESTED → ACCEPTED → SCHEDULED → IN_PROGRESS → COMPLETED`(또는 `FAILED`, `CANCELLED`)이며 `/central_status.requests[]`로만 FastAPI에 전달한다. **`COMPLETED`는 차량이 `PARKED`가 된 시점**이다(충전 완료 시점이 아니다).
4. `desired_finish_at`은 사용자가 PARKED가 되길 원하는 시각이다. 대기 + 충전기 이동 + 충전 + 주차구역 이동이 이 시각 안에 들어오도록 스케줄한다.
5. 차량 상태는 `ARRIVED_AT_STATION, WAITING, ASSIGNED, MOVING_TO_CHARGER, ARRIVED_AT_CHARGER, CHARGING, CHARGE_DONE, MOVING_TO_PARKING, PARKED, FAULT`. 충전이 끝나면(CHARGE_DONE) 관제가 `MOVE_TO_PARKING` 작업을 만든다. 출차·호출 흐름은 없다.
6. `/central_status`는 1 Hz로 발행한다. 차량 `last_seen_at`이 5초 넘게 갱신되지 않으면 앱은 OFFLINE으로 표시한다.
7. `/central_status.tasks[]`에 진행 중·최근 작업을 반드시 넣는다. 차량의 `current_task_id`는 이 목록에 있는 작업이어야 한다.
8. `events[]`의 `event_id`는 관제가 매기는 고유 값이다. 같은 이벤트를 다시 보내도 FastAPI가 중복 저장하지 않는다.
9. `/emergency_stop`(`STOP`/`RELEASE`, `vehicle_id`=`ALL`이면 전체)을 받으면 모든 작업을 멈추고 `emergency_stop_active`를 `/central_status`에 반영한다.
10. `/admin/command`(cancel/retry/reassign, 사유 포함)는 관리자 웹의 수동 조치이다.
11. 충전기 점검 모드·출력 제한을 관제에 전달하는 방법은 **아직 정해지지 않았다**(열린 항목).
12. `zone_id`·`charger_id`는 FastAPI DB의 `parking_zones`·`chargers` id와 같아야 한다. 모르는 id는 null로 저장된다. DB 값은 관제의 `fleet_locations.yaml`과 맞춰야 한다.
13. `/charging/request`의 `parking_zone_id`는 사용자가 고른 주차 구역이다(PARKING 종류의 `zone_id`). 값이 있으면 `MOVE_TO_PARKING`의 목적지를 그 구역으로 하고, `null`이면 관제가 빈 구역을 배정한다. 그 구역이 막혔거나 쓸 수 없으면 요청을 실패시키지 말고 자동 배정으로 바꾼 뒤 `events[]`에 알려 주길 권장한다(대체 정책은 관제 담당과 합의). 같은 `request_id` 재발행으로 구역이 바뀔 수 있다.

## 메시지 예시

### `/charging/request`

```json
{
  "schema_version": 1,
  "request_id": "11111111-1111-4111-8111-111111111111",
  "vehicle_id": "CAR_01",
  "desired_finish_at": "2026-10-05T09:00:00Z",
  "target_soc": 80,
  "min_soc": 60,
  "battery_kwh": 60.0,
  "max_charge_kw": 11.0,
  "parking_zone_id": "PARKING_02"
}
```

### `/charging/cancel`

```json
{
  "schema_version": 1,
  "request_id": "11111111-1111-4111-8111-111111111111",
  "vehicle_id": "CAR_01",
  "requested_by": "user"
}
```

### `/admin/command`

```json
{
  "schema_version": 1,
  "command_id": "11111111-1111-4111-8111-111111111111",
  "action": "reassign",
  "vehicle_id": "CAR_01",
  "request_id": "11111111-1111-4111-8111-111111111111",
  "charger_id": "CHARGER_02",
  "reason": "점검",
  "admin_id": "11111111-1111-4111-8111-111111111111"
}
```

### `/emergency_stop`

```json
{
  "schema_version": 1,
  "action": "STOP",
  "vehicle_id": "ALL",
  "reason": "장애물",
  "issued_by": "11111111-1111-4111-8111-111111111111",
  "issued_at": "2026-10-05T09:00:00Z"
}
```

### `/vehicle_task`

```json
{
  "schema_version": 1,
  "task_id": "11111111-1111-4111-8111-111111111111",
  "request_id": "11111111-1111-4111-8111-111111111111",
  "vehicle_id": "CAR_01",
  "type": "MOVE_TO_PARKING",
  "target_id": "PARKING_02",
  "target_pose": {
    "x": 12.3,
    "y": 4.8,
    "yaw": 1.57
  }
}
```

### `/vehicle_task_status`

```json
{
  "schema_version": 1,
  "task_id": "11111111-1111-4111-8111-111111111111",
  "vehicle_id": "CAR_01",
  "status": "RUNNING",
  "progress": 0.4
}
```

### `/vehicle_command`

```json
{
  "schema_version": 1,
  "command": "START_CHARGING",
  "vehicle_id": "CAR_01",
  "charger_id": "CHARGER_01",
  "request_id": "11111111-1111-4111-8111-111111111111",
  "target_soc": 80
}
```

### `/charging_status`

```json
{
  "schema_version": 1,
  "vehicle_id": "CAR_01",
  "charger_id": "CHARGER_01",
  "soc": 55.5,
  "power_kw": 7.2,
  "charging": true,
  "done": false
}
```

### `/central_status`

```json
{
  "schema_version": 1,
  "at": "2026-10-05T09:00:00Z",
  "vehicles": [
    {
      "vehicle_id": "CAR_01",
      "state": "CHARGING",
      "soc": 55.0,
      "zone_id": null,
      "pose": null,
      "progress": null,
      "charger_id": null,
      "current_task_id": null,
      "estimated_completion": null,
      "last_seen_at": "2026-10-05T09:00:00Z"
    }
  ],
  "tasks": [
    {
      "task_id": "11111111-1111-4111-8111-111111111111",
      "request_id": null,
      "vehicle_id": "CAR_01",
      "type": "MOVE_TO_CHARGER",
      "status": "RUNNING",
      "target_id": "CHARGER_01",
      "target_pose": {
        "x": 1.0,
        "y": 2.0,
        "yaw": 0.1
      },
      "progress": 0.5,
      "error_message": null
    }
  ],
  "chargers": [
    {
      "charger_id": "CHARGER_01",
      "state": "IN_USE",
      "vehicle_id": "CAR_01",
      "power_kw": 7.2
    }
  ],
  "requests": [
    {
      "request_id": "11111111-1111-4111-8111-111111111111",
      "vehicle_id": "CAR_01",
      "status": "IN_PROGRESS",
      "planned_charger_id": null,
      "planned_start_at": null,
      "planned_parked_at": null,
      "reason": null
    }
  ],
  "events": [
    {
      "event_id": "e1",
      "type": "CHARGE_STARTED",
      "at": "2026-10-05T09:00:00Z",
      "vehicle_id": null,
      "charger_id": null,
      "request_id": null,
      "task_id": null,
      "payload": {}
    }
  ],
  "scheduler": {
    "queue_length": 0
  },
  "emergency_stop_active": false
}
```


## 실패·취소 사유 전달 (사용자 앱 연동)
- 요청 실패 사유는 `/central_status.tasks[].error_message`(FAILED 작업)에서 읽어 앱에 `last_request.failure_reason`으로 내려간다. 실패한 요청에 FAILED 작업과 `error_message`를 함께 보내 주면 앱에 그대로 표시된다(없으면 기본 문구).
- 취소는 `/charging/cancel` 발행 후 `requests[].status=CANCELLED`를 보내면 앱이 "취소 완료"로 바뀐다. 그 전까지는 "취소 처리 중".
- 차량 `last_seen_at`이 5초 넘게 갱신되지 않으면 앱은 "연결 끊김"으로 보여준다(마지막 값 유지).
