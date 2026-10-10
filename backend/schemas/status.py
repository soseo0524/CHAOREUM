"""GET /me/status, WS /ws/status, GET /me/sessions, /me/notifications."""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import AwareDatetime, Field

from .charge_requests import ChargeRequestOut
from .common import ApiModel, AppRole, ChargeRequestStatus, StrEnum, TaskStatus, TaskType, VehicleState


STEP_LABELS = {
    1: "충전소로 이동중",
    2: "충전중",
    3: "충전완료",
    4: "주차구역으로 이동중",
    5: "주차완료",
}

# VehicleState -> 5단계. 매핑 없는 상태(ARRIVED_AT_STATION, WAITING, FAULT)는 None.
STATE_TO_STEP: dict[VehicleState, int] = {
    VehicleState.ASSIGNED: 1,
    VehicleState.MOVING_TO_CHARGER: 1,
    VehicleState.ARRIVED_AT_CHARGER: 1,
    VehicleState.CHARGING: 2,
    VehicleState.CHARGE_DONE: 3,
    VehicleState.MOVING_TO_PARKING: 4,
    VehicleState.PARKED: 5,
}


class HomeState(StrEnum):
    """홈 화면이 어떤 모습인지(디자인 2-0~2-11)를 서버가 한 값으로 판정한다. 앱은 이 값으로 화면을 고른다."""

    WAITING_ASSIGNMENT = "WAITING_ASSIGNMENT"  # 차량은 등록했지만 관리자가 아직 배정 안 함(2-9)
    NO_DATA = "NO_DATA"  # 배정됐지만 아직 상태를 한 번도 못 받음(로딩/데이터 없음, 2-10)
    NO_REQUEST = "NO_REQUEST"  # 요청 없음(2-0)
    QUEUED = "QUEUED"  # 접수·대기 중(2-0b)
    MOVING_TO_CHARGER = "MOVING_TO_CHARGER"  # 1단계(2)
    CHARGING = "CHARGING"  # 2단계
    CHARGE_DONE = "CHARGE_DONE"  # 3단계
    MOVING_TO_PARKING = "MOVING_TO_PARKING"  # 4단계
    PARKED = "PARKED"  # 5단계 / 완료
    CANCELING = "CANCELING"  # 취소 처리 중(2-6)
    CANCELLED = "CANCELLED"  # 취소 완료(2-7)
    REQUEST_FAILED = "REQUEST_FAILED"  # 요청 실패(2-5)
    FAULT = "FAULT"  # 차량 문제(관제가 FAULT 보고)
    VEHICLE_OFFLINE = "VEHICLE_OFFLINE"  # 연결 끊김(2-11). 마지막 값은 그대로 내려가며 last_seen_at 으로 "n분 전" 표시


class EtaState(StrEnum):
    """예상 완료시간 표시 규칙. KNOWN=시각 표시 / CALCULATING='계산 중' / NONE='—'."""

    KNOWN = "KNOWN"
    CALCULATING = "CALCULATING"
    NONE = "NONE"


class Eta(ApiModel):
    state: EtaState
    at: AwareDatetime | None = Field(None, description="state=KNOWN일 때만")
    approx: bool = Field(False, description="true면 관제 값이 없어 서버가 대략 계산한 시각(앱에서 '약'으로 표시)")


class LastRequest(ApiModel):
    """활성 요청이 없을 때 직전 요청의 결과(실패·취소·완료). 24시간 지나면 null → NO_REQUEST."""

    id: UUID
    status: ChargeRequestStatus
    ended_at: AwareDatetime
    failure_reason: str | None = Field(None, description="FAILED일 때 사유. 관제가 준 값이 없으면 기본 문구")


class LastSession(ApiModel):
    """가장 최근 끝난 충전 요약(요청 없음 화면 2-0)."""

    ended_at: AwareDatetime
    energy_kwh: float = Field(ge=0)
    cost_won: int = Field(ge=0)
    end_soc: int | None = None


class CurrentTask(ApiModel):
    id: UUID
    type: TaskType
    status: TaskStatus
    progress: float | None = Field(None, ge=0, le=1)


class Pose(ApiModel):
    x: float
    y: float
    yaw: float


class ChargeInfo(ApiModel):
    """충전량·금액(홈 2·2-2~2-4, 6번). 충전 중에는 SOC로 계산한 현재값, 끝난 뒤에는 확정값."""

    energy_kwh: float = Field(ge=0, description="지금까지 충전한 양(kWh)")
    cost_won: int = Field(ge=0, description="충전 금액(원) = round(energy_kwh × unit_price_won)")
    unit_price_won: int = Field(ge=0, description="적용 단가(원/kWh)")
    in_progress: bool = Field(description="true면 충전 중이라 값이 계속 늘어남")


