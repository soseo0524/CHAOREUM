# AIOT · 자동 충전·주차 사용자 앱

전기차를 맡기면 로봇이 **충전소로 이동 → 충전 → 주차 구역으로 이동 → 주차**까지 자동으로 해 주는 서비스의 **사용자 앱과 그 백엔드**입니다.
앱은 Expo(React Native), 서버는 FastAPI, 데이터베이스와 로그인은 Supabase를 씁니다.

> 이 저장소 범위: 사용자 앱 + 백엔드(API·DB). 관리자 웹과 ROS2 관제·스케줄러·Qwen은 다른 담당자의 작업이며, 서로의 약속(계약)은 `backend/ros_schemas/`와 `docs/AIOT_CENTRAL_INTERFACE.md`에 있습니다.

## 진행 상황

| 단계 | 상태 |
|---|---|
| 화면 디자인 (`design/`) | 완료(수정 가능) |
| API 스키마, ROS JSON 계약 | 완료 |
| FastAPI + SQLAlchemy + Alembic | 완료. 개발용 SQLite 테스트 49개 통과 |
| Supabase 연결 | 진행 중. 프로젝트 생성·`.env` 작성·`alembic upgrade head`/`seed.py` 실행(터미널에서 직접). 가입 시 `profiles` 자동 생성 트리거와 JWT 관리자 권한 훅을 `schema.sql`에 추가. 대시보드에서 훅 켜기와 로그인 실물 확인은 남음 |
| Expo 앱 화면 | 예정 |
| 실제 ROS2 관제 연동 | 개발용 시뮬레이터만 검증. 게이트웨이 스크립트는 ROS2에서 미시험 |

## 폴더 구조

```
backend/   FastAPI 서버 (routers/, services.py, models.py, schemas/, ros_schemas/, alembic/, tests/)
gateway/   관제 PC에서 서버로 연결하는 ROS 게이트웨이 스크립트
docs/      기능 명세, 관제 인터페이스, 도메인 설정
design/    화면 디자인 (aiot-user-app.pen, Pencil로 열기)
app/       Expo 사용자 앱 (예정)
```

## 백엔드 실행

Python 3.10 이상이 필요합니다.

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 개발 모드: 로그인 없이(dev 토큰), 메모리 SQLite, 가짜 관제
AUTH_MODE=dev ROS_MODE=mock uvicorn main:app --reload
```

- 문서: http://localhost:8000/docs
- 테스트: `pytest backend/tests` (루트에서) 또는 `cd backend && pytest`
- 개발 모드에서는 `Authorization: Bearer dev:<사용자UUID>:user` 형태의 토큰을 씁니다(관리자는 `:admin`).
- `POST /dev/simulate`가 5단계 흐름(이동 → 충전 → 충전 완료 → 주차 이동 → 주차 완료)을 가짜로 돌려 줍니다.

## 환경 변수 (Supabase 연결)

`backend/.env.example`을 `backend/.env`로 복사해서 채웁니다. **`.env`는 절대 커밋하지 않습니다.**(`.gitignore`에 들어 있음)

| 변수 | 설명 |
|---|---|
| `AUTH_MODE` | `dev`(개발) / `jwt`(Supabase 로그인 토큰 검증) |
| `SUPABASE_URL` | `https://<프로젝트>.supabase.co`. 이 값이 있으면 공개키로 토큰을 검증 |
| `SUPABASE_SERVICE_ROLE_KEY` | 회원 탈퇴 시 계정 삭제용. 서버에만 두기 |
| `DATABASE_URL` | Supabase의 Postgres 연결 문자열. 비우면 메모리 SQLite |
| `ROS_MODE` | `mock` / `gateway`(관제 PC가 서버로 연결) / `rclpy`(미구현) |
| `GATEWAY_TOKEN` | `gateway` 모드에서 관제 게이트웨이와 나눠 쓰는 비밀값 |
| `PUSH_MODE` | `mock`(기록만) / `expo`(실제 푸시) |
| `CHARGE_UNIT_PRICE_WON` | 충전 단가(원/kWh), 기본 300(임시값) |
| `CORS_ORIGINS` | 관리자 웹 출처(쉼표 구분) |

DB 테이블 만들기(Postgres에 연결한 뒤):

```bash
cd backend && alembic upgrade head
```

### Supabase Auth 연동 (schema.sql 끝부분)

- 가입하면 `auth.users` 트리거가 `profiles` 행을 자동으로 만든다(`handle_new_user`, 기본 권한 `user`).
- 관리자 권한은 `profiles.app_role`을 로그인 토큰(JWT)의 `app_role` 클레임으로 넣는 **Custom Access Token Hook**(`custom_access_token_hook`)으로 전달한다. 서버는 이 클레임만 믿고, 사용자가 고칠 수 있는 `user_metadata`는 읽지 않는다.
- 이미 만든 DB라면 `schema.sql`의 이 부분은 `alembic upgrade head`만으로는 반영되지 않으므로(0001은 한 번만 실행) SQL Editor에서 해당 구문을 한 번 실행하거나 새 리비전으로 추가한다.
- 적용 후 Supabase 대시보드 **Authentication → Hooks**에서 `custom_access_token_hook`을 선택해 켠다.

## 주요 API

| 용도 | 엔드포인트 |
|---|---|
| 홈 상태(화면 판정 `home_state`, 예상 시간, 충전량·금액) | `GET /me/status`, `WS /ws/status` |
| 차량 | `GET/POST/PATCH/DELETE /vehicles` |
| 충전 요청·취소·수정 | `POST /charge-requests`, `PATCH /charge-requests/{id}` |
| 주차 구역 목록 | `GET /parking-zones` |
| 전체 지도: 구역(A·B·C)별 빈자리 수 | `GET /parking-zones/areas` |
| 구역 안 맵: 자리별 상태·칸 위치 | `GET /parking-zones/areas/{A\|B\|C}?selected=PARKING_33` |
| 충전 이력 | `GET /me/sessions` |
| 알림·푸시 | `GET /me/notifications`, `/me/notification-settings`, `/me/push-tokens` |
| 관제 연결 | `/ws/gateway` (ROS 게이트웨이) |

화면 상태와 서버 값의 대응(값이 없을 때의 "계산 중", "—" 표시 규칙 포함)은 `docs/AIOT_FEATURE_SPEC.md`의 "화면 상태" 절을 보세요.

## 문서

- `docs/AIOT_FEATURE_SPEC.md` 기능 명세와 화면 상태 매핑
- `docs/AIOT_CENTRAL_INTERFACE.md` 중앙관제와의 인터페이스(토픽, 실패·취소 사유 전달)
- `docs/AIOT_DOMAIN_CONFIG.md` 도메인 설정
- `CLAUDE.md` 개발 규칙

## 보안 메모

- 비밀번호·키·`.env`는 저장소와 채팅에 올리지 않습니다. 실수로 올렸다면 해당 키를 재발급하세요.
- 개인정보·위치정보 동의 문구는 법률 검토 전입니다.
