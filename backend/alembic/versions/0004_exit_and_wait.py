"""출차(exit_requests, 차량 상태 MOVING_TO_EXIT·EXITED)와 임시 대기 칸(charge_requests.wait_zone_id·wait_arrived).

0001이 schema.sql 전체를 적용하므로 새 DB에는 이미 있다. 그래서 모두 '없을 때만' 만든다.

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter type vehicle_state_enum add value if not exists 'MOVING_TO_EXIT' before 'FAULT'")
    op.execute("alter type vehicle_state_enum add value if not exists 'EXITED' before 'FAULT'")
    op.execute("""
        do $$ begin
            create type exit_status_enum as enum ('REQUESTED', 'IN_PROGRESS', 'COMPLETED', 'FAILED');
        exception when duplicate_object then null;
        end $$
    """)
    op.execute("alter table charge_requests add column if not exists wait_zone_id text")
    op.execute("alter table charge_requests add column if not exists wait_arrived boolean not null default false")
    op.execute("""
        create table if not exists exit_requests (
            id uuid primary key default gen_random_uuid(),
            vehicle_id uuid not null references vehicles(id) on delete cascade,
            charge_request_id uuid references charge_requests(id) on delete set null,
            status exit_status_enum not null default 'REQUESTED',
            exit_zone_id text,
            error_message text,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            completed_at timestamptz
        )
    """)
    op.execute("create unique index if not exists uq_one_active_exit_per_vehicle on exit_requests (vehicle_id) where status in ('REQUESTED', 'IN_PROGRESS')")
    op.execute("create index if not exists idx_exit_requests_vehicle on exit_requests (vehicle_id, created_at desc)")
    op.execute("drop trigger if exists trg_exit_requests_updated_at on exit_requests")
    op.execute("create trigger trg_exit_requests_updated_at before update on exit_requests for each row execute function set_updated_at()")
    op.execute("alter table exit_requests enable row level security")


def downgrade() -> None:
    op.execute("drop table if exists exit_requests")
    op.execute("drop type if exists exit_status_enum")
    op.execute("alter table charge_requests drop column if exists wait_arrived")
    op.execute("alter table charge_requests drop column if exists wait_zone_id")
    # vehicle_state_enum 값은 Postgres에서 지울 수 없어 남겨 둔다
