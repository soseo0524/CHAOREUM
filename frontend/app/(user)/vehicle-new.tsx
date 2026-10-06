// 01.05 차량 등록
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, View } from 'react-native';

import { BackBar, Button, Field, Screen, T, Title } from '@/components/ui';
import { C } from '@/constants/theme';
import { useStatus } from '@/hooks/useStatus';
import { api } from '@/services/api';

const PLATE = /^[0-9가-힣A-Za-z ]{4,12}$/; // 서버 PLATE_PATTERN과 같음
const DEFAULT_MAX_CHARGE_KW = 11; // 디자인에 입력칸이 없어 충전기 출력(11 kW)을 기본값으로 보낸다

export default function VehicleNew() {
  const { refresh } = useStatus();
  const [plate, setPlate] = useState('');
  const [model, setModel] = useState('');
  const [battery, setBattery] = useState('');
  const [busy, setBusy] = useState(false);

  async function onSubmit() {
    const kwh = Number(battery);
    if (!PLATE.test(plate.trim())) return Alert.alert('차량 번호', '차량 번호를 확인해 주세요. 예: 12가 3456');
    if (!(kwh > 0 && kwh <= 500)) return Alert.alert('배터리 용량', '배터리 용량(kWh)을 숫자로 입력해 주세요.');
    setBusy(true);
    try {
      await api.createVehicle({
        plate_no: plate.trim(),
        model: model.trim() || null,
        battery_kwh: kwh,
        max_charge_kw: DEFAULT_MAX_CHARGE_KW,
      });
      await refresh();
      router.back();
    } catch (e: any) {
      Alert.alert('등록 실패', e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen
        contentStyle={{ gap: 14 }}
        footer={<Button label="등록하기" onPress={onSubmit} loading={busy} disabled={!plate || !battery} />}
      >
        <BackBar onPress={() => router.back()} />
        <Title eyebrow="새 차량">차량 등록</Title>
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
          <T style={{ color: C.sub, fontSize: 13, lineHeight: 20 }}>
            등록하면 관리자가 차량을 배정해요. 배정이 끝나면 알려 드릴게요.
          </T>
        </View>
      </Screen>
    </KeyboardAvoidingView>
  );
}
