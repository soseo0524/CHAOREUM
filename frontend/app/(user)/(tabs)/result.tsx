// 03.06 주차 완료 · 결과 요약
import { router, useFocusEffect } from 'expo-router';
import { Car, Check, ChevronRight } from 'lucide-react-native';
import { useCallback, useState } from 'react';
import { Pressable, View } from 'react-native';

import { BackBar, Button, Screen, T } from '@/components/ui';
import { clockText, minutesBetween, won, zoneLabel } from '@/constants/format';
import { C } from '@/constants/theme';
import type { ChargeSession } from '@/constants/types';
import { useStatus } from '@/hooks/useStatus';
import { api } from '@/services/api';

export default function Result() {
  const { status } = useStatus();
  const v = status?.vehicles[0];
  const [session, setSession] = useState<ChargeSession | null>(null);

  useFocusEffect(
    useCallback(() => {
      if (!v) return;
      api
        .sessions()
        .then((rows) => setSession(rows.find((r) => r.vehicle_id === v.vehicle_id) ?? null))
        .catch(() => {});
    }, [v?.vehicle_id]), // eslint-disable-line react-hooks/exhaustive-deps
  );

  const zone = zoneLabel(v?.zone_id ?? v?.active_request?.parking_zone_id) ?? '주차 구역';
  const doneAt = v?.active_request?.completed_at ?? v?.last_request?.ended_at ?? session?.end_at ?? null;
  const soc = session?.end_soc ?? (v?.soc != null ? Math.round(v.soc) : null);
  const mins = session ? minutesBetween(session.start_at, session.end_at) : null;
  const kwh = session?.energy_kwh ?? v?.charge?.energy_kwh ?? null;
  const cost = session?.cost_won ?? v?.charge?.cost_won ?? null;

  return (
    <Screen tabs scroll footer={<Button label="이력 보기" onPress={() => router.push('/history')} />}>
      <BackBar onPress={() => router.back()} />
      <View style={{ gap: 10, paddingTop: 8 }}>
        <View
          style={{
            width: 64,
            height: 64,
            borderRadius: 32,
            backgroundColor: C.active,
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Check size={32} color="#FFFFFF" strokeWidth={3} />
        </View>
        <T style={{ color: C.active, fontSize: 36, letterSpacing: -1, lineHeight: 42 }}>{'주차까지\n끝났어요'}</T>
        <T style={{ color: C.sub, fontSize: 14 }}>
          {v?.plate_no ?? ''}
          {doneAt ? ` · ${clockText(doneAt)} 완료` : ''}
        </T>
      </View>

      <View style={{ gap: 12, paddingTop: 12 }}>
        <T style={{ color: C.sub, fontSize: 12, letterSpacing: 1 }}>주차 위치</T>
        <Pressable
          onPress={() => router.navigate('/')}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: 14,
            padding: 16,
            borderRadius: 24,
            backgroundColor: '#1c1c1e',
          }}
        >
          <View
            style={{
              width: 52,
              height: 52,
              borderRadius: 14,
              backgroundColor: C.active,
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Car size={28} color="#0b1f1c" />
          </View>
          <View style={{ flex: 1, gap: 2 }}>
            <T medium style={{ fontSize: 20, letterSpacing: -0.5 }}>
              {zone}
            </T>
            <T style={{ color: '#8e8e93', fontSize: 14 }}>주차 완료</T>
          </View>
          <ChevronRight size={20} color="#48484a" />
        </Pressable>
      </View>

      <View style={{ flexDirection: 'row', gap: 10, paddingTop: 12 }}>
        <Stat label="배터리" value={soc != null ? String(soc) : '—'} unit="%" />
        <Stat label="충전 시간" value={mins != null ? String(mins) : '—'} unit="분" />
        <Stat label="충전량" value={kwh != null ? String(Math.round(kwh)) : '—'} unit="kWh" />
      </View>
      <View style={{ flexDirection: 'row' }}>
        <Stat label="충전 금액" value={cost != null ? won(cost) : '—'} unit="원" />
      </View>
    </Screen>
  );
}

function Stat({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <View
      style={{ flex: 1, gap: 4, backgroundColor: C.surface, borderRadius: 18, padding: 16, paddingRight: 14 }}
    >
      <T style={{ color: C.sub, fontSize: 12 }}>{label}</T>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 3 }}>
        <T mono style={{ fontSize: 26, letterSpacing: -1 }}>
          {value}
        </T>
        <T mono style={{ color: C.sub, fontSize: 12, paddingBottom: 5 }}>
          {unit}
        </T>
      </View>
    </View>
  );
}
