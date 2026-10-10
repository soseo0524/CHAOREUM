"""충전 요청이 도달한 가장 높은 진행 단계. 관제 차량 상태가 흔들려도 앱 화면이 앞 단계로 돌아가지 않게 한다.

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table charge_requests add column if not exists progress_step smallint not null default 0 check (progress_step between 0 and 5)")


def downgrade() -> None:
    op.execute("alter table charge_requests drop column if exists progress_step")
