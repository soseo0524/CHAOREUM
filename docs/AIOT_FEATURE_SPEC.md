# AIOT 기능 명세서 (사용자 앱 · 관리자 앱)

기준일: 2026-10-03 · 원본: Claude Docs "AIOT 기능 명세서" (이 파일은 그 내용을 옮긴 사본)

## 1. 개요

사용자 앱은 내 차량의 충전·주차 조건을 입력하고 진행 상황을 확인하는 앱이고, 관리자 앱은 충전소 전체 차량·충전기·주차 구역을 관제하고 개입하는 앱이다. 두 앱은 화면과 권한이 다르며 같은 백엔드를 쓴다. **제작 범위**: 사용자 앱(Expo)만 이 프로젝트에서 만든다. 관리자 앱은 다른 담당자가 웹사이트로 만들며, 이 프로젝트는 관리자 웹이 쓰는 `/admin/*` API와 WebSocket을 제공한다(5.2).

| 구분 | 사용자 앱 | 관리자 앱(웹, 타 담당자) |
| --- | --- | --- |
| 대상 | 차량 소유자·이용자 | 충전소 운영자 |
| 목적 | 충전 조건 입력, 상태 확인, 주차 위치 확인 | 전체 관제, 스케줄 감독, 이상 대응, 통계 |
| 시야 | 내 차량 1~N대 | 모든 차량·충전기·구역 |
| 인증 | Supabase Auth, role = user | Supabase Auth, role = admin |

**전제**

- Expo 프로젝트는 사용자 앱 하나만 만든다(라우트 그룹 `(auth)`, `(user)`). 관리자는 다른 담당자가 웹사이트로 만들고, 5.2의 관리자 API가 둘 사이의 계약이다. 권한 검사는 앱·웹의 화면 분기가 아니라 FastAPI가 한다.
- 차량 이동·충전 제어는 중앙관제(ROS 2)가 하고, 앱은 요청 입력과 상태 조회만 한다. 앱이 차량을 직접 제어하지 않는다.
- 초기 범위는 시뮬레이션과 축소 차량(동시 운영 3~4대, 충전기 1대 이상)이며, 실제 양산 차량 연동은 제외한다. 차량을 여러 대 동시에 운영하므로 ROS 2 도메인이 나뉘고 Domain Bridge가 필수다(5.4).
- 충전기와 차량 상태는 현재 구현된 `/central_status` 스냅샷(1 Hz)을 기준으로 한다.

## 2. 공통 기능

| ID | 기능 | 설명 | 비고 |
| --- | --- | --- | --- |
| C-01 | 로그인·회원가입 | 이메일+비밀번호. Supabase Auth가 JWT를 발급하고 앱이 저장 | 소셜 로그인은 후순위 |
| C-02 | 권한 분리 | JWT의 커스텀 claim app_role(user, admin)로 화면 그룹과 API를 구분. 관리자 API는 FastAPI가 매 요청 role 검사 | 앱 화면 숨김만으로 막지 않음 |
| C-03 | 푸시 알림 | 충전 시작, 충전 완료, 이동 완료, 이상 발생 시 Expo 푸시 | 관리자는 이상·경고 중심 |
| C-04 | 실시간 상태 | 차량·충전기 상태를 최초 조회 후 WebSocket(/ws/status)으로 갱신 | 연결 인증은 5.5. Supabase Realtime은 쓰지 않음 |
| C-05 | 세션 관리 | 토큰 만료 시 재로그인, 로그아웃 시 푸시 토큰 해제 | |
| C-06 | 오류·오프라인 표시 | 서버 연결 실패와 차량·충전기 OFFLINE을 구분해 표시. `last_seen_at`이 5초 이상 갱신되지 않으면 OFFLINE | 표시용 파생값, 5.1 참고 |

### 차량 상태 정의

충전 흐름의 상태 이름은 현재 구현(PIPELINE 문서 10.3)을 따르고, 앱에서는 아래 한국어 표기로 보여준다. 입차, 충전 완료, 주차 이동 상태는 앱 기능을 위해 추가한 상태다. 앱에서 보여주는 주 진행 순서는 **충전소로 이동 중 → 충전 중 → 충전 완료 → 주차구역으로 이동 중 → 주차 완료**다. 사용자 호출로 차량을 내보내는 '출차' 흐름은 쓰지 않는다.

| 시스템 상태 | 앱 표기 | 의미 |
| --- | --- | --- |
| ARRIVED_AT_STATION | 입차 완료 | 충전소에 진입해 정보 등록 대기 (추가) |
| WAITING | 충전 대기 | 대기 구역에서 순번 대기 |
| ASSIGNED | 충전 배정됨 | 충전기가 배정되고 이동 명령 발행 |
| MOVING_TO_CHARGER | 충전소로 이동 중 | 충전기를 향해 자율 이동 중 |
| ARRIVED_AT_CHARGER | 충전기 도착 | 도착 확인 후 충전 시작 대기 |
| CHARGING | 충전 중 | SOC 증가 중 |
| CHARGE_DONE | 충전 완료 | 목표 SOC 도달, 주차 구역 배정 대기 (추가) |
| MOVING_TO_PARKING | 주차구역으로 이동 중 | 충전 후 주차 구역으로 자율 이동 중 (추가) |
| PARKED | 주차 완료 | 주차 구역에 도착해 정차 |
| FAULT | 이상 | 충전 이상, 통신 두절, 비상 정지 (추가) |

차량 상태와 충전 요청 상태는 다른 개념이라 별도 enum으로 둔다. 충전 요청(`charge_requests.status`)은 REQUESTED → ACCEPTED → SCHEDULED → IN_PROGRESS → COMPLETED 이고, 취소는 CANCEL_REQUESTED → CANCELLED, 실패는 FAILED다. 충전 요청의 `COMPLETED`는 목표 SOC 달성 시점(CHARGE_DONE)이 아니라, 충전 후 주차 구역까지 이동해 `PARKED`에 도달한 시점으로 정의한다. 요청이 `IN_PROGRESS`인 동안 차량은 충전소로 이동, 충전, 주차구역 이동 단계를 거친다.

차량 이동 작업(task)의 상태는 별개로 `CREATED → ACCEPTED → RUNNING → COMPLETED`로 관리하고, 실패하면 `FAILED`, 취소되면 `CANCELLED`로 끝난다. 차량 상태와 task 상태는 서로 다른 개념이다. 구조는 충전 요청 1개에 이동 작업 여러 개가 붙고, 작업이 진행되면서 차량 실제 상태가 바뀐다. 세 enum(ChargeRequestStatus, VehicleState, TaskStatus)을 섞지 않고, 서버와 앱이 같은 상태 타입 정의를 쓴다(문자열을 여기저기 직접 쓰지 않음).

## 3. 사용자 앱

사용자 앱은 하단 탭 4개(홈, 충전 요청, 이력, 내 정보)로 구성하고, 화면 9개와 기능 항목을 정의한다. 우선순위 P1은 MVP 필수, P2는 베타, P3는 후순위다.

### 3.1 화면 목록

