"""초기 스키마: backend/db/schema.sql 전체를 적용한다(스키마의 단일 출처).

Revision ID: 0001
Revises:
"""
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def upgrade() -> None:
    sql = SCHEMA.read_text(encoding="utf8")
    # text()가 ':'를 바인드 파라미터로 해석하지 않게 이스케이프(::jsonb 등)
    op.execute(sa.text(sql.replace(":", "\\:")))


def downgrade() -> None:
    raise NotImplementedError("초기 스키마는 되돌리지 않는다. 후속 변경은 새 리비전으로 추가한다.")
