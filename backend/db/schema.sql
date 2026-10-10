-- AIOT PostgreSQL schema (Supabase). 기준: docs/AIOT_FEATURE_SPEC.md 5.1
-- 초기 기준 SQL이다. 실제 적용은 Alembic 마이그레이션으로 옮긴다.
-- 앱은 DB에 직접 접근하지 않으며(FastAPI 경유), FastAPI는 서버 환경변수의 service role/DB 연결만 쓴다.

create extension if not exists pgcrypto;

-- ───────── Enum ─────────
create type app_role_enum as enum ('user', 'admin');
create type profile_status_enum as enum ('ACTIVE', 'SUSPENDED');

create type vehicle_state_enum as enum (
    'ARRIVED_AT_STATION', 'WAITING', 'ASSIGNED', 'MOVING_TO_CHARGER',
    'ARRIVED_AT_CHARGER', 'CHARGING', 'CHARGE_DONE', 'MOVING_TO_PARKING',
    'PARKED', 'FAULT'
);

create type charge_request_status_enum as enum (
    'REQUESTED', 'ACCEPTED', 'SCHEDULED', 'IN_PROGRESS', 'COMPLETED',
    'CANCEL_REQUESTED', 'CANCELLED', 'FAILED'
);

create type task_status_enum as enum (
    'CREATED', 'ACCEPTED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'
);

create type task_type_enum as enum ('MOVE_TO_CHARGER', 'MOVE_TO_PARKING');
create type charger_state_enum as enum ('AVAILABLE', 'IN_USE', 'MAINTENANCE', 'FAULT');
create type parking_zone_kind_enum as enum ('WAITING', 'CHARGING', 'PARKING');
-- OFFLINE은 enum에 넣지 않는다: now() - last_seen_at >= 5초일 때 계산하는 파생 상태.