| ID | 화면 | 핵심 내용 | 우선순위 |
| --- | --- | --- | --- |
| U-01 | 로그인·회원가입 | 이메일 로그인, 가입, 비밀번호 재설정 | P1 |
| U-02 | 홈 | 내 차량 상태 카드, 현재 SOC, 예상 충전 완료시간 | P1 |
| U-03 | 차량 등록·관리 | 차량번호, 모델, 배터리 용량, 충전 가능 전력 | P1 |
| U-04 | 충전 요청 | 희망 완료 시각, 목표 SOC, 최소 필요 SOC | P1 |
| U-05 | 실시간 진행 상태 | 대기 순번, 이동 중 위치, 충전 진행률 | P1 |
| U-06 | 주차 위치 | 차량 주차 구역, 주차 완료 여부 | P1 |
| U-07 | 알림 함 | 상태 변경·이상 알림 목록 | P2 |
| U-08 | 충전 이력 | 과거 충전 시간, 충전량, 대기시간 | P2 |
| U-09 | 내 정보·동의 | 프로필, 알림 설정, 무인 이동 권한 위임 동의, 탈퇴 | P1 |

### 3.2 화면별 기능 명세

**U-01 로그인·회원가입**

- 이메일과 비밀번호(8자 이상)로 가입하고, 이메일 인증을 거친다.
- 로그인 성공 시 JWT를 저장하고 role이 user면 홈으로 보낸다. admin이면 "관리자는 웹사이트에서 이용해 주세요"를 안내하고 로그아웃한다.
- 실패 시 원인을 구분해 보여준다(비밀번호 오류, 미인증, 네트워크).

**U-02 홈**

- 대표 차량의 상태(2장 상태 표기), SOC 게이지, 예상 충전 완료시간, 주차 위치를 한 카드에 보여준다.
- 차량이 여러 대면 카드를 좌우로 넘기고, 충전 요청이 없으면 "충전 요청" 버튼을 노출한다.
- 상태는 실시간 갱신하고, 서버 연결이 끊기면 마지막 갱신 시각을 표시한다.

**U-03 차량 등록·관리**

- 차량번호, 모델명, 배터리 용량(kWh), 최대 충전 전력(kW)을 등록·수정·삭제한다.
- 등록 직후에는 ROS 차량이 배정되지 않아 '배정 대기'로 표시하고, 관리자가 ROS 차량을 배정하면 충전 요청을 할 수 있다.
- 차량번호는 중복 등록을 막는다. 충전·이동 중인 차량은 삭제할 수 없다.

**U-04 충전 요청**

- 입력값: 희망 완료 시각(충전을 끝내고 주차까지 마치길 원하는 시각, 현재보다 미래), 목표 SOC(%), 최소 필요 SOC(%), 주차 구역(선택, 비우면 자동 배정).
- 검증: 최소 필요 SOC ≤ 목표 SOC ≤ 100, 현재 SOC보다 목표 SOC가 낮으면 경고.
- 제출 시 예상 충전 소요시간과 희망 완료 시각 충족 가능성을 미리 보여주고, 충족이 어려우면 시각을 늦추거나 목표 충전량을 낮추도록 안내한다.
- 요청 후에도 희망 완료 시각·목표 SOC를 변경할 수 있고, 변경은 스케줄러가 다시 계산한다. 충전이 시작된 뒤에는 취소해도 즉시 동작하지 않고 안전한 지점에서 처리된다.

**U-05 실시간 진행 상태**

- 단계 표시줄(대기, 배정, 충전소로 이동, 도착, 충전, 충전 완료, 주차구역으로 이동, 주차 완료)에 현재 단계를 강조한다.
- 대기 중에는 대기 순번과 예상 대기시간, 충전 중에는 SOC 진행률과 예상 완료시간을 보여준다.
- 이동 중에는 진행률(progress)을 표시하고 지도 위치는 P2다.
- 스케줄이 바뀔 때(순서 변경) 이유를 한 줄로 알려준다.

**U-06 주차 위치**

- 주차 구역 이름과 위치를 보여준다(좌표는 `fleet_locations.yaml` 기준).
- 충전이 끝나면 '주차구역으로 이동 중'을 거쳐 '주차 완료'로 바뀌고, 도착 시 알림을 보낸다. 사용자가 차량을 호출하거나 인수 완료를 누르는 단계는 없다.

**U-07 알림 함**

- 충전 시작, 충전 완료, 주차 완료, 이상 발생, 희망 완료 시각 임박을 목록으로 보관하고 읽음 표시를 한다.

**U-08 충전 이력**

- 날짜순 목록: 시작·종료 시각, 시작 SOC→종료 SOC, 대기시간. 상세 화면은 이벤트 타임라인을 보여준다.

**U-09 내 정보·동의**

- 프로필 수정, 푸시 알림 켜기/끄기, 로그아웃, 회원 탈퇴(개인정보 삭제 요청). 탈퇴는 `DELETE /me`로 처리하며, 활성 충전 요청·작업이 있으면 거절하고 없을 때만 진행한다. 순서는 푸시 토큰 삭제, 동의 철회 처리, 차량 soft delete와 소유 관계 해제(`owner_id = NULL`), 프로필 개인정보 삭제, `auth.users` 삭제다. 충전 이력과 감사 로그는 개인정보 없이 남긴다.
- **무인 이동 권한 위임 동의**: 서비스 제공자가 차량을 이동·충전할 권한을 받는 절차다. 동의 이력(시각, 버전)을 저장하고, 동의 없이는 충전 요청을 진행할 수 없다.

### 3.x 화면 상태 ↔ 백엔드 매핑 (v4)

`GET /me/status`(와 WS `vehicle_status`)의 각 차량에 **`home_state`** 가 들어 있고, 앱은 이 값 하나로 홈 화면을 고른다. 차량이 하나도 없으면 `vehicles=[]` + `empty_reason="NO_VEHICLE"`.

| home_state | 화면 | 판정 조건(위에서부터 먼저 맞는 것) |
|---|---|---|
| (vehicles 비어 있음) | 2-6 차량 없음 | `empty_reason = NO_VEHICLE` |
| WAITING_ASSIGNMENT | 2-6b 배정 대기 | `assigned=false` |
| NO_DATA | 2-9 불러오는 중 | 배정됐지만 상태를 한 번도 못 받음(`state=null`). 로딩이 길어지면 앱이 2-7로 전환 |
| CANCELING | 3-4·3-5 취소 접수·처리 중 | 활성 요청이 `CANCEL_REQUESTED` |
| FAULT | 2-8 차량 이상 | `state=FAULT` |
| VEHICLE_OFFLINE | 2-11 연결 끊김 | `online=false`(마지막 수신 5초 초과). 마지막 값은 그대로, `last_seen_at`으로 "n분 전" |
| QUEUED | 2-0b 대기 | 활성 요청 있음 + 아직 이동 전(`REQUESTED/ACCEPTED/SCHEDULED`) |
| MOVING_TO_CHARGER / CHARGING / CHARGE_DONE / MOVING_TO_PARKING / PARKED | 1~5단계 | 활성 요청 + 차량 상태 |
| REQUEST_FAILED | 2-5 요청 실패 | 활성 요청 없음 + 24시간 내 직전 요청이 `FAILED`. `last_request.failure_reason`(관제 작업의 `error_message`, 없으면 기본 문구) |
| CANCELLED | 3-6 취소 완료 | 활성 요청 없음 + 24시간 내 직전 요청이 `CANCELLED` |
| PARKED | 6 완료 유지 | 활성 요청 없음 + 직전 요청 `COMPLETED` + 차량 `PARKED` |
| NO_REQUEST | 2-0 요청 없음 | 위에 해당 없음. `last_session`(마지막 충전 요약)으로 "지난 충전" 표시 |

