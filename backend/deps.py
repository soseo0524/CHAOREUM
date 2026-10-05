"""인증. dev 모드: 'Authorization: Bearer dev:<uuid>:<user|admin>'. jwt 모드: Supabase JWT(HS256, app_role 클레임)."""
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

import repo
from database import get_db

from config import settings
from errors import ApiError
from schemas.common import AppRole, ErrorCode, ProfileStatus


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    role: AppRole
    email: str | None = None


_jwks = None


def _decode_supabase(token: str) -> dict:
    """SUPABASE_URL이 있으면 새 방식(비대칭 서명 키, JWKS)으로, 없으면 예전 방식(공유 비밀 HS256)으로 검증한다."""
    import jwt

    global _jwks
    if settings.supabase_url:
        _jwks = _jwks or jwt.PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json", cache_keys=True)
        key = _jwks.get_signing_key_from_jwt(token).key
        return jwt.decode(token, key, algorithms=["ES256", "RS256"], audience="authenticated")
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], audience="authenticated")


def authenticate_token(token: str) -> CurrentUser:
    try:
        if settings.auth_mode == "dev":
            _, uid, role = token.split(":")
            return CurrentUser(UUID(uid), AppRole(role))
        import jwt  # PyJWT

        claims = _decode_supabase(token)
        # 'role' 클레임은 PostgreSQL role이라 쓰지 않는다. 관리자 여부는 서버만 쓸 수 있는 곳(app_role 훅 또는 app_metadata)에서만 읽고,
        # 없으면 일반 사용자다. user_metadata는 사용자가 직접 고칠 수 있어 절대 쓰지 않는다.
        role = claims.get("app_role") or (claims.get("app_metadata") or {}).get("app_role") or "user"
        return CurrentUser(UUID(claims["sub"]), AppRole(role), claims.get("email"))
    except Exception:
        raise ApiError(401, ErrorCode.UNAUTHENTICATED, "로그인이 필요합니다.")


def current_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, ErrorCode.UNAUTHENTICATED, "로그인이 필요합니다.")
    u = authenticate_token(authorization[7:])
    if repo.ensure_profile(db, u.id, u.role).status == ProfileStatus.SUSPENDED:
        raise ApiError(403, ErrorCode.FORBIDDEN, "이용이 정지된 계정입니다.")
    return u


def require_user(u: CurrentUser = Depends(current_user)) -> CurrentUser:
    if u.role != AppRole.USER:
        raise ApiError(403, ErrorCode.FORBIDDEN, "사용자 계정만 사용할 수 있습니다.")
    return u


def require_admin(u: CurrentUser = Depends(current_user)) -> CurrentUser:
    if u.role != AppRole.ADMIN:
        raise ApiError(403, ErrorCode.FORBIDDEN, "관리자 권한이 필요합니다.")
    return u
