// 06.03 알림 설정
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, View } from 'react-native';

import { Toggle } from '@/components/dialog';
import { BackBar, Screen, T, Title } from '@/components/ui';
import { C } from '@/constants/theme';
import type { NotificationSettings } from '@/constants/types';
import { api } from '@/services/api';

const ITEMS: { key: keyof NotificationSettings; title: string; sub: string }[] = [
  { key: 'charge_done', title: '충전 완료', sub: '충전이 끝나면 알려 드려요' },
  { key: 'parked', title: '주차 완료', sub: '주차가 끝나면 알려 드려요' },
  { key: 'fault', title: '연결 끊김·차량 이상', sub: '문제가 생기면 바로 알려 드려요' },
  { key: 'queue_change', title: '대기 순번 변경', sub: '내 순서가 바뀌면 알려 드려요' },
];

export default function NotificationSettingsScreen() {
  const [s, setS] = useState<NotificationSettings | null>(null);

  useFocusEffect(
    useCallback(() => {
      api
        .notificationSettings()
        .then(setS)
        .catch((e) => Alert.alert('불러오기 실패', e.message));
    }, []),
  );

  async function toggle(key: keyof NotificationSettings, value: boolean) {
    const prev = s;
    setS((x) => (x ? { ...x, [key]: value } : x));
    try {
      setS(await api.updateNotificationSettings({ [key]: value }));
    } catch (e: any) {
      setS(prev);
      Alert.alert('저장 실패', e.message);
    }
  }

  return (
    <Screen tabs contentStyle={{ gap: 14 }}>
      <BackBar onPress={() => router.back()} />
      <Title eyebrow="내 정보">알림 설정</Title>
      {s ? (
        ITEMS.map((it) => (
          <View
            key={it.key}
            style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 14 }}
          >
            <View style={{ gap: 4, flex: 1 }}>
              <T style={{ fontSize: 16 }}>{it.title}</T>
              <T style={{ color: C.sub, fontSize: 13 }}>{it.sub}</T>
            </View>
            <Toggle value={s[it.key]} onChange={(v) => toggle(it.key, v)} />
          </View>
        ))
      ) : (
        <ActivityIndicator color={C.text} />
      )}
    </Screen>
  );
}