2-10(값 일부 없음)은 별도 상태가 아니라 위 상태 중 하나에서 값이 `null`인 경우다(아래 표시 규칙). 2-7(앱↔서버 연결 실패)은 서버가 알 수 없으므로 앱이 요청 실패·타임아웃으로 직접 판단한다.

새 요청을 보내면 `last_request`가 비어 결과 화면(실패·취소)은 자동으로 사라진다. 결과 화면은 24시간 뒤에도 사라진다.

### 값이 없을 때 표시 규칙

| 값 | 필드 | 규칙 |
|---|---|---|
| 예상 완료시간 | `eta.state` | `KNOWN`=시각 표시 / `CALCULATING`=**계산 중** (진행 중인데 아직 값 없음) / `NONE`=**—** (완료·오프라인·요청 없음·미배정·결함) |
| 배터리 | `soc=null` | **—** |
| 충전량·금액 | `charge=null` | 충전 전에는 칸을 숨기고, 충전 중·완료·주차 이동·주차 완료에서만 표시 |
| 위치(자리) | `zone_id=null` | **—** |
| 대기 순번 | `queue_position=null` | 숨김(대기 상태가 아닐 때) |
| 마지막 수신 | `last_seen_at=null` | **—** (한 번도 못 받음) |
| 마지막 충전 | `last_session=null` | 칸 숨김 |

### 그 밖에 이번에 맞춘 것
- 충전 단가는 `CHARGE_UNIT_PRICE_WON`(기본 300원/kWh), 세션 시작 시점 단가로 고정. 금액 = round(충전량 × 단가).
- 요청 실패 푸시/알림 본문에 실패 사유가 들어간다.
- 내 정보·차량 관리·충전 이력은 기존 API(`/me`, `/vehicles`, `/me/sessions`)로 이미 제공.
- 아직 실제 Supabase·ROS2 연결로 검증한 것은 아님(SQLite 테스트 49개 통과).

### 3.y 주차 지도 API (구역 → 자리 2단계)

주차 위치는 두 단계로 고른다. 모바일 화면에 지하 주차장 전체를 한 번에 그릴 수 없어서, 전체 지도에서 구역을 먼저 정하고 구역 안에서 자리를 고른다.

| 화면 | API | 내용 |
|---|---|---|
| 02.02 전체 지도 | `GET /parking-zones/areas` | 구역 A(1~7번)·B(8~14번)·C(15~21번)별 `free_count`(빈자리 수), `state`(OPEN/FULL), `has_mine`, 구역 카드의 미니 현황용 `seats[]`. 확대·축소·이동은 앱이 처리 |
| 02.03 구역 안 맵 | `GET /parking-zones/areas/{area_id}` | 자리별 `state`(TAKEN=차 있음, FREE=빈자리, MINE=내 자리·고르는 중), `row`/`col`(윗줄 4칸, 아랫줄 3칸+입구 칸), `entrance` |
| 02-A.02 이미 선정된 자리 | 같은 API + `?selected=PARKING_03` | 그 자리가 이미 선정됐으면 `selected_ok=false`(그 자리는 TAKEN). 요청 접수 때도 409 `PARKING_ZONE_UNAVAILABLE` |
| 02-A.03 가득 찬 구역 | 위 두 API의 `state=FULL` | 앱이 "가득 찬 구역이에요"로 버튼을 막는다 |

- 자리 번호 n = 주차 구역 `PARKING_nn`(capacity 1). 고른 자리의 `zone_id`를 충전 요청의 `parking_zone_id`로 보낸다.
- 옛 1인칭 줄 방식 `GET /parking-zones/map`은 삭제했다.
- 구역 묶음(A·B·C)은 서버 코드(`schemas/parking_map.py`의 `AREAS`)에 있고 DB에는 없다. 구역 수·범위를 바꾸려면 이 값만 고치면 된다.

## 4. 관리자 앱 (웹, 다른 담당자가 제작)

> 이 장은 관리자 웹 담당자에게 넘기는 화면·기능 요구사항이다. Expo 앱의 구현 범위가 아니며, 모바일 전제 표현은 웹(데스크톱 브라우저)에 맞게 조정해도 된다. 이 프로젝트의 책임은 5.2의 관리자 API와 WebSocket이다.

관리자 앱은 현재 구현된 웹 대시보드의 기능(상태·이벤트 표시)을 모바일로 옮기고, 수동 개입과 설정을 더한다. 화면 12개를 정의한다. 태블릿 사용이 많으면 표와 지도 화면은 태블릿 레이아웃을 별도로 고려한다.

### 4.1 화면 목록

| ID | 화면 | 핵심 내용 | 우선순위 |
| --- | --- | --- | --- |
| A-01 | 관리자 로그인 | role = admin만 진입, 실패 횟수 제한 | P1 |
| A-02 | 대시보드 | 충전기 이용률, 대기 차량 수, 평균 대기시간, 활성 알림 | P1 |
| A-03 | 실시간 관제 맵 | 차량 위치, 충전기·주차 구역, 이동 경로 | P2 |
| A-04 | 차량 관리 | 차량 목록·상세, 작업 취소·재시도 | P1 |
| A-05 | 충전기 관리 | 충전기 상태, 점검 모드, 출력 설정 | P1 |
| A-06 | 충전 스케줄 큐 | 우선순위 순서, 배정 이유, 수동 재배정 | P1 |
| A-07 | 주차 구역 관리 | 구역 정의, 점유 상태, 좌표 편집 | P2 |
| A-08 | 이벤트·이력 로그 | 모든 이벤트 검색·필터, 내보내기 | P1 |
| A-09 | 이상·안전 | 이상 알림 확인, 비상 정지·해제 | P1 |
| A-10 | 사용자 관리 | 계정 목록, 권한 변경, 정지 | P2 |
| A-11 | 통계·성능 지표 | 이용률, 대기시간, SOC 달성률, 순환 성공률 | P2 |
| A-12 | 시스템 설정 | 스케줄러 모드, Qwen 연결, 우선순위 가중치 | P2 |

### 4.2 화면별 기능 명세

**A-01 관리자 로그인**

- 관리자 계정은 가입 화면 없이 운영자가 부여한다(사용자 앱에서 role을 스스로 선택할 수 없음).
- 연속 실패 5회 시 일정 시간 잠금.

**A-02 대시보드**

- 카드: 충전기 사용 중/전체, 대기 차량 수, 평균 대기시간, 활성 이상 건수.
- 차량 목록: ID, 상태, SOC → 목표 SOC, 완료 예정 시각. 완료 임박 차량을 강조한다.
- 최근 이벤트 10개를 실시간으로 보여준다(`/central_status`의 이벤트 이력).