class VehicleStatus(ApiModel):
    vehicle_id: UUID
    plate_no: str
    assigned: bool = Field(description="ros_vehicle_id 배정 여부")
    state: VehicleState | None = Field(None, description="미배정·상태 미수신이면 null")
    online: bool = Field(description="last_seen_at 5초 이내. false면 앱에서 OFFLINE 표시")
    step: int | None = Field(None, ge=1, le=5, description="5단계 진행 번호(STATE_TO_STEP)")
    step_label: str | None = None
    soc: float | None = Field(None, ge=0, le=100)
    zone_id: str | None = Field(None, description="현재 구역(주차 위치 표시용, 예: PARKING_02)")
    pose: Pose | None = Field(None, description="map frame 좌표(m, rad). 지도에 내 차를 그릴 때 사용")
    charger_id: str | None = None
    progress: float | None = Field(None, ge=0, le=1, description="현재 작업 진행률")
    current_task: CurrentTask | None = None
    estimated_completion: AwareDatetime | None = Field(None, description="예상 PARKED 시각")
    active_request: ChargeRequestOut | None = None
    charge: ChargeInfo | None = Field(None, description="충전 중·충전 완료·주차 이동·주차 완료 상태에서만. 최근 충전 세션 기준")
    home_state: HomeState = Field(description="홈 화면 상태(서버 판정). 우선순위는 services.home_state 참고")
    eta: Eta = Field(description="예상 완료시간 표시 규칙")
    last_request: LastRequest | None = Field(None, description="활성 요청이 없을 때만. 실패·취소·완료 직후 화면용")
    last_session: LastSession | None = Field(None, description="활성 요청이 없을 때만. 마지막 충전 요약")
    last_seen_at: AwareDatetime | None = Field(None, description="오프라인 화면의 '마지막 수신 n분 전'")
    updated_at: AwareDatetime | None = None


class MeStatusResponse(ApiModel):
    server_time: AwareDatetime
    vehicles: list[VehicleStatus]
    empty_reason: Literal["NO_VEHICLE"] | None = Field(None, description="vehicles가 비었을 때 'NO_VEHICLE'(등록 차량 없음 화면)")


# --- 이력·알림 ---
class ChargeSessionOut(ApiModel):
    id: UUID
    request_id: UUID
    vehicle_id: UUID
    charger_id: str
    start_at: AwareDatetime
    end_at: AwareDatetime | None
    start_soc: int
    end_soc: int | None
    energy_kwh: float | None
    unit_price_won: int | None = None
    cost_won: int | None = Field(None, description="충전 금액(원). 세션이 끝나지 않았으면 null")


class NotificationOut(ApiModel):
    id: UUID
    type: str
    title: str
    body: str
    data: dict[str, Any]
    read_at: AwareDatetime | None
    created_at: AwareDatetime


class PushTokenCreate(ApiModel):
    token: str = Field(min_length=1)
    platform: Literal["ios", "android"]


# --- WebSocket /ws/status (JSON 메시지, 첫 메시지는 auth, 5초 이내) ---
class WsAuth(ApiModel):  # client -> server
    type: Literal["auth"] = "auth"
    token: str


class WsAuthOk(ApiModel):  # server -> client. 이후 클라이언트는 GET /me/status로 스냅샷 확보
    type: Literal["auth_ok"] = "auth_ok"
    role: AppRole


class WsVehicleStatus(ApiModel):
    type: Literal["vehicle_status"] = "vehicle_status"
    data: VehicleStatus


class WsRequestUpdate(ApiModel):
    type: Literal["request_update"] = "request_update"
    data: ChargeRequestOut


class WsNotification(ApiModel):
    type: Literal["notification"] = "notification"
    data: NotificationOut


class WsAdminEvent(ApiModel):  # admin 전용 스코프
    type: Literal["admin_event"] = "admin_event"
    event_type: str
    at: AwareDatetime
    payload: dict[str, Any]


class WsError(ApiModel):
    type: Literal["error"] = "error"
    code: str
    message: str


WsServerMessage = Annotated[
    Union[
        WsAuthOk,
        WsVehicleStatus,
        WsRequestUpdate,
        WsNotification,
        WsAdminEvent,
        WsError,
    ],
    Field(discriminator="type"),
]


# --- 알림 설정(9-2) ---
class NotificationSettings(ApiModel):
    charge_done: bool = True
    parked: bool = True
    fault: bool = True
    queue_change: bool = False


class NotificationSettingsPatch(ApiModel):
    charge_done: bool | None = None
    parked: bool | None = None
    fault: bool | None = None
    queue_change: bool | None = None
