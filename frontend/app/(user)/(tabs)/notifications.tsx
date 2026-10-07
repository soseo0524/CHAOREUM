// 08.01 알림함
import { router, useFocusEffect } from 'expo-router';
import { ChevronLeft } from 'lucide-react-native';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, View } from 'react-native';

import { Screen, T, Title } from '@/components/ui';
import { clockText, monthDay } from '@/constants/format';
import { C } from '@/constants/theme';
import type { NotificationItem } from '@/constants/types';
import { api } from '@/services/api';

function dayKey(iso: string) {
  const d = new Date(iso);
  const today = new Date();
  const y = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return '오늘';
  if (d.toDateString() === y.toDateString()) return '어제';
  return monthDay(iso);
}

export default function Notifications() {
  const [rows, setRows] = useState<NotificationItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .notifications()
      .then(setRows)
      .catch((e) => setError(e.message));
  }, []);
  useFocusEffect(load);

  async function readAll() {
    try {
      await api.readAllNotifications();
      load();
    } catch (e: any) {
      Alert.alert('읽음 처리 실패', e.message);
    }
  }

  async function open(n: NotificationItem) {
    if (!n.read_at) {
      setRows((r) => r?.map((x) => (x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x)) ?? r);
      api.readNotification(n.id).catch(() => {});
    }
    if (n.type === 'PARKED') router.push('/result');
  }

  const groups: { key: string; items: NotificationItem[] }[] = [];
  for (const n of rows ?? []) {
    const k = dayKey(n.created_at);
    const g = groups[groups.length - 1];
    if (g?.key === k) g.items.push(n);
    else groups.push({ key: k, items: [n] });
  }

  return (
    <Screen tabs>
      <View style={{ height: 40, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <ChevronLeft size={22} color={C.text} />
        </Pressable>
        {rows?.some((n) => !n.read_at) ? (
          <Pressable onPress={readAll} hitSlop={10}>
            <T style={{ color: C.primaryText, fontSize: 13 }}>모두 읽음</T>
          </Pressable>
        ) : null}
      </View>
      <View style={{ paddingTop: 4, paddingBottom: 12 }}>
        <Title>알림</Title>
      </View>
      {rows === null && !error ? <ActivityIndicator color={C.text} /> : null}
      {error ? <T style={{ color: C.error, fontSize: 13 }}>{error}</T> : null}
      {rows?.length === 0 ? <T style={{ color: C.sub, fontSize: 14 }}>아직 받은 알림이 없어요.</T> : null}
      {groups.map((g, gi) => (
        <View key={g.key} style={{ paddingTop: gi ? 20 : 0 }}>
          <T style={{ color: C.muted, fontSize: 12, letterSpacing: 1 }}>{g.key}</T>
          {g.items.map((n) => (
            <Pressable
              key={n.id}
              onPress={() => open(n)}
              style={{
                flexDirection: 'row',
                gap: 14,
                paddingVertical: 16,
                borderBottomWidth: 1,
                borderBottomColor: C.line,
              }}
            >
              <View style={{ width: 8, height: 20, alignItems: 'center', justifyContent: 'center' }}>
                {n.read_at ? null : (
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.primaryText }} />
                )}
              </View>
              <View style={{ flex: 1, gap: 4 }}>
                <T style={{ fontSize: 15, color: n.read_at ? C.sub : C.text }}>{n.title}</T>
                <T style={{ color: C.muted, fontSize: 13 }}>{n.body}</T>
              </View>
              <T mono style={{ color: C.muted, fontSize: 12 }}>
                {clockText(n.created_at)}
              </T>
            </Pressable>
          ))}
        </View>
      ))}
    </Screen>
  );
}
