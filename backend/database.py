import os

try:  # backend/.env 가 있으면 읽는다(없어도 무방)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
from datetime import timezone

import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite://"  # 기본: 메모리 SQLite(개발·테스트). 운영은 Supabase Postgres URL


def _make_engine(url: str):
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url, pool_pre_ping=True)


engine = _make_engine(DATABASE_URL)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class UTCDateTime(sa.types.TypeDecorator):
    """항상 timezone-aware UTC로 돌려준다(SQLite는 tz를 버리므로 보정)."""

    impl = sa.DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            raise ValueError("naive datetime is not allowed")
        return value.astimezone(timezone.utc) if value is not None else None

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_dev_db():
    """개발·테스트용: 테이블 생성. 운영 DB는 Alembic(backend/db/schema.sql)으로만 만든다."""
    Base.metadata.create_all(engine)


def migrate_db() -> None:
    """운영(Postgres): 서버가 켜질 때 Alembic 마이그레이션을 최신으로 맞춘다(이미 최신이면 아무것도 안 함).

    배포 플랫폼의 '배포 전 명령' 설정에 기대지 않으려고 코드에서 실행한다. 실패하면 예외로 서버 시작을 막는다
    (스키마가 코드와 다른 채로 요청을 받으면 더 큰 오류가 나므로).
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    here = Path(__file__).resolve().parent
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here / "alembic"))
    command.upgrade(cfg, "head")

