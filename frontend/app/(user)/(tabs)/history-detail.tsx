// 08.03 충전 이력 상세
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator } from 'react-native';

import { MetricRow } from '@/components/home';
import { BackBar, Row, Screen, T, Title } from '@/components/ui';
import { chargerNo, clockText, dayWithWeek, minutesBetween, won } from '@/constants/format';
import { C } from '@/constants/theme';
import type { ChargeSession } from '@/constants/types';
import { api } from '@/services/api';

export default function HistoryDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [row, setRow] = useState<ChargeSession | null | undefined>(undefined);

  useFocusEffect(
    useCallback(() => {
      api
        .sessions()
        .then((all) => setRow(all.find((r) => r.id === id) ?? null))
        .catch(() => setRow(null));
    }, [id]),
  );

  if (row === undefined) {
    return (
      <Screen tabs>
        <BackBar onPress={() => router.back()} />
        <ActivityIndicator color={C.text} style={{ marginTop: 40 }} />
      </Screen>
    );
  }
  if (row === null) {
    return (
      <Screen tabs>
        <BackBar onPress={() => router.back()} />
        <T style={{ color: C.sub, fontSize: 14 }}>이 충전 기록을 찾을 수 없어요.</T>
      </Screen>
    );
  }

  const done = row.end_at != null && row.end_soc != null;
  const mins = minutesBetween(row.start_at, row.end_at);
  const d = new Date(row.start_at);

  return (
    <Screen tabs contentStyle={{ gap: 18 }}>
      <BackBar onPress={() => router.back()} />
      <Title size={32}>{`${d.getMonth() + 1}월 ${d.getDate()}일 충전`}</Title>
      <MetricRow
        items={[
          { label: '충전된 양', value: done ? String(row.end_soc! - row.start_soc) : '—', unit: done ? '%' : undefined },
          { label: 'kWh', value: row.energy_kwh == null ? '—' : String(Math.round(row.energy_kwh)) },
        ]}
      />
      <Row label="배터리" chevron={false}>
        <T mono style={{ fontSize: 15 }}>
          {row.start_soc}% → {done ? `${row.end_soc}%` : '충전 중'}
        </T>
      </Row>
      <Row label="충전 시간" chevron={false}>
        <T mono style={{ fontSize: 15 }}>
          {clockText(row.start_at)} ~ {row.end_at ? clockText(row.end_at) : '진행 중'}
          {mins != null ? ` (${mins}분)` : ''}
        </T>
      </Row>
      <Row label="충전기" chevron={false}>
        <T style={{ fontSize: 15 }}>{chargerNo(row.charger_id) ?? '—'}</T>
      </Row>
      <Row label="충전 금액" chevron={false}>
        <T mono style={{ fontSize: 15 }}>
          {row.cost_won == null ? '—' : `${won(row.cost_won)}원`}
        </T>
      </Row>
      <Row label="날짜" chevron={false}>
        <T style={{ fontSize: 15 }}>{dayWithWeek(row.start_at)}</T>
      </Row>
      <Row label="요청 번호" chevron={false}>
        <T mono style={{ fontSize: 15 }}>
          #{row.request_id.slice(0, 6).toUpperCase()}
        </T>
      </Row>
    </Screen>
  );
}
