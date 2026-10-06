// 최초 GET /me/status 후 /ws/status로 실시간 갱신. 끊기면 3초 뒤 다시 연결하고 스냅샷을 다시 받는다.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';

import type { MeStatus } from '@/constants/types';
import { api, connectStatusWs } from '@/services/api';
import { useAuth } from '@/services/auth';

type StatusCtx = {
  status: MeStatus | null;
  error: string | null;
  connected: boolean;
  lastUpdated: Date | null;
  refresh: () => Promise<void>;
  reconnect: () => void;
};

const Ctx = createContext<StatusCtx | null>(null);

export function StatusProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const [status, setStatus] = useState<MeStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [attempt, setAttempt] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.status());
      setLastUpdated(new Date());
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    if (!session) return;
    let closed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    refresh();
    connectStatusWs({
      onOpen: () => {
        setConnected(true);
        refresh();
      },
      onMessage: (m) => {
        if (m.type === 'vehicle_status') {
          setStatus((s) =>
            s ? { ...s, vehicles: s.vehicles.map((v) => (v.vehicle_id === m.data.vehicle_id ? m.data : v)) } : s,
          );
          setLastUpdated(new Date());
        } else if (m.type === 'request_update') {
          refresh();
        }
      },
      onClose: () => {
        setConnected(false);
        if (!closed) timer = setTimeout(() => setAttempt((a) => a + 1), 3000);
      },
    }).then((ws) => {
      wsRef.current = ws;
      if (!ws && !closed) timer = setTimeout(() => setAttempt((a) => a + 1), 3000);
    });
    return () => {
      closed = true;
      clearTimeout(timer);
      wsRef.current?.close();
    };
  }, [session?.user.id, attempt, refresh]);

  const reconnect = useCallback(() => {
    wsRef.current?.close();
    setAttempt((a) => a + 1);
  }, []);

  return (
    <Ctx.Provider value={{ status, error, connected, lastUpdated, refresh, reconnect }}>{children}</Ctx.Provider>
  );
}

export function useStatus() {
  const c = useContext(Ctx);
  if (!c) throw new Error('StatusProvider missing');
  return c;
}