**A-03 실시간 관제 맵**

- 중앙관제의 목표 좌표(map frame, x·y·yaw)를 화면 좌표로 변환해 차량·충전기·주차 구역을 그린다.
- 차량 탭으로 상세(작업 ID, 목표, 진행률)를 연다.

**A-04 차량 관리**

- 목록은 상태·소유자·차량번호로 검색·필터한다.
- 상세: 작업 이력(`ACCEPTED` → `MOVING_TO_CHARGER` → `ARRIVED_AT_CHARGER` → `CHARGING` → `CHARGE_DONE` → `MOVING_TO_PARKING` → `PARKED`), 충전 이력, 소유자 연락 정보.
- 수동 조치: 작업 취소, 재시도, 재배정만 허용한다. 임의 상태 변경은 운영 중 상태머신을 깨뜨릴 수 있어 MVP에서 제외하고 개발·복구 모드 전용으로 제한한다. 모든 수동 조치는 사유를 입력받고 감사 로그에 기록한다.

**A-05 충전기 관리**

- 충전기별 상태(`AVAILABLE`, 사용 중, 점검, 고장), 출력(kW), 현재 배정 차량.
- 점검 모드를 켜면 스케줄러가 그 충전기를 배정에서 제외한다. 사용 중인 충전기는 충전이 끝난 뒤에 점검으로 전환한다.
- 현재 구현은 충전기 1대(`CHARGER_01`)라, 다중 충전기는 데이터 모델만 대비한다.

**A-06 충전 스케줄 큐**

- 대기 차량을 우선순위 순으로 보여주고 각 차량의 결정 근거(`LOW_SLACK_TIME` 등 reason)를 표시한다.
- 결정 출처 배지: Qwen(LLM) 또는 규칙 기반 fallback(`RULE_FALLBACK`).
- 수동 재배정: 대상 차량을 선택해 다음 충전 차례로 지정한다(사유 필수, 다시 자동 모드로 복귀 옵션).

**A-07 주차 구역 관리**

- 구역(대기, 충전, 주차)별 용량과 현재 점유 차량을 보여준다.
- 구역 좌표를 수정하면 중앙관제 설정에 반영하는 방식은 열린 질문이다.

**A-08 이벤트·이력 로그**

- 이벤트를 시간·종류·차량·충전기 기준으로 검색하고 CSV로 내보낸다(CSV는 MVP 제외).
- 현재 `~/.ros/aiot_charging_history.jsonl`에 쓰는 이벤트를 DB로도 저장해야 앱에서 조회할 수 있다.

**A-09 이상·안전**

- 이상 목록: 발생 시각, 대상, 심각도, 확인 여부. 확인(ack)과 메모를 남긴다.
- 비상 정지 버튼: 한 번 더 확인하는 대화상자 후 모든 차량에 정지 명령을 보낸다. 해제는 별도로 현장 안전 확인 체크를 거친다.
- 현재 중앙관제에 비상 정지 토픽이 없으므로 신규 구현이 필요하다.

**A-10 사용자 관리**

- 계정 목록·검색, 소유 차량, 동의 이력 조회. 계정 정지·복구, 관리자 권한 부여(최상위 관리자만).

**A-11 통계·성능 지표**

- 기간(일/주/월)별 충전기 평균 이용률, 차량 평균 대기시간, 충전 완료 차량의 충전 구역 점유시간, 희망 완료 시각 만족률, 목표 SOC 달성률, 단위 시간당 충전 완료 차량 수, 순환 성공률.

**A-12 시스템 설정**

- 스케줄러 모드 전환(LLM / RULE), Qwen URL·timeout, 우선순위 가중치(완료 임박도, SOC 부족분, 대기시간, 긴급 여부).
- 현재 Qwen URL과 timeout이 코드에 고정되어 있어 파라미터화가 선행되어야 한다. 모든 설정 변경은 변경 이력을 남긴다.

## 5. 데이터 모델과 API 개요

앱은 FastAPI의 REST API와 WebSocket만 사용하며, Supabase DB 및 ROS 2에는 직접 접근하지 않는다. 데이터는 Supabase PostgreSQL에 저장한다. 아래는 명세 단계의 초안이며 스키마 확정은 구현 단계에서 한다.

### 5.1 주요 테이블

| 테이블 | 주요 필드 | 용도 |
| --- | --- | --- |
| profiles | id(auth.users FK), name, phone, app_role(user/admin), status(ACTIVE/SUSPENDED), is_super_admin, notification_prefs(jsonb), created_at, updated_at | 사용자 프로필과 권한, 알림 종류별 켜기/끄기 |
| vehicles | id(UUID), ros_vehicle_id(TEXT, nullable, 예 CAR_01), owner_id(nullable), plate_no, model, battery_kwh, max_charge_kw, created_at, updated_at, deleted_at | 등록 차량(soft delete, ROS 차량은 관리자가 나중에 배정) |
| vehicle_states | vehicle_id(PK/FK), state, soc, zone_id, pose_x, pose_y, pose_yaw, progress, charger_id, current_task_id, estimated_completion, last_seen_at, updated_at | 차량 실시간 상태(추가) |
| charge_requests | id(UUID), vehicle_id, desired_finish_at, target_soc, min_soc, parking_zone_id(nullable, FK parking_zones, null=자동 배정), status, created_at, updated_at, cancel_requested_at, completed_at | 충전 요청과 조건, 요청 상태 |
| vehicle_tasks | id(UUID), request_id, vehicle_id, type(MOVE_TO_CHARGER/MOVE_TO_PARKING), status, target_id, target_pose_x·y·yaw, progress, error_message, created_at, accepted_at, started_at, completed_at, updated_at | 차량 이동 작업(추가) |
| charge_sessions | id(UUID), request_id, charger_id, start_at, end_at, start_soc, end_soc, energy_kwh, created_at | 충전 이력 |
| chargers | id(TEXT, 예 CHARGER_01), name, max_power_kw, created_at, updated_at | 충전기 정의(관리자가 등록) |
| charger_states | charger_id(PK/FK), state(AVAILABLE/IN_USE/MAINTENANCE/FAULT), output_kw, assigned_vehicle_id, maintenance, last_seen_at, updated_at | 충전기 실시간 상태(추가) |
| parking_zones | id(TEXT, 예 PARKING_02), name, kind(WAITING/CHARGING/PARKING), capacity, pose_x, pose_y, pose_yaw | 대기·충전·주차 구역 |
| events | id, at, type, vehicle_id, charger_id, request_id, task_id, payload(jsonb) | 중앙관제 이벤트 저장 |
| notifications | id, user_id, type, title, body, data(jsonb), read_at, created_at | 사용자 알림 |
| push_tokens | id, user_id, expo_push_token(unique), platform, enabled, created_at, updated_at, last_seen_at | Expo 푸시 토큰(추가) |
| consents | id, user_id, version, agreed_at, revoked_at | 무인 이동 권한 위임 동의와 철회 |
| audit_logs | id, admin_id, action, reason(NOT NULL), entity_type, entity_id, before_data, after_data, at | 관리자 수동 조치 기록 |
| settings | key, value(jsonb), updated_by, updated_at | 스케줄러 모드 등 설정 |

