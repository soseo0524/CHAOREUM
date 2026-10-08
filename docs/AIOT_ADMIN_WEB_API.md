# AIOT 관리자 웹 연동 안내 (관리자 웹 담당자용)

관리자 웹은 별도 서버·DB 없이 **사용자 앱과 같은 백엔드(FastAPI)의 `/admin/*` API**만 호출한다. DB(Supabase)에 직접 접속하지 않는다.

```
[관리자 웹] ──HTTPS──▶ [백엔드 · Railway] ──▶ [Supabase DB]
                            ▲
[사용자 앱] ────────────────┤
[중앙관제(ROS) · 게이트웨이] ┘
```

## 1. 접속 정보

| 항목 | 값 |
| --- | --- |
| API 주소 | `https://chaoreum-production.up.railway.app` |
| API 문서(요청·응답 스키마, 직접 호출 가능) | `https://chaoreum-production.up.railway.app/docs` |
| OpenAPI JSON(코드 생성용) | `https://chaoreum-production.up.railway.app/openapi.json` |
| 실시간 | `wss://chaoreum-production.up.railway.app/ws/status` |
| 로그인 | Supabase Auth (사용자 앱과 같은 프로젝트). Supabase URL·publishable key는 백엔드 담당에게 받는다 |

## 2. 연결 전에 백엔드 쪽에서 해 줄 것

1. **CORS 허용**: 관리자 웹 주소(예: `https://admin.example.com`, 로컬 개발이면 `http://localhost:5173`)를 Railway 변수 `CORS_ORIGINS`에 쉼표로 구분해 넣는다. 안 넣으면 브라우저가 요청을 막는다.
2. **관리자 계정 지정**: 관리자 웹 담당자가 Supabase로 가입한 뒤, SQL Editor에서
   ```sql
   update profiles set app_role = 'admin' where id = '<auth.users의 id>';
   ```
   바꾼 권한은 **다시 로그인해야** 토큰에 반영된다.
3. Supabase Authentication > Hooks에서 `custom_access_token_hook`이 켜져 있어야 토큰에 `app_role`이 들어간다.

## 3. 인증

1. 관리자 웹에서 Supabase로 로그인한다(`supabase.auth.signInWithPassword` 등).
2. 받은 `access_token`을 모든 요청에 붙인다.
   ```
   Authorization: Bearer <access_token>
   ```
3. 서버는 토큰의 `app_role` 클레임으로 권한을 판단한다. `admin`이 아니면 `/admin/*`는 **403**, 토큰이 없거나 만료되면 **401**.
4. 관리자 계정으로 사용자 앱에 로그인하면 "웹사이트를 이용해 주세요" 안내 후 로그아웃된다(앱은 사용자 전용).

## 4. 공통 규칙

- 요청·응답은 JSON. 시각은 timezone이 있는 ISO 8601(UTC).
- **변경 요청(PATCH/POST)은 모두 `reason`(2~500자)이 필수**이고, 감사 로그(`audit_logs`)에 남는다.
- 알 수 없는 필드는 거부된다(422).
- 오류 응답 형식:
  ```json
  { "code": "ROS_ID_DUPLICATED", "message": "이미 다른 차량에 배정된 ROS 차량입니다.", "details": null }
  ```
  `message`는 한국어 사용자 문구라 그대로 보여 줘도 된다.

## 5. API 목록

| 메서드·경로 | 용도 | 본문 / 쿼리 |
| --- | --- | --- |
| `GET /admin/overview` | 대시보드 집계 | — |
| `GET /admin/vehicles` | 전체 차량(소유자·상태·현재 작업·활성 요청) | — |
| `PATCH /admin/vehicles/{vehicle_id}` | ROS 차량 ID 배정·해제 | `{ "ros_vehicle_id": "EV-01" \| null, "reason": "..." }` |
| `GET /admin/chargers` | 충전기 목록·상태 | — |
| `PATCH /admin/chargers/{charger_id}` | 점검 모드·출력 제한 | `{ "state": "MAINTENANCE" \| "AVAILABLE", "max_power_kw": 7.0, "reason": "..." }` (둘 중 하나 이상) |
| `GET /admin/queue` | 충전 대기열 | — |
| `POST /admin/queue` | 요청 수동 조치 | `{ "request_id": "...", "action": "cancel" \| "retry" \| "reassign", "charger_id": "CHARGER_02"(reassign만), "reason": "..." }` |
| `POST /admin/tasks/{task_id}/cancel` | 진행 중 작업 취소 | `{ "reason": "..." }` |
| `POST /admin/emergency-stop` | 비상 정지·해제 | `{ "action": "STOP" \| "RELEASE", "reason": "..." }` |
| `GET /admin/events` | 이벤트 로그(최신순) | `?type=...&limit=100` (최대 500) |
| `GET /admin/settings` | 시스템 설정 | — |
| `PATCH /admin/settings` | 설정 변경 | `{ "values": { "키": 값 }, "reason": "..." }` |

정확한 응답 필드는 `/docs`의 스키마(`AdminOverview`, `AdminVehicleOut`, `ChargerOut`, `QueueResponse`, `EventOut`, `SettingOut`)를 기준으로 한다.

### 주요 오류 코드

