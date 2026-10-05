# AIOT — 자동 주차/충전 관제 앱

## 개요
- 자동 주차 앱. **사용자 앱(Expo)만 이 저장소에서 만든다.** 관리자는 다른 담당자가 웹사이트로 만들며, 이 저장소는 관리자 웹이 쓰는 `/admin/*` API만 제공(`backend/`). 중앙관제(ROS 2·스케줄러·Qwen)도 다른 담당자가 만든다: 계약은 `backend/ros_schemas/`와 `docs/AIOT_CENTRAL_INTERFACE.md`, 관제 없이는 `ROS_MODE=mock` + `POST /dev/simulate`로 개발.
- 현재 구현: EV 충전 중앙관제 + Qwen(4-bit) 연동 MVP (ROS 2 Humble). 상세: `AIOT_QWEN_CHARGING_PIPELINE.md` (필요할 때만 읽기)
- 팀 실행 가이드: `AIOT_TEAM_EXECUTION_GUIDE.md` (필요할 때만 읽기)
- 기능 명세서(사용자·관리자 앱 화면, API, 상태 모델): `docs/AIOT_FEATURE_SPEC.md` (화면·API 작업 시 해당 장만 읽기)
## 스택 (확정 — 임의로 Firebase/MySQL/Express 등을 섞지 말 것)
- 앱: **Expo + React Native + TypeScript + Expo Router** — `frontend/`. 사용자 앱 전용(관리자 화면 없음), API 호출은 `frontend/services/api.ts` 한 곳에서만.
- 백엔드: **FastAPI + Pydantic + SQLAlchemy + Alembic** — `backend/`. 처음엔 단순하게(main.py, routers/, services.py, ros_bridge.py, deps.py). API 스키마는 `backend/schemas/`, ROS 토픽 JSON은 `backend/ros_schemas/`. DB는 SQLAlchemy(`models.py`, `repo.py`, `database.py`): `DATABASE_URL`이 없으면 메모리 SQLite(개발·테스트), 있으면 Postgres. 운영 스키마는 Alembic이 `backend/db/schema.sql`을 적용(`cd backend && alembic upgrade head`)하며 `tests/test_schema_parity.py`가 모델과 SQL의 컬럼 일치를 검사한다. 개발 실행: `cd backend && AUTH_MODE=dev ROS_MODE=mock uvicorn main:app --reload`, 테스트: `pytest backend/tests`, 커지면 api/services로 분리.
- DB/인증/파일: **Supabase PostgreSQL / Supabase Auth / Supabase Storage**.
- 흐름: Expo → (Supabase Auth 로그인, JWT 발급) → Expo가 JWT를 담아 FastAPI 호출 → FastAPI가 JWT 검증 + 관리자/사용자 권한 검사 → DB.
- **앱은 DB에 직접 접근하지 않고** 주요 CRUD는 모두 FastAPI REST API 경유.
- 비밀값(`DATABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `JWT_SECRET` 등)은 FastAPI 서버 환경변수(`backend/.env`, 커밋 금지)에만. 앱에는 공개 가능한 anon key만.
- 앱 라우트: Expo Router 그룹 `(auth)`, `(user)`. admin 계정이 로그인하면 웹 이용 안내 후 로그아웃. 권한 검사는 FastAPI(`require_user`, `require_admin`). 관리자 웹용 CORS는 `CORS_ORIGINS`.
- 상태 enum: 차량 상태(VehicleState)와 충전 요청 상태(ChargeRequestStatus)는 별도 enum. 서버(Python Enum)와 앱(TS union)에 같은 정의를 두고 문자열을 직접 쓰지 않는다. 상세는 명세서 2장.
- 실시간: 최초 `GET /me/status` 후 FastAPI WebSocket `/ws/status`. Supabase Realtime 미사용. 중앙관제가 DB를 폴링하지 않는다(FastAPI가 ROS 2로 발행). WebSocket은 연결 후 첫 메시지로 JWT 인증. 출차(호출) 흐름은 없음: 차량 진행 = 충전소로 이동 중→충전 중→충전 완료→주차구역으로 이동 중→주차 완료. 차량 3~4대 동시 운영이라 ROS 도메인을 나누고 Domain Bridge(토픽만)로 연결. 도메인 배치 초안은 `docs/AIOT_DOMAIN_CONFIG.md`. 충전 요청 COMPLETED=PARKED 도달 시, desired_finish_at=PARKED 도달 희망 시각, task 상태(CREATED/ACCEPTED/RUNNING/COMPLETED/FAILED/CANCELLED)는 별도 enum. 도메인 간 통신은 Topic + request_id/task_id로 통일(Action 미사용). 활성 충전 요청은 차량당 1개, last_seen_at 5초 초과 시 OFFLINE(표시용).
- DB DDL: `backend/db/schema.sql`(15개 테이블). 권한은 JWT custom claim `app_role`(user/admin)이며 Supabase 기본 `role` claim은 쓰지 않음. vehicles.id는 UUID이고 ROS 식별자(CAR_01 등)는 vehicles.ros_vehicle_id(nullable, 관리자 배정). 충전기·구역 id는 TEXT, 요청·작업·세션 id는 UUID. 회원 탈퇴는 owner_id set null + 이력 보존. public 테이블은 RLS 켜고 앱 policy 없음.
- DB 추가 테이블: `vehicle_states`, `charger_states`는 `/central_status` 수신 시 upsert.
- MVP 제외: 지도, 통계, 사용자 관리, Qwen 설정 UI, 좌표 편집, CSV 내보내기, 결제.
- 배포: 백엔드 Railway, 앱 EAS Build → App Store / Google Play.
- 실시간 차량/충전 상태: rosbridge WebSocket(ws://<서버IP>:9090). 실기기에서는 127.0.0.1 불가.

## 구조
- `aiot_ws/src/aiot_central_control/` ROS 패키지 (nodes, config/fleet_locations.yaml, launch)
- `aiot_ws/qwen_server/` Qwen FastAPI (:8000, /health, /decide)
- `aiot_ws/dashboard/` 웹 대시보드 (참고용)
- `install/`, `log/`는 빌드 산출물 — 읽지 말 것

## 규칙
- Python 3.10. Qwen 서버는 conda `qwen-control`만 사용.
- ROS 실행/빌드 터미널은 conda 비활성화 후 `source /opt/ros/humble/setup.bash`.
- src 수정 후: `colcon build --packages-select aiot_central_control --symlink-install` → source → 노드 재시작.
- ROS 토픽은 std_msgs/String JSON. 토픽 계약 변경 시 PIPELINE 문서도 갱신.
- 검증: `python aiot_ws/test_scheduler.py`, `aiot_ws/test_central_cycle.py` (pytest 가능하면 pytest).
- 불필요한 라이브러리 추가 금지.

## 응답/컨텍스트
- 한국어로 답변, 간결하게. 큰 문서는 필요한 부분만 읽기.

## Summary Instructions
대화 압축 시: 변경한 파일과 이유, 토픽/API 계약, 미해결 이슈와 다음 단계 중심으로 요약.