`vehicle_states`와 `charger_states`는 중앙관제의 `/central_status`를 받을 때마다 upsert한다. 그러면 `GET /me/status`와 `GET /admin/vehicles`가 이벤트 로그를 계산하지 않고 현재 상태를 바로 읽는다. 정의(chargers)와 실시간 상태(charger_states)를 나눠 관리자 설정과 ROS 런타임 데이터가 섞이지 않게 한다.

**제약과 규칙**

- DDL은 `backend/db/schema.sql`에 둔다(초기 기준 SQL, 이후 Alembic으로 이관). 충전기·구역 id는 ROS와 같은 TEXT(`CHARGER_01`, `PARKING_02` 등)이고, 차량·요청·작업·세션 id는 UUID다. 차량의 ROS 식별자(`CAR_01` 등)는 `vehicles.ros_vehicle_id`에 따로 두며, 삭제되지 않은 차량끼리만 유일하다. ROS 메시지의 `vehicle_id`는 `ros_vehicle_id` 값이고, `request_id`·`task_id`에는 UUID 문자열을 담는다. FastAPI가 둘을 변환한다.
- 사용자는 ROS 차량을 직접 고르지 않는다. 차량을 먼저 등록하면 관리자가 `CAR_01~04` 중 하나를 배정하고, 배정 전에는 충전 요청을 만들 수 없다(`ros_vehicle_id`가 NULL).
- `vehicles.owner_id`는 nullable이고 `on delete set null`이다. 회원 탈퇴가 충전 이력·이벤트·감사 로그를 지우지 않게 하기 위해서다.
- 차량 삭제는 `deleted_at`을 쓰는 soft delete다. 차량번호 중복은 삭제되지 않은 차량끼리만 부분 유니크 인덱스로 막는다.
- `charge_requests.completed_at`은 PARKED 도달 시각이다. 충전 요청 하나에 `vehicle_tasks`가 여러 개 붙고(MOVE_TO_CHARGER, MOVE_TO_PARKING), 이벤트에는 `request_id`와 `task_id`를 남겨 어느 요청의 어느 작업에서 문제가 났는지 추적한다.
- 모든 public 테이블은 RLS를 켜되 앱용 policy는 만들지 않는다. 앱은 DB에 직접 접근하지 않고, FastAPI만 서버의 service role로 접근한다.
- 권한은 JWT의 커스텀 claim `app_role`(user/admin)로 구분한다. Supabase 기본 `role` claim은 PostgreSQL 역할이라 쓰지 않으며, 명세 안의 "role"은 모두 `app_role`을 뜻한다. `app_role`은 Supabase Custom Access Token Hook으로 JWT에 넣는다.
- `charge_requests.desired_finish_at`은 충전 완료 시각이 아니라 **PARKED 상태까지 도달하기를 희망하는 시각**이다. 스케줄러는 대기 + 충전기로 이동 + 충전 + 주차구역 이동 ≤ `desired_finish_at`으로 계산한다.
- `vehicle_states`(vehicle_id)와 `charger_states`(charger_id)는 각각 `vehicles`, `chargers`와 1:1인 런타임 상태 테이블이다. 키는 PK이면서 FK다.
- 차량 하나에는 활성 충전 요청이 1개만 허용한다. 활성 상태는 REQUESTED, ACCEPTED, SCHEDULED, IN_PROGRESS, CANCEL_REQUESTED이며, `charge_requests(vehicle_id)`에 이 상태일 때만 적용되는 부분 유니크 인덱스를 둔다.
- 요청과 세션은 1:N이다. `charge_sessions.request_id`가 요청을 가리키고, 충전을 나눠 진행하면 한 요청에 세션이 여러 개 생길 수 있다.
- `created_at`, `updated_at`, `cancel_requested_at`은 스케줄링·감사·통계에서 쓴다.
- OFFLINE 판정: `last_seen_at`이 5초 이상 갱신되지 않으면 OFFLINE으로 본다(`/central_status` 1 Hz 기준). 화면 표시용 파생값이며 `state` 컬럼에는 저장하지 않는다. 차량과 충전기에 같은 기준을 쓴다.

### 5.2 API 목록

| 영역 | 메서드·경로 | 기능 | 권한 |
| --- | --- | --- | --- |
| 사용자 | GET/POST/PATCH/DELETE /vehicles | 차량 등록·조회·수정·삭제 | user |
| 사용자 | POST /charge-requests | 충전 요청 생성 | user |
| 사용자 | PATCH /charge-requests/{id} | 희망 완료 시각·목표 SOC 변경, 취소 | user |
| 사용자 | GET /me/status | 내 차량 실시간 상태 | user |
| 사용자 | GET /parking-zones | 주차 구역 목록과 남은 자리(구역 선택 화면) | user |
| 사용자 | GET /me/sessions, /me/notifications | 충전 이력(충전 시작·종료 SOC, 충전량), 알림함 | user |
| 사용자 | POST /me/notifications/{id}/read | 알림 읽음 처리 | user |
| 사용자 | GET/PATCH /me/notification-settings | 알림 4종(충전 완료·주차 완료·이상·대기 순번 변경) 켜기/끄기 | user |
| 사용자 | POST/DELETE /me/push-tokens | Expo 푸시 토큰 등록·해제(로그아웃 시 해제) | user |
| 사용자 | POST /consents | 위임 동의 저장 | user |
| 사용자 | DELETE /me | 회원 탈퇴(절차는 U-09) | user |
| 관리자 | GET /admin/overview | 대시보드 집계(관리자 웹이 호출. 브라우저 호출용 CORS 허용 출처는 환경변수 `CORS_ORIGINS`) | admin |
| 관리자 | GET /admin/vehicles, /admin/chargers | 전체 차량·충전기 조회 | admin |
| 관리자 | POST /admin/tasks/{id}/cancel | 작업 취소(사유 필수) | admin |
| 관리자 | PATCH /admin/vehicles/{id} | ROS 차량(`ros_vehicle_id`) 배정·해제 | admin |
| 관리자 | PATCH /admin/chargers/{id} | 점검 모드·출력 | admin |
| 관리자 | GET/POST /admin/queue | 스케줄 큐 조회·수동 재배정 | admin |
| 관리자 | GET /admin/events | 이벤트 검색·내보내기 | admin |
| 관리자 | POST /admin/emergency-stop | 비상 정지 | admin |
| 관리자 | GET/PATCH /admin/settings | 시스템 설정 | admin |
| 실시간 | WS /ws/status | 상태 변경분 스트림 (JWT 인증은 5.5) | user/admin |

