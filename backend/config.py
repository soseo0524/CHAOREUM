import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    auth_mode: str = field(default_factory=lambda: os.getenv("AUTH_MODE", "dev"))  # dev | jwt
    jwt_secret: str = field(default_factory=lambda: os.getenv("SUPABASE_JWT_SECRET", ""))
    ros_mode: str = field(default_factory=lambda: os.getenv("ROS_MODE", "mock"))  # mock | gateway | rclpy
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", "").rstrip("/"))  # 예: https://xxxx.supabase.co. 있으면 JWT를 공개키(JWKS)로 검증
    supabase_service_key: str = field(default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))  # 회원 탈퇴 시 auth.users 삭제용. 서버에만 둔다
    gateway_token: str = field(default_factory=lambda: os.getenv("GATEWAY_TOKEN", ""))  # ROS_MODE=gateway에서 관제 쪽 게이트웨이가 쓰는 비밀값
    unit_price_won_per_kwh: int = field(default_factory=lambda: int(os.getenv("CHARGE_UNIT_PRICE_WON", "300")))  # 충전 단가(원/kWh). 세션 시작 시점 값을 세션에 저장
    avg_service_min: int = 12  # 대기 1대당 예상 대기시간(분). 스케줄러 연동 시 교체
    offline_after_s: float = 5.0  # last_seen_at 이후 이 시간 넘으면 online=false
    ws_auth_timeout_s: float = 5.0
    move_to_charger_s: int = 60  # 추정용 상수. 스케줄러 연동 시 교체
    move_to_parking_s: int = 60
    cors_origins: tuple = field(default_factory=lambda: tuple(o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()))  # 관리자 웹 출처
    chargers: tuple = ("CHARGER_01", "CHARGER_02")  # DB 연결 전 임시 시드


settings = Settings()
