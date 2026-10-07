// 서버 backend/schemas/ 와 같은 정의. 화면 코드에서 상태 문자열을 직접 쓰지 말고 이 파일의 값을 쓴다.

export const VehicleState = {
  ARRIVED_AT_STATION: 'ARRIVED_AT_STATION',
  WAITING: 'WAITING',
  ASSIGNED: 'ASSIGNED',
  MOVING_TO_CHARGER: 'MOVING_TO_CHARGER',
  ARRIVED_AT_CHARGER: 'ARRIVED_AT_CHARGER',
  CHARGING: 'CHARGING',
  CHARGE_DONE: 'CHARGE_DONE',
  MOVING_TO_PARKING: 'MOVING_TO_PARKING',
  PARKED: 'PARKED',
  FAULT: 'FAULT',
} as const;
export type VehicleState = (typeof VehicleState)[keyof typeof VehicleState];

export const ChargeRequestStatus = {
  REQUESTED: 'REQUESTED',
  ACCEPTED: 'ACCEPTED',
  SCHEDULED: 'SCHEDULED',
  IN_PROGRESS: 'IN_PROGRESS',
  COMPLETED: 'COMPLETED',
  CANCEL_REQUESTED: 'CANCEL_REQUESTED',
  CANCELLED: 'CANCELLED',
  FAILED: 'FAILED',
} as const;
export type ChargeRequestStatus = (typeof ChargeRequestStatus)[keyof typeof ChargeRequestStatus];

export const HomeState = {
  WAITING_ASSIGNMENT: 'WAITING_ASSIGNMENT',
  NO_DATA: 'NO_DATA',
  NO_REQUEST: 'NO_REQUEST',
  QUEUED: 'QUEUED',
  MOVING_TO_CHARGER: 'MOVING_TO_CHARGER',
  CHARGING: 'CHARGING',
  CHARGE_DONE: 'CHARGE_DONE',
  MOVING_TO_PARKING: 'MOVING_TO_PARKING',
  PARKED: 'PARKED',
  CANCELING: 'CANCELING',
  CANCELLED: 'CANCELLED',
  REQUEST_FAILED: 'REQUEST_FAILED',
  FAULT: 'FAULT',
  VEHICLE_OFFLINE: 'VEHICLE_OFFLINE',
} as const;
export type HomeState = (typeof HomeState)[keyof typeof HomeState];

export const EtaState = { KNOWN: 'KNOWN', CALCULATING: 'CALCULATING', NONE: 'NONE' } as const;
export type EtaState = (typeof EtaState)[keyof typeof EtaState];

export const AppRole = { USER: 'user', ADMIN: 'admin' } as const;
export type AppRole = (typeof AppRole)[keyof typeof AppRole];

export const FeasibilityReason = {
  OK: 'OK',
  DEADLINE_TOO_EARLY: 'DEADLINE_TOO_EARLY',
  NO_CHARGER_CAPACITY: 'NO_CHARGER_CAPACITY',
  CHARGERS_UNAVAILABLE: 'CHARGERS_UNAVAILABLE',
  CENTRAL_UNAVAILABLE: 'CENTRAL_UNAVAILABLE',
} as const;
export type FeasibilityReason = (typeof FeasibilityReason)[keyof typeof FeasibilityReason];

export type Profile = {
  id: string;
  email: string | null;
  name: string | null;
  phone: string | null;
  app_role: AppRole;
  status: 'ACTIVE' | 'SUSPENDED';
  consent_agreed: boolean;
  consent_version: string | null;
};

export type Vehicle = {
  id: string;
  plate_no: string;
  model: string | null;
  battery_kwh: number;
  max_charge_kw: number;
  assigned: boolean;
  created_at: string;
  updated_at: string;
};

export type ChargeRequest = {
  id: string;
  vehicle_id: string;
  desired_finish_at: string;
  target_soc: number;
  min_soc: number;
  parking_zone_id: string | null;
  status: ChargeRequestStatus;
  created_at: string;
  updated_at: string;
  cancel_requested_at: string | null;
  completed_at: string | null;
  queue_position: number | null;
  estimated_wait_min: number | null;
};

export type ChargeInfo = { energy_kwh: number; cost_won: number; unit_price_won: number; in_progress: boolean };

export type VehicleStatus = {
  vehicle_id: string;
  plate_no: string;
  assigned: boolean;
  state: VehicleState | null;
  online: boolean;
  step: number | null;
  step_label: string | null;
  soc: number | null;
  zone_id: string | null;
  charger_id: string | null;
  progress: number | null;
  estimated_completion: string | null;
  active_request: ChargeRequest | null;
  charge: ChargeInfo | null;
  home_state: HomeState;
  eta: { state: EtaState; at: string | null };
  last_request: { id: string; status: ChargeRequestStatus; ended_at: string; failure_reason: string | null } | null;
  last_session: { ended_at: string; energy_kwh: number; cost_won: number; end_soc: number | null } | null;
  last_seen_at: string | null;
  updated_at: string | null;
};

export type MeStatus = { server_time: string; vehicles: VehicleStatus[]; empty_reason: 'NO_VEHICLE' | null };

export type Feasibility = {
  feasible: boolean;
  reason: FeasibilityReason;
  estimated_parked_at: string | null;
  earliest_parked_at: string | null;
  breakdown: { wait_s: number; move_to_charger_s: number; charge_s: number; move_to_parking_s: number } | null;
  message: string | null;
};

export type SeatState = 'TAKEN' | 'FREE' | 'MINE';
export type AreaStateKind = 'OPEN' | 'FULL';
export type AreaSeat = { seat_no: number; zone_id: string; state: SeatState };
export type AreaSummary = {
  area_id: string;
  name: string;
  seat_total: number;
  free_count: number;
  state: AreaStateKind;
  has_mine: boolean;
  seats: AreaSeat[];
};
export type AreasOut = { areas: AreaSummary[] };
export type AreaDetailSeat = AreaSeat & { row: number; col: number };
export type AreaDetail = {
  area_id: string;
  name: string;
  seat_total: number;
  free_count: number;
  state: AreaStateKind;
  rows: number;
  cols: number;
  entrance: { row: number; col: number };
  seats: AreaDetailSeat[];
  selected_zone_id: string | null;
  selected_ok: boolean | null;
};

export type ChargeSession = {
  id: string;
  request_id: string;
  vehicle_id: string;
  charger_id: string;
  start_at: string;
  end_at: string | null;
  start_soc: number;
  end_soc: number | null;
  energy_kwh: number | null;
  unit_price_won: number | null;
  cost_won: number | null;
};

export type NotificationItem = {
  id: string;
  type: string;
  title: string;
  body: string;
  data: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
};

export type NotificationSettings = { charge_done: boolean; parked: boolean; fault: boolean; queue_change: boolean };

export type ParkingZone = { id: string; name: string; capacity: number; available: number; is_available: boolean };

export type WsMessage =
  | { type: 'auth_ok'; role: AppRole }
  | { type: 'vehicle_status'; data: VehicleStatus }
  | { type: 'request_update'; data: ChargeRequest }
  | { type: 'notification'; data: NotificationItem }
  | { type: 'error'; code: string; message: string };

/** 위임 동의 문구 버전(02.04 시트·위임 동의 화면) */
export const CONSENT_VERSION = 'v1';
