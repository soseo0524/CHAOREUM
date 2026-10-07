// 07.02 차량 수정
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, View } from 'react-native';

import { BackBar, Button, Field, Screen, T, Title } from '@/components/ui';
import { C } from '@/constants/theme';
import type { Vehicle } from '@/constants/types';
import { useStatus } from '@/hooks/useStatus';
import { api } from '@/services/api';

const PLATE = /^[0-9가-힣A-Za-z ]{4,12}$/; // 서버 PLATE_PATTERN과 같음

export default function VehicleEdit() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { refresh } = useStatus();
  const [v, setV] = useState<Vehicle | null>(null);
  const [plate, setPlate] = useState('');
  const [model, setModel] = useState('');
  const [battery, setBattery] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .vehicles()
      .then((rows) => {
        const x = rows.find((r) => r.id === id) ?? null;
        setV(x);
        if (x) {
          setPlate(x.plate_no);
          setModel(x.model ?? '');
          setBattery(String(x.battery_kwh));
        }
      })
      .catch((e) => Alert.alert('불러오기 실패', e.message));
  }, [id]);

  async function save() {
    if (!v) return;
    const kwh = Number(battery);
    if (!PLATE.test(plate.trim())) return Alert.alert('차량 번호', '차량 번호를 확인해 주세요. 예: 12가 3456');
    if (!(kwh > 0 && kwh <= 500)) return Alert.alert('배터리 용량', '배터리 용량(kWh)을 숫자로 입력해 주세요.');
    setBusy(true);
    try {
      await api.updateVehicle(v.id, {
        ...(plate.trim() !== v.plate_no ? { plate_no: plate.trim() } : {}),
        model: model.trim() || null,
        battery_kwh: kwh,
      });
      await refresh();
      router.back();
    } catch (e: any) {
      Alert.alert('저장 실패', e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen
        tabs
        contentStyle={{ gap: 14 }}
        footer={<Button label="저장하기" onPress={save} loading={busy} disabled={!v || !plate || !battery} />}
      >
        <BackBar onPress={() => router.back()} />
        <Title eyebrow="차량 정보">차량 수정</Title>
        <Field label="차량 번호" placeholder="12가 3456" value={plate} onChangeText={setPlate} />
        <Field label="모델" placeholder="예: 아이오닉 5" value={model} onChangeText={setModel} />
        <Field
          label="배터리 용량 (kWh)"
          placeholder="77.4"
          keyboardType="decimal-pad"
          value={battery}
          onChangeText={setBattery}
        />
        <View>
          <T style={{ color: C.sub, fontSize: 13, lineHeight: 20 }}>번호를 바꾸면 관리자가 배정을 다시 확인해요.</T>
        </View>
      </Screen>
    </KeyboardAvoidingView>
  );
}
