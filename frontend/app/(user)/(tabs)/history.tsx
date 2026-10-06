// 08.02 충전 이력 — 이번 달 요약과 지난 충전 목록
import { useFocusEffect, router } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, View } from 'react-native';

import { MetricRow } from '@/components/home';
import { BackBar, Screen, T, Title } from '@/components/ui';
import { chargerNo, dayWithWeek, minutesBetween } from '@/constants/format';
import { C } from '@/constants/theme';
import type { ChargeSession } from '@/constants/types';
import { api } from '@/services/api';

export default function History() {
  const [rows, setRows] = useState<ChargeSession[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      setError(null);
      api
        .sessions()
        .then(setRows)
        .catch((e) => setError(e.message));
    }, []),
  );

  const month = useMemo(() => {
    const now = new Date();
    const mine = (rows ?? []).filter((r) => {
      const d = new Date(r.start_at);
      return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
    });
    const kwh = mine.reduce((a, r) => a + (r.energy_kwh ?? 0), 0);
    const mins = mine.reduce((a, r) => a + (minutesBetween(r.start_at, r.end_at) ?? 0), 0);
    return { count: mine.length, kwh, hours: mins / 60 };
  }, [rows]);

  return (
    <Screen tabs contentStyle={{ gap: 20 }}>
      <View style={{ gap: 4 }}>
        <BackBar onPress={() => router.back()} />
        <Title eyebrow="충전 이력" size={32}>
          {`이번 달 ${month.count}회`}
        </Title>
      </View>

      <MetricRow
        items={[
          { label: 'kWh 충전', value: String(Math.round(month.kwh)) },
          { label: '시간', value: month.hours.toFixed(1) },
        ]}
      />

      {rows === null && !error ? <ActivityIndicator color={C.text} style={{ marginTop: 24 }} /> : null}
      {error ? <T style={{ color: C.error, fontSize: 13 }}>{error}</T> : null}
      {rows?.length === 0 ? (
        <T style={{ color: C.sub, fontSize: 14, paddingTop: 12 }}>아직 충전 이력이 없어요.</T>
      ) : null}

      <View>
        {rows?.map((r) => {
          const done = r.end_at != null;
          const gain = done && r.end_soc != null ? `${r.start_soc}% → ${r.end_soc}%` : `${r.start_soc}% → 충전 중`;
          return (
            <Pressable
              key={r.id}
              onPress={() => router.push({ pathname: '/history-detail', params: { id: r.id } })}
              style={{
                paddingVertical: 14,
                borderBottomWidth: 1,
                borderBottomColor: C.line,
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 12,
              }}
            >
              <View style={{ gap: 4, flexShrink: 1 }}>
                <T style={{ fontSize: 15 }}>{dayWithWeek(r.start_at)}</T>
                <T style={{ color: C.sub, fontSize: 12 }}>
                  {[chargerNo(r.charger_id), gain].filter(Boolean).join(' · ')}
                </T>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 3 }}>
                <T mono style={{ fontSize: 20, letterSpacing: -0.5 }}>
                  {r.energy_kwh == null ? '—' : String(Math.round(r.energy_kwh))}
                </T>
                {r.energy_kwh == null ? null : (
                  <T mono style={{ color: C.sub, fontSize: 12, paddingBottom: 3 }}>
                    kWh
                  </T>
                )}
              </View>
            </Pressable>
          );
        })}
      </View>
    </Screen>
  );
}