- **API 스키마 결정**(코드는 `backend/schemas/`): `POST /charge-requests`는 `dry_run=true`이면 저장·발행 없이 가능 여부(feasibility)만 계산해 요청 화면 미리보기에 쓴다. `dry_run=false`에서 희망 완료 시각이 불가능하면 저장하지 않고 422 `DEADLINE_INFEASIBLE`을 돌려주며 가장 빠른 가능 시각을 담는다. 검사 순서는 차량 배정(422 `VEHICLE_NOT_ASSIGNED`), 위임 동의(403 `CONSENT_REQUIRED`), 진행 중 요청(409 `ACTIVE_REQUEST_EXISTS`), 시각 가능 여부 순이다. `PATCH /charge-requests/{id}`는 수정과 취소를 동시에 보낼 수 없고, 수정은 REQUESTED·ACCEPTED·SCHEDULED에서만 된다(그 밖은 409 `REQUEST_NOT_MODIFIABLE`). `GET /me/status`는 차량이 여러 대일 수 있어 `vehicles` 배열로 돌려주며 사용자 응답에는 `ros_vehicle_id`를 넣지 않고 `assigned`만 둔다. 5단계 진행 번호는 ASSIGNED·MOVING_TO_CHARGER·ARRIVED_AT_CHARGER=1, CHARGING=2, CHARGE_DONE=3, MOVING_TO_PARKING=4, PARKED=5이고 ARRIVED_AT_STATION·WAITING·FAULT는 단계가 없다. 사용자는 충전 요청 때 `parking_zone_id`로 주차 구역을 직접 고를 수 있고(비우면 관제가 자동 배정), 고른 구역은 PARKING 종류여야 한다. `GET /parking-zones`가 구역별 남은 자리(capacity − 주차 중 − 그 구역을 고른 진행 중 요청)를 돌려주며, 이미 선정된 구역을 고르면 409 `PARKING_ZONE_UNAVAILABLE`이다. 수정은 REQUESTED·ACCEPTED·SCHEDULED에서 구역 변경도 가능하다. 관리자 변경 API는 모두 `reason`이 필수이며 감사 로그에 남긴다.

### 5.3 중앙관제(ROS 2) 연동

- 중앙관제(ROS 2 노드, 스케줄러, Qwen)는 다른 담당자가 만들어 붙인다. 이 프로젝트와의 계약은 5.4의 토픽 JSON(`backend/ros_schemas/`)이며, 관제 담당자용 요약은 `docs/AIOT_CENTRAL_INTERFACE.md`이다. 관제가 붙기 전에는 개발용 시뮬레이터(`ROS_MODE=mock`, `POST /dev/simulate`)로 앱을 개발한다.
- 제어 경로: 앱 → FastAPI → ROS 2. 상태 경로: ROS 2 → FastAPI → PostgreSQL·WebSocket → 앱. 앱은 DB나 ROS를 직접 다루지 않는다.
- 충전 요청(`POST /charge-requests`): FastAPI가 DB에 저장한 뒤 `/charging/request` Topic으로 중앙관제에 발행한다(5.4). 중앙관제가 DB를 주기적으로 읽는 방식(폴링)은 쓰지 않는다. 중앙관제가 DB 상태에 의존하게 되기 때문이다.
- 요청의 수명주기(REQUESTED → ACCEPTED → SCHEDULED → IN_PROGRESS → COMPLETED)는 `request_id`로 추적한다. ROS 2 Action은 쓰지 않는다(5.4).
- 상태 반영: FastAPI의 ROS 노드가 `/central_status`(1 Hz)를 구독해 내부 캐시에 두고 DB에 upsert하면서 WebSocket으로 방송한다. 앱은 최초 진입 시 `GET /me/status`, 이후 `/ws/status`로 변경분을 받는다. Supabase Realtime은 단계만 늘려서 쓰지 않는다.
- 충전이 끝나면(CHARGE_DONE) 스케줄러가 주차 구역 이동 작업(`/vehicle_task`, type=MOVE_TO_PARKING)을 만든다. 차량 상태는 MOVING_TO_CHARGER → ARRIVED_AT_CHARGER → CHARGING → CHARGE_DONE → MOVING_TO_PARKING → PARKED 순으로 바뀌며, 사용자 호출이나 인수 확인은 없다.
- 연결 방식(`ROS_MODE`): `mock`(개발용), `gateway`(관제가 노트북 등 서버가 접속할 수 없는 곳에 있을 때: 관제 PC의 게이트웨이가 서버 `/ws/gateway`로 먼저 연결해 토픽을 양방향 전달, 끊긴 동안의 메시지는 최대 500개 보관 후 재전송, 비밀값 `GATEWAY_TOKEN`), `rclpy`(서버가 ROS 노드로 직접 연결, 미구현). 게이트웨이 참고 구현은 `gateway/ros_gateway_client.py`.
- 알림 생성: 상태 전이로 서버가 만든다. 충전 완료·주차 완료·차량 이상(FAULT)·요청 실패·대기 순번 앞당김(내 앞 요청이 취소·시작되어 순번이 줄 때)이다. 알림함에는 항상 저장하고, 푸시와 WebSocket 방송은 알림 설정(5.1 `notification_prefs`)이 켜진 종류만 보낸다. 푸시 전송은 `PUSH_MODE=expo`일 때만 실제로 나간다(기본 `mock`).
- 충전 이력: 차량이 CHARGING에 들어가면 충전 세션을 열고 벗어나면 닫는다. 충전량(kWh)은 SOC 증가분 × 배터리 용량으로 계산한다.
- 대기 순번: 접수 순서(REQUESTED·ACCEPTED·SCHEDULED)로 매기고, 예상 대기시간은 앞선 대수 × 평균 소요 시간(임시값 12분, 스케줄러 연동 시 교체)이다. `GET /me/status`의 `active_request.queue_position`, `estimated_wait_min`으로 내려준다. 차량 좌표는 `pose`(map frame)로 내려준다.
- 현재 중앙관제는 `/vehicle_states`의 고정 시뮬레이터 값을 쓰므로, 실제 요청을 반영하는 수신 경로를 중앙관제에 추가해야 한다.

### 5.4 ROS 2 토픽 계약

**Domain Bridge가 필요한 이유**: 차량 3~4대를 동시에 운영하므로 ROS 2 도메인을 나누고, 도메인 사이는 Domain Bridge로 잇는다. 기존 파이프라인 문서(`AIOT_QWEN_CHARGING_PIPELINE.md`)는 단일 PC·단일 도메인 구성이어서 Domain Bridge가 없다. 이 구성은 다중 차량 확장 시 추가되는 부분이다.

도메인 간 통신은 Domain Bridge가 토픽만 넘길 수 있다는 전제로 ROS 2 Topic으로 통일한다. ROS 2 Action은 goal·cancel용 서비스와 feedback·status용 토픽을 함께 쓰기 때문에 토픽만 넘기는 구성에서는 쓸 수 없다. 충전 요청, 차량 이동 작업, 비상 정지는 JSON 메시지 Topic으로 보내고, 각 요청에 `request_id` 또는 `task_id`를 붙여 수락·진행·완료·실패 상태를 같은 ID로 추적한다. Action의 goal·feedback·result에 해당하는 흐름을 Topic과 ID로 직접 구현하는 셈이다.