| 코드 | HTTP | 언제 |
| --- | --- | --- |
| `UNAUTHENTICATED` | 401 | 토큰 없음·만료 |
| `FORBIDDEN` | 403 | 관리자가 아님 |
| `NOT_FOUND` | 404 | 차량·충전기·요청·작업 없음 |
| `VALIDATION_ERROR` | 422 | 필드 오류, `reason` 누락, 바꿀 수 없는 설정 키 |
| `ROS_ID_DUPLICATED` | 409 | 그 ROS 차량 ID가 이미 다른 차량에 배정됨 |
| `HAS_ACTIVE_WORK` | 409 | 진행 중인 요청이 있어 배정 해제 불가 |
| `VEHICLE_NOT_ASSIGNED` | 422 | ROS 차량이 없는 요청에 조치 |

## 6. 상태 값

| 구분 | 값 |
| --- | --- |
| 차량 `state` | `ARRIVED_AT_STATION`, `WAITING`, `ASSIGNED`, `MOVING_TO_CHARGER`, `ARRIVED_AT_CHARGER`, `CHARGING`, `CHARGE_DONE`, `MOVING_TO_PARKING`, `PARKED`, `FAULT` |
| 오프라인 | `state`가 아니라 `online: false`(마지막 수신 5초 초과)로 표시 |
| 충전 요청 `status` | `REQUESTED`, `ACCEPTED`, `SCHEDULED`, `IN_PROGRESS`, `COMPLETED`(주차까지 끝남), `CANCEL_REQUESTED`, `CANCELLED`, `FAILED` |
| 작업 `status` | `CREATED`, `ACCEPTED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED` |
| 충전기 `state` | `AVAILABLE`, `IN_USE`, `MAINTENANCE`, `FAULT` |

ID 형식: 차량·요청·작업 id는 UUID, 충전기·구역 id는 문자열(`CHARGER_01`, `PARKING_05`), ROS 차량 ID는 `EV-01` 형식.

## 7. 실시간 상태 (WebSocket)

1. `wss://.../ws/status`에 연결하고 **5초 안에** 첫 메시지로 토큰을 보낸다(URL에 토큰을 넣지 않는다).
   ```json
   { "type": "auth", "token": "<access_token>" }
   ```
2. 성공하면 `{ "type": "auth_ok", "role": "admin" }`. 실패하면 서버가 코드 4401로 닫는다.
3. 연결 직후 `GET /admin/vehicles` 등으로 현재 상태를 한 번 받고, 이후 메시지로 갱신한다.
4. 관리자 연결은 **모든 차량**의 `{ "type": "vehicle_status", "data": {...} }`를 받는다.
5. 토큰이 만료되면 서버가 연결을 닫는다. 새 토큰으로 다시 연결하고 상태를 다시 조회한다.

## 8. 주차장 지도에 차량 표시 (관리자 대시보드)

관제 대시보드(관제 담당 `macaron8_AIOT-main/dashboard`)처럼 지도 위에 차량을 그리되, **데이터는 ROS가 아니라 이 서버에서** 받는다(로그인·기록이 적용되고 인터넷 어디서나 열린다).

- **차량 위치**: `GET /admin/vehicles`의 `pose`(`{x, y, yaw}`) + `zone_id`. 이후 `/ws/status`의 `vehicle_status.data.pose`로 갱신된다.
  - 좌표계는 관제 지도와 같은 `camera_map`: 원점은 출발 시 카메라 중심, **x = 전방, y = 왼쪽**(m), yaw는 rad(반시계 +).
  - 관제가 연결돼 상태를 보내기 전에는 `pose`가 `null`이다.
- **지도 그림·주차칸 좌표**: 관제 담당의 대시보드 폴더 파일을 그대로 쓴다(관제 담당에게 받기).
  - `map_final.png`(배경), `map_config.json`(그림 ↔ 좌표 변환), `slots_final_ros.json`(57칸 꼭짓점, 같은 좌표계), `obstacles_ros.json`(기둥)
  - 주차칸 번호 n ↔ 이 서버의 구역 id `PARKING_nn`(예: 5번 → `PARKING_05`).
- **차량을 움직이는 명령**(대시보드의 "Send to Charger" 같은 것)은 ROS로 직접 보내지 말고 이 서버의 `/admin/*`로 요청한다. 직접 보내면 사용자 앱과 기록에 반영되지 않는다.

## 9. 현재 제약 (알아 둘 것)

- `GET /admin/events`는 지금 `type`, `limit`만 필터로 받는다(차량·기간 필터는 아직 없음).
- 비상 정지·수동 조치(`cancel` 외의 `retry`, `reassign`)는 백엔드에 기록되지만, **현재 관제(macaron8)에는 이 기능이 없어 관제로 전달되지 않고 실제 차량에도 적용되지 않는다**(관제 담당과 협의 중). 요청 취소(`cancel`)는 전달된다.
- 주차 위치는 관제가 구역(A/B/C) 안에서 빈 칸을 고른다. 사용자가 고른 칸과 실제 주차 칸이 다를 수 있고, 실제 칸은 차량 `zone_id`로 확인한다.
- 사용자 관리, 통계, 지도 편집, CSV 내보내기, 결제는 MVP 범위 밖이라 API가 없다.
- 차량은 사용자가 등록하면 비어 있는 ROS 차량 ID(`EV-01~03`)가 **자동 배정**된다(`AUTO_ASSIGN_ROS_IDS`). 관리자 화면의 배정·해제는 그 값을 바꾸거나 자동 배정을 끈 경우에 쓴다.

## 10. 문의

API 추가·변경이 필요하면 백엔드 담당에게 요청한다. 계약의 기준 코드는 `backend/schemas/admin.py`, `backend/routers/admin.py`.