-- ───────── 테이블 ─────────
create table profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    name text,
    phone text,
    app_role app_role_enum not null default 'user',
    status profile_status_enum not null default 'ACTIVE',
    is_super_admin boolean not null default false,
    notification_prefs jsonb not null default '{}'::jsonb,  -- 알림 종류별 켜기/끄기(9-2). 없는 키는 기본값
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table vehicles (
    id uuid primary key default gen_random_uuid(),  -- DB 내부 차량 PK
    ros_vehicle_id text,                       -- ROS 차량 식별자(예: CAR_01). 관리자가 나중에 배정, 배정 전 NULL
    owner_id uuid references profiles(id) on delete set null,  -- 탈퇴 시 소유 관계만 해제하고 이력은 보존
    plate_no text not null,
    model text,
    battery_kwh numeric(8,2) not null check (battery_kwh > 0),
    max_charge_kw numeric(8,2) not null check (max_charge_kw > 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    deleted_at timestamptz                     -- soft delete
);
create unique index uq_active_vehicle_plate on vehicles (plate_no) where deleted_at is null;
-- 삭제되지 않은 차량끼리만 ROS 차량 하나를 하나의 차량에 배정
create unique index uq_active_ros_vehicle_id on vehicles (ros_vehicle_id)
    where ros_vehicle_id is not null and deleted_at is null;

create table chargers (
    id text primary key,                       -- 예: CHARGER_01
    name text not null,
    max_power_kw numeric(8,2) not null check (max_power_kw > 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table parking_zones (
    id text primary key,                       -- 예: PARKING_02
    name text not null,
    kind parking_zone_kind_enum not null,
    capacity integer not null check (capacity > 0),
    pose_x double precision not null,
    pose_y double precision not null,
    pose_yaw double precision not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table charge_requests (
    id uuid primary key default gen_random_uuid(),
    vehicle_id uuid not null references vehicles(id),
    desired_finish_at timestamptz not null,    -- PARKED 도달을 희망하는 시각
    target_soc smallint not null check (target_soc between 1 and 100),
    min_soc smallint not null check (min_soc between 0 and 100),
    parking_zone_id text references parking_zones(id),  -- (이전 방식) 사용자가 고른 칸. 앱은 parking_area를 쓴다
    parking_area text check (parking_area in ('A', 'B', 'C')),  -- 사용자가 고른 주차 구역(null=관제 자동). 칸은 관제가 고른다
    status charge_request_status_enum not null default 'REQUESTED',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    cancel_requested_at timestamptz,
    completed_at timestamptz,                  -- PARKED 도달 시각
    progress_step smallint not null default 0 check (progress_step between 0 and 5),  -- 이 요청이 도달한 가장 높은 진행 단계(화면이 뒤로 가지 않게)
    constraint ck_charge_soc check (min_soc <= target_soc)
);

-- 차량당 활성 충전 요청은 1개
create unique index uq_one_active_charge_request_per_vehicle
    on charge_requests (vehicle_id)
    where status in ('REQUESTED', 'ACCEPTED', 'SCHEDULED', 'IN_PROGRESS', 'CANCEL_REQUESTED');

create table vehicle_tasks (
    id uuid primary key default gen_random_uuid(),
    request_id uuid references charge_requests(id),
    vehicle_id uuid not null references vehicles(id),
    type task_type_enum not null,
    status task_status_enum not null default 'CREATED',
    target_id text not null,                   -- 충전기 또는 주차 구역 id
    target_pose_x double precision not null,
    target_pose_y double precision not null,
    target_pose_yaw double precision not null,
    progress numeric(5,4) not null default 0 check (progress between 0 and 1),
    error_message text,
    created_at timestamptz not null default now(),
    accepted_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz not null default now()
);

create table vehicle_states (
    vehicle_id uuid primary key references vehicles(id) on delete cascade,
    state vehicle_state_enum not null,
    soc smallint not null check (soc between 0 and 100),
    zone_id text references parking_zones(id),
    pose_x double precision,
    pose_y double precision,
    pose_yaw double precision,
    progress numeric(5,4) check (progress between 0 and 1),
    charger_id text references chargers(id),
    current_task_id uuid references vehicle_tasks(id) on delete set null,
    estimated_completion timestamptz,
    last_seen_at timestamptz not null,
    updated_at timestamptz not null default now()
);

create table charger_states (
    charger_id text primary key references chargers(id) on delete cascade,
    state charger_state_enum not null,
    output_kw numeric(8,2) check (output_kw >= 0),
    assigned_vehicle_id uuid references vehicles(id),
    maintenance boolean not null default false,  -- true + IN_USE: 현재 작업 종료 후 점검 진입
    last_seen_at timestamptz not null,
    updated_at timestamptz not null default now()
);

create table charge_sessions (
    id uuid primary key default gen_random_uuid(),
    request_id uuid not null references charge_requests(id),
    charger_id text not null references chargers(id),
    start_at timestamptz not null,
    end_at timestamptz,
    start_soc smallint not null check (start_soc between 0 and 100),
    end_soc smallint check (end_soc between 0 and 100),
    energy_kwh numeric(10,3) check (energy_kwh >= 0),
    unit_price_won integer check (unit_price_won >= 0),
    created_at timestamptz not null default now(),
    constraint ck_charge_session_time check (end_at is null or end_at >= start_at)
);

create table events (
    id bigint generated always as identity primary key,
    source_event_id text,                      -- 중앙관제 event_id. 재수신 중복 방지
    at timestamptz not null default now(),
    type text not null,
    vehicle_id uuid references vehicles(id),
    charger_id text references chargers(id),
    request_id uuid references charge_requests(id),
    task_id uuid references vehicle_tasks(id),
    payload jsonb not null default '{}'::jsonb
);

create table notifications (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references profiles(id) on delete cascade,
    type text not null,
    title text not null,
    body text not null,
    data jsonb not null default '{}'::jsonb,
    read_at timestamptz,
    created_at timestamptz not null default now()
);

create table push_tokens (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references profiles(id) on delete cascade,
    expo_push_token text not null unique,
    platform text check (platform in ('ios', 'android')),
    enabled boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now()
);

create table consents (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references profiles(id) on delete cascade,
    version text not null,
    agreed_at timestamptz not null default now(),
    revoked_at timestamptz
);

create table audit_logs (
    id bigint generated always as identity primary key,
    admin_id uuid not null references profiles(id),
    action text not null,
    reason text not null,                      -- 사유 없는 수동 조치 방지
    entity_type text,
    entity_id text,
    before_data jsonb,
    after_data jsonb,
    at timestamptz not null default now()
);

create table settings (
    key text primary key,
    value jsonb not null,
    updated_by uuid references profiles(id) on delete set null,
    updated_at timestamptz not null default now()
);

-- ───────── 인덱스 ─────────
create index idx_vehicles_owner on vehicles (owner_id);
create index idx_charge_requests_vehicle on charge_requests (vehicle_id);
create index idx_charge_requests_status on charge_requests (status);
create index idx_charge_requests_finish on charge_requests (desired_finish_at);
create index idx_vehicle_tasks_request on vehicle_tasks (request_id);
create index idx_vehicle_tasks_vehicle on vehicle_tasks (vehicle_id);
create index idx_vehicle_tasks_status on vehicle_tasks (status);
create index idx_charge_sessions_request on charge_sessions (request_id);
create unique index uq_events_source_event_id on events (source_event_id) where source_event_id is not null;
create index idx_events_at on events (at desc);
create index idx_events_vehicle on events (vehicle_id);
create index idx_events_type on events (type);
create index idx_notifications_user_created on notifications (user_id, created_at desc);
create index idx_notifications_unread on notifications (user_id) where read_at is null;
create index idx_consents_user on consents (user_id, agreed_at desc);

-- ───────── updated_at 자동 갱신 ─────────
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger trg_profiles_updated_at before update on profiles for each row execute function set_updated_at();
create trigger trg_vehicles_updated_at before update on vehicles for each row execute function set_updated_at();
create trigger trg_chargers_updated_at before update on chargers for each row execute function set_updated_at();
create trigger trg_parking_zones_updated_at before update on parking_zones for each row execute function set_updated_at();
create trigger trg_charge_requests_updated_at before update on charge_requests for each row execute function set_updated_at();
create trigger trg_vehicle_tasks_updated_at before update on vehicle_tasks for each row execute function set_updated_at();
create trigger trg_vehicle_states_updated_at before update on vehicle_states for each row execute function set_updated_at();
create trigger trg_charger_states_updated_at before update on charger_states for each row execute function set_updated_at();
create trigger trg_push_tokens_updated_at before update on push_tokens for each row execute function set_updated_at();

-- ───────── RLS: 켜되 앱용 policy는 만들지 않는다 (앱은 DB 직접 접근 금지) ─────────
alter table profiles enable row level security;
alter table vehicles enable row level security;
alter table vehicle_states enable row level security;
alter table charge_requests enable row level security;
alter table vehicle_tasks enable row level security;
alter table charge_sessions enable row level security;
alter table chargers enable row level security;
alter table charger_states enable row level security;
alter table parking_zones enable row level security;
alter table events enable row level security;
alter table notifications enable row level security;
alter table consents enable row level security;
alter table audit_logs enable row level security;
alter table settings enable row level security;
alter table push_tokens enable row level security;

-- ───────── Supabase Auth 연동 ─────────
-- 가입 시 profiles 행을 만든다(app_role은 기본 'user'. 사용자 메타데이터에서 권한을 읽지 않는다).
create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    insert into public.profiles (id) values (new.id) on conflict (id) do nothing;
    return new;
end;
$$;
create trigger on_auth_user_created after insert on auth.users
    for each row execute function public.handle_new_user();

-- Custom Access Token Hook: profiles.app_role을 JWT의 app_role 클레임으로 넣는다.
-- 적용 후 Supabase 대시보드 Authentication > Hooks에서 이 함수를 선택해 켠다.
create function public.custom_access_token_hook(event jsonb) returns jsonb
language plpgsql stable as $$
declare
    claims jsonb := event->'claims';
    r public.app_role_enum;
begin
    select app_role into r from public.profiles where id = (event->>'user_id')::uuid;
    claims := jsonb_set(claims, '{app_role}', to_jsonb(coalesce(r, 'user')::text));
    return jsonb_set(event, '{claims}', claims);
end;
$$;
grant usage on schema public to supabase_auth_admin;
grant execute on function public.custom_access_token_hook to supabase_auth_admin;
revoke execute on function public.custom_access_token_hook from authenticated, anon, public;
grant select on table public.profiles to supabase_auth_admin;
-- 훅 전용 읽기 policy(앱용 아님. anon/authenticated에는 여전히 policy 없음)
create policy auth_admin_read_profiles on public.profiles as permissive for select
    to supabase_auth_admin using (true);