| Topic | 방향 | 역할 | 구분 |
| --- | --- | --- | --- |
| `/charging/request` | FastAPI → 중앙관제 | 충전 요청(request_id 포함) | 신규 |
| `/charging/cancel` | FastAPI → 중앙관제 | 충전 요청 취소(request_id) | 신규 |
| `/admin/command` | FastAPI → 중앙관제 | 관리자 수동 조치(작업 취소·재시도·재배정, 사유 포함) | 신규 |
| `/emergency_stop` | FastAPI → 중앙관제·차량 | 비상 정지·해제(action: STOP, RELEASE) | 신규 |
| `/vehicle_task` | 중앙관제 → 차량 | 이동 작업(task_id 포함) | 기존 |
| `/vehicle_task_status` | 차량 → 중앙관제 | 수락·이동·도착·완료 보고 | 기존 |
| `/vehicle_command` | 중앙관제 → 충전 시뮬레이터 | START_CHARGING 등 | 기존 |
| `/charging_status` | 충전 시뮬레이터 → 중앙관제 | SOC, 충전 완료 | 기존 |
| `/central_status` | 중앙관제 → FastAPI | 전체 상태와 요청 상태 | 기존, 요청 상태 추가 |

- **토픽 이름 확정**: 위 표의 이름을 5.4의 최종 목록으로 쓴다. 기존 토픽(`/vehicle_task`, `/vehicle_task_status`, `/vehicle_command`, `/charging_status`, `/central_status`)은 현재 구현 이름을 바꾸지 않고, 신규 토픽만 `/charging/...`, `/admin/...` 형태로 둔다. 차량별 토픽을 따로 만들지 않고 모든 메시지에 `vehicle_id`를 담는다. 이 목록 밖의 토픽을 추가하려면 5.4를 먼저 고친다.
- 모든 토픽은 `std_msgs/String` JSON이다. 필드는 `backend/ros_schemas/`(Pydantic)에서 확정했다. `vehicle_id`는 `ros_vehicle_id`(예: CAR_01), `request_id`·`task_id`는 UUID 문자열이고, 시각은 timezone이 있는 UTC ISO 8601이며, 모든 메시지에 `schema_version`(현재 1)이 있다. 수신 측은 모르는 필드를 무시한다.
- MVP에서는 요청 처리 상태를 별도 토픽(`/charging/request_status`)으로 늘리지 않고 `/central_status`에 포함한다. 필요해지면 분리한다.
- 차량 이동 관련 토픽 이름은 현재 구현(`/vehicle_task` 계열)을 그대로 쓴다.
- `/vehicle_task`에는 목적지를 명시한다. 중앙관제가 `fleet_locations.yaml`에서 목표 좌표를 찾아 `target_id`와 `target_pose`를 함께 보내고, 차량은 받은 좌표로 이동만 한다. 예: `{"task_id":"<UUID>","request_id":"<UUID>","vehicle_id":"CAR_01","type":"MOVE_TO_PARKING","target_id":"PARKING_02","target_pose":{"x":12.3,"y":4.8,"yaw":1.57}}` (type은 MOVE_TO_CHARGER, MOVE_TO_PARKING). `request_id`로 작업과 충전 요청을 연결한다.
- `/vehicle_task_status`는 `task_id`와 task 상태(`ACCEPTED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`)와 진행률을 보낸다.
- 충전 요청 메시지 예: `{"request_id":"<UUID>","vehicle_id":"CAR_01","desired_finish_at":"2026-10-03T09:00:00Z","target_soc":80,"min_soc":60,"battery_kwh":60,"max_charge_kw":11,"parking_zone_id":"PARKING_02"}` (`parking_zone_id`는 사용자가 고른 구역이며 null이면 관제가 배정, `battery_kwh`·`max_charge_kw`는 스케줄러의 충전 시간 추정용). 같은 `request_id`로 다시 발행하면 요청 수정으로 보고 중앙관제가 덮어쓴다(수정 전용 토픽을 따로 두지 않는다).
- 그 밖의 메시지 규칙: `/emergency_stop`의 `vehicle_id`가 `ALL`이면 전체 대상이다. `/vehicle_task_status`는 FAILED일 때 `error_message`가 필수이고, `/vehicle_command`의 START_CHARGING은 `target_soc`가 필수이다. `/central_status`의 이벤트에는 중앙관제가 매기는 `event_id`가 있어 재수신해도 중복 저장하지 않는다.
- 도메인 배치(확정 필요): 어느 노드·차량이 어느 `ROS_DOMAIN_ID`에 속하는지, Domain Bridge가 넘기는 토픽 목록은 `docs/AIOT_DOMAIN_CONFIG.md`에 정리하고 `domain_bridge` 설정 파일로 옮긴다. 차량이 늘어도 FastAPI·앱은 바뀌지 않도록 `vehicle_id`를 메시지에 담는다.
- 구조(예상): FastAPI와 중앙관제가 같은 중앙 도메인이면 `/charging/request`와 `/central_status`는 Domain Bridge를 거치지 않는다. 중앙관제 ↔ 차량 구간(`/vehicle_task`, `/vehicle_task_status`, `/emergency_stop`, 차량 상태 토픽)만 Domain Bridge를 지난다. 실제 배치는 `docs/AIOT_DOMAIN_CONFIG.md`에서 확정한다.
- `/central_status`는 MVP에서 하나로 유지한다(차량·충전기·작업·요청 상태·이벤트 포함. 작업은 FastAPI가 `vehicle_tasks`에 저장해 차량 상태의 `current_task_id` 참조를 맞춘다). 다중 차량으로 커져 메시지가 무거워지면 그때 `/vehicle_states`, `/charger_states`, `/scheduler_status`, `/events`로 나눈다.

### 5.5 WebSocket 인증

- 연결 후 5초 안에 첫 메시지로 `{"type":"auth","token":"<Supabase access token>"}`을 보낸다. 보내지 않거나 검증에 실패하면 서버가 연결을 닫는다.
- FastAPI가 JWT의 서명과 만료를 검증하고 user id(sub)와 app_role을 확인한다. 토큰을 URL 쿼리에 싣지 않는다(서버 로그에 남을 수 있음).
- 송신 범위: user는 본인 차량·요청의 상태 변경만, admin은 전체 상태와 이상 알림을 받는다.
- 토큰이 만료되면 서버가 연결을 닫고, 앱이 갱신된 토큰으로 다시 연결해 `GET /me/status`로 상태를 맞춘다.

## 6. 비기능 요구사항과 안전·책임

차량이 무인으로 움직이는 서비스라 보안과 안전 요구를 일반 앱보다 엄격하게 둔다. 수치는 초안 목표이며 측정 후 조정한다.

| 항목 | 요구 |
| --- | --- |
| 보안 | DB·service role key·JWT secret은 FastAPI 서버 환경변수에만 둔다. 앱에는 공개 가능한 anon key만 둔다. |
| 권한 | 모든 API가 JWT와 role을 검사한다. 사용자는 본인 차량·요청만 조회·수정한다. |
| 통신 | 배포 시 HTTPS. 내부 rosbridge는 외부에 직접 노출하지 않고 FastAPI를 거친다(현재 인증·TLS 없음). |
| 실시간성 | 차량 상태 갱신 지연 3초 이내 목표(중앙관제 발행 주기 1 Hz 기준). |
| 장애 대응 | Qwen이 꺼져도 규칙 기반 fallback으로 운영이 계속된다(현재 구현). 앱은 연결 끊김을 화면에 구분해 보여준다. |
| 감사 | 관리자 수동 조치는 누가, 언제, 왜를 audit_logs에 남긴다. |
| 개인정보 | 최소한만 수집하고 탈퇴 시 삭제 요청을 처리한다. 세부 보관 기간은 법률 검토가 필요하다. |
| 화면 | 사용자 앱은 스마트폰(iOS·Android) 세로 기준. 관리자는 웹(데스크톱 브라우저)이며 타 담당자가 정한다. |

