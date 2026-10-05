"""Expo 푸시 전송. PUSH_MODE=mock(기본)이면 보내지 않고 sent에 기록만 한다. PUSH_MODE=expo면 Expo Push API로 보낸다."""
from __future__ import annotations

import json
import os
import urllib.request
from uuid import UUID

import models as m
from sqlalchemy import select
from sqlalchemy.orm import Session

EXPO_URL = "https://exp.host/--/api/v2/push/send"
sent: list[dict] = []  # mock 모드 전송 기록(시험용)


def mode() -> str:
    return os.getenv("PUSH_MODE", "mock")


def send(db: Session, user_id: UUID, title: str, body: str, data: dict) -> int:
    """사용자의 켜진 토큰 모두에 보낸다. 보낸 개수를 돌려준다. 전송 실패는 알림 처리 전체를 막지 않는다."""
    tokens = list(db.scalars(select(m.PushToken.expo_push_token).where(m.PushToken.user_id == user_id, m.PushToken.enabled.is_(True))))
    if not tokens:
        return 0
    msgs = [dict(to=t, title=title, body=body, data=data, sound="default") for t in tokens]
    if mode() != "expo":
        sent.extend(msgs)
        return len(msgs)
    try:
        req = urllib.request.Request(EXPO_URL, data=json.dumps(msgs).encode(), headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:  # 네트워크 오류 등. 알림함에는 이미 저장돼 있다
        return 0
    return len(msgs)
