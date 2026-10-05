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

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite://")  # 기본: 메모리 SQLite(개발·테스트). 운영은 Supabase Postgres URL


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
