// 07.01 내 차량 · 목록 (+ 07.03 삭제 확인)
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, View } from 'react-native';

import { Dialog } from '@/components/dialog';
import { BackBar, Button, Screen, T, Title } from '@/components/ui';
import { C } from '@/constants/theme';
import type { Vehicle } from '@/constants/types';
import { useStatus } from '@/hooks/useStatus';
import { api } from '@/services/api';

export default function Vehicles() {
  const { refresh } = useStatus();
  const [rows, setRows] = useState<Vehicle[] | null>(null);
  const [target, setTarget] = useState<Vehicle | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .vehicles()
      .then(setRows)
      .catch((e) => Alert.alert('불러오기 실패', e.message));
  }, []);
  useFocusEffect(load);

  async function remove() {
    if (!target) return;
    setBusy(true);
    try {
      await api.deleteVehicle(target.id);
      setTarget(null);
      load();
      refresh();
    } catch (e: any) {
      setTarget(null);
      Alert.alert('삭제할 수 없어요', e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen
      tabs
      contentStyle={{ gap: 20 }}
      footer={<Button kind="outline" label="차량 추가" onPress={() => router.push('/vehicle-new')} />}
    >
      <BackBar onPress={() => router.back()} />
      <Title eyebrow="차량">내 차량</Title>
      {rows === null ? <ActivityIndicator color={C.text} /> : null}
      {rows?.length === 0 ? <T style={{ color: C.sub, fontSize: 14 }}>등록된 차량이 없어요.</T> : null}
      <View>
        {rows?.map((v) => (
          <View key={v.id} style={{ gap: 14, paddingVertical: 18, borderBottomWidth: 1, borderBottomColor: C.line }}>
            <View style={{ gap: 4 }}>
              <T style={{ fontSize: 20 }}>{v.plate_no}</T>
              <T style={{ color: C.sub, fontSize: 13 }}>{[v.model, `${v.battery_kwh} kWh`].filter(Boolean).join(' · ')}</T>
            </View>
            {v.assigned ? null : (
              <T style={{ color: C.sub, fontSize: 13 }}>관리자가 차량을 배정하면 충전을 요청할 수 있어요.</T>
            )}
            <View style={{ flexDirection: 'row', gap: 20 }}>
              <Pressable onPress={() => router.push({ pathname: '/vehicle-edit', params: { id: v.id } })} hitSlop={8}>
                <T style={{ color: C.primaryText, fontSize: 14 }}>수정</T>
              </Pressable>
              <Pressable onPress={() => setTarget(v)} hitSlop={8}>
                <T style={{ color: C.muted, fontSize: 14 }}>삭제</T>
              </Pressable>
            </View>
          </View>
        ))}
      </View>
      <Dialog
        visible={!!target}
        title={`${target?.plate_no ?? ''}을 삭제할까요?`}
        body="차량과 충전 이력이 모두 지워지고 되돌릴 수 없어요. 진행 중인 충전 요청이 있으면 함께 취소돼요."
        keepLabel="유지"
        confirmLabel="삭제"
        loading={busy}
        onKeep={() => setTarget(null)}
        onConfirm={remove}
      />
    </Screen>
  );
}
