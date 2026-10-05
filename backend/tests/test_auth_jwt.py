import time
import uuid
from dataclasses import replace

import jwt
import pytest

import deps
from tests.test_api import client, clean  # noqa: F401


@pytest.fixture
def jwt_mode(monkeypatch):
    monkeypatch.setattr(deps, "settings", replace(deps.settings, auth_mode="jwt", jwt_secret="x" * 32, supabase_url=""))


def tok(**extra):
    claims = dict(sub=str(uuid.uuid4()), aud="authenticated", exp=int(time.time()) + 600, email="a@example.com", **extra)
    return jwt.encode(claims, "x" * 32, algorithm="HS256")


def get_me(t):
    return client.get("/me", headers={"Authorization": f"Bearer {t}"})


def test_plain_supabase_token_without_app_role_is_a_user(jwt_mode):
    r = get_me(tok())  # 새로 가입한 사용자 토큰에는 app_role 클레임이 없다
    assert r.status_code == 200 and r.json()["app_role"] == "user" and r.json()["email"] == "a@example.com"


def test_admin_only_from_server_controlled_claims(jwt_mode):
    assert get_me(tok(app_metadata={"app_role": "admin"})).json()["app_role"] == "admin"
    assert get_me(tok(user_metadata={"app_role": "admin"})).json()["app_role"] == "user"  # 사용자가 고칠 수 있는 곳은 무시


def test_bad_or_expired_token_is_401(jwt_mode):
    assert get_me("garbage").status_code == 401
    assert get_me(jwt.encode(dict(sub=str(uuid.uuid4()), aud="authenticated", exp=1), "x" * 32, algorithm="HS256")).status_code == 401
    assert get_me(jwt.encode(dict(sub=str(uuid.uuid4()), aud="authenticated", exp=int(time.time()) + 600), "y" * 32, algorithm="HS256")).status_code == 401
