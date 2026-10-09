"""충전 요청에 주차 구역(A·B·C) 지정 칸 추가. 칸(자리)은 관제가 고른다.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 새 DB는 0001(schema.sql)에서 이미 만들어지므로 있으면 건너뛴다
    op.execute("alter table charge_requests add column if not exists parking_area text check (parking_area in ('A', 'B', 'C'))")


def downgrade() -> None:
    op.execute("alter table charge_requests drop column if exists parking_area")