### 안전과 책임

- 희망 완료 시각과 SOC의 오차로 계획한 스케줄과 실제 결과가 다를 수 있다. 앱은 "예상"이라는 표현을 써서 확정으로 오해하지 않게 한다.
- 무인 이동 중 충돌·손상 책임 문제가 있어, 사용자 위임 동의(U-09)를 필수 흐름으로 두고 동의 문구는 법률 검토 후 확정한다.
- 초기 검증은 시뮬레이션과 축소 차량으로 제한하고, 실제 양산 전기차 제어는 범위 밖이다.
- 충전 커넥터 체결·분리의 안전은 앱이 보장하지 않는다. 별도 정밀 기구·센서·인터락이 필요하며 앱은 그 상태를 보여주는 역할이다.

## 7. MVP 범위와 열린 질문

MVP는 "사용자가 충전을 요청하고, 관리자가 진행을 보고, 충전이 끝난 차량이 주차 구역으로 복귀하는 한 바퀴"를 앱에서 끝까지 확인할 수 있는 수준으로 잡는다.

### 7.1 개발 순서

1. **상태·인터페이스 확정**: vehicle_states, 충전 요청 상태, 주차 이동 상태, ROS 요청 인터페이스(위 2·5장에 반영)
2. **인증·권한**: C-01, C-02, U-01, A-01 (Supabase Auth, FastAPI JWT 검증)
3. **차량·충전 요청**: U-03, U-04, DB 테이블(profiles, vehicles, charge_requests)
4. **상태 조회**: U-02, U-05, A-02, A-04, A-05 (중앙관제 상태를 DB에 반영하는 연동 포함)
5. **스케줄·이벤트**: A-06, A-08, U-08
6. **주차 위치·알림·안전**: U-06, U-07, A-09, 위임 동의(U-09)
7. **운영 확장**: A-03, A-07, A-10, A-11, A-12

MVP에서는 지도(A-03), 통계(A-11), 사용자 관리(A-10), Qwen 설정 UI·좌표 편집(A-07, A-12), CSV 내보내기(A-08)를 제외한다. 사용자 흐름은 로그인 → 차량 등록 → 충전 요청 → 현재 상태 → 충전 진행 → 주차 이동 → PARKED, 관리자 흐름은 로그인 → 대시보드 → 차량 목록 → 충전기 상태 → 스케줄 큐 → 이벤트다.

현재 중앙관제에서 이미 되는 것: 차량 상태 발행, Qwen/규칙 기반 배차, 이동·충전 상태 보고, 이벤트 저장. 없는 것: 충전 완료 후 주차 복귀 배차(구현 예정), 비상 정지, 사용자 요청 입력 경로, 다중 충전기.

### 7.2 결정 사항과 열린 질문

- [x] 앱 구성: Expo 프로젝트는 사용자 앱만 — (auth), (user) 라우트 그룹. 관리자는 다른 담당자가 웹사이트로 제작(2026-10-05 결정)
- [x] 실시간 방식: REST + FastAPI WebSocket, Supabase Realtime 미사용
- [x] 충전 요청 전달: FastAPI가 ROS 2로 발행, 중앙관제의 DB 폴링은 사용 안 함
- [x] 사용자 지도: MVP는 구역명 표시만
- [x] 사용자 정보 항목: 이름·전화번호만
- [x] 결제·요금: MVP 제외
- [x] ROS 요청 인터페이스: Domain Bridge 제약으로 도메인 간 통신은 ROS 2 Topic으로 통일하고, request_id/task_id로 요청·진행·완료 상태를 관리(5.4). Action 미사용
- [x] WebSocket 인증: 연결 후 첫 메시지로 JWT 검증, user/admin별 송신 범위 제한(5.5)
- [x] 관리자 강제 상태 변경: MVP 제외, 취소·재시도·재배정만 허용
- [x] 오프라인 판정: last_seen_at 5초 이상 미갱신 시 OFFLINE
- [x] 활성 충전 요청: 차량당 1개(부분 유니크 인덱스)
- [x] 차량 진행 단계: 충전소로 이동 중 → 충전 중 → 충전 완료 → 주차구역으로 이동 중 → 주차 완료. 출차(호출) 흐름과 관련 상태·API·토픽은 쓰지 않음(2장)
- [x] 충전 요청 COMPLETED 시점: PARKED 도달 시. desired_finish_at도 PARKED 도달 희망 시각(5.1, 2장)
- [x] 이동 작업(task) 상태: CREATED → ACCEPTED → RUNNING → COMPLETED / FAILED / CANCELLED, 차량 상태와 별개(2장)
- [x] DB 구조: 테이블 15개(vehicle_tasks, push_tokens 추가), TEXT/UUID id 정책, soft delete, RLS 켜고 앱 policy 없음, `app_role` custom claim. DDL은 `backend/db/schema.sql`
- [x] 차량 id 매핑: `vehicles.id`는 UUID, ROS 식별자는 `ros_vehicle_id`(nullable, 삭제되지 않은 차량끼리 유일). 사용자는 차량 정보만 등록하고 관리자가 CAR_01~04를 배정
- [x] 회원 탈퇴: `owner_id` nullable + `on delete set null`, 이력·감사 로그 보존, 개인정보만 삭제(U-09)
- [x] 충전 중에도 취소 가능(IN_PROGRESS에서 취소 허용). 차량을 어디로 옮길지는 관제와 합의 필요
- [x] 지도 좌석 1개 = 차 1대. 자리 n번 = 주차 구역 `PARKING_nn`(1~21), 구역 `capacity` = 1
- [ ] 위임 동의 문구와 탈퇴 시 개인정보(차량번호 포함) 익명화·보관기간 법률 검토
- [ ] 도메인 구성: 도메인 개수와 노드·차량별 `ROS_DOMAIN_ID`, Domain Bridge로 넘길 토픽 목록 확정(5.4, `docs/AIOT_DOMAIN_CONFIG.md`)

### 7.3 다음 단계

기능 명세는 여기서 동결하고 구현 설계로 넘어간다. 순서는 1) DB ERD와 PostgreSQL 테이블 정의(완료: `backend/db/schema.sql`), 2) API 요청·응답 스키마(완료: `backend/schemas/`), 3) ROS Topic JSON 스키마(완료: `backend/ros_schemas/`), 4) FastAPI 구조 생성(완료: 인메모리 저장소·ROS mock·게이트웨이 연결·알림·푸시, 테스트 43개 통과), 5) Supabase DB·Auth 연결, 6) Expo 화면 구현이다.
