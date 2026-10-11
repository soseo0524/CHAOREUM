"""차량별 '결과 확인' 시각: 주차·출차 완료 등 결과 화면에서 '홈으로 돌아가기'를 누르면 그 전에 끝난 결과는 홈에 다시 띄우지 않는다.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table vehicles add column if not exists result_dismissed_at timestamptz")


def downgrade() -> None:
    op.execute("alter table vehicles drop column if exists result_dismissed_at")
