// FastAPI 호출은 모두 이 파일에서만 한다. 앱은 DB에 직접 접근하지 않는다.
import type {
  AreaDetail,
  AreasOut,
  ChargeRequest,
  ChargeSession,
  Feasibility,
  MeStatus,
  ParkingZone,
  Profile,
  Vehicle,
  WsMessage,
} from '@/constants/types';
import { supabase } from './supabase';

export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? '').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: any) {
    super(message);
  }
}

async function token(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const t = await token();
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'NETWORK', '서버에 연결할 수 없어요. 같은 Wi-Fi인지, 서버가 켜져 있는지 확인해 주세요.');
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(res.status, data?.code ?? 'UNKNOWN', data?.message ?? `요청에 실패했어요 (${res.status})`, data?.details);
  }
  return data as T;
}

export const api = {
  me: () => request<Profile>('GET', '/me'),
  updateMe: (b: { name?: string; phone?: string }) => request<Profile>('PATCH', '/me', b),
  consent: (version: string) => request('POST', '/consents', { version }),
  status: () => request<MeStatus>('GET', '/me/status'),
  sessions: () => request<ChargeSession[]>('GET', '/me/sessions'),
  vehicles: () => request<Vehicle[]>('GET', '/vehicles'),
  createVehicle: (b: { plate_no: string; model?: string | null; battery_kwh: number; max_charge_kw: number }) =>
    request<Vehicle>('POST', '/vehicles', b),
  parkingAreas: () => request<AreasOut>('GET', '/parking-zones/areas'),
  parkingArea: (areaId: string, selected?: string | null) =>
    request<AreaDetail>('GET', `/parking-zones/areas/${areaId}${selected ? `?selected=${selected}` : ''}`),
  parkingZones: () => request<ParkingZone[]>('GET', '/parking-zones'),
  createRequest: (b: {
    vehicle_id: string;
    desired_finish_at: string;
    target_soc: number;
    min_soc: number;
    parking_zone_id?: string | null;
    dry_run?: boolean;
  }) => request<{ request: ChargeRequest | null; feasibility: Feasibility }>('POST', '/charge-requests', b),
  updateRequest: (
    id: string,
    b: { desired_finish_at?: string; target_soc?: number; min_soc?: number; parking_zone_id?: string; cancel?: true },
  ) => request<{ request: ChargeRequest; feasibility: Feasibility | null }>('PATCH', `/charge-requests/${id}`, b),
};

/** /ws/status 연결. 첫 메시지로 JWT를 보낸다. 끊기면 onClose 후 호출한 쪽이 다시 연결한다. */
export async function connectStatusWs(handlers: {
  onMessage: (m: WsMessage) => void;
  onOpen: () => void;
  onClose: () => void;
}): Promise<WebSocket | null> {
  const t = await token();
  if (!t || !API_URL) return null;
  const ws = new WebSocket(`${API_URL.replace(/^http/, 'ws')}/ws/status`);
  ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token: t }));
  ws.onmessage = (e) => {
    const m = JSON.parse(String(e.data)) as WsMessage;
    if (m.type === 'auth_ok') handlers.onOpen();
    handlers.onMessage(m);
  };
  ws.onclose = () => handlers.onClose();
  return ws;
}
