// 위치·차량 위임 동의 (내 정보에서 보기). 문구는 02.04 동의 시트와 같다.
import { router } from 'expo-router';
import { BatteryCharging, KeyRound, MapPin } from 'lucide-react-native';
import { useState } from 'react';
import { Alert, View } from 'react-native';

import { BackBar, Button, Screen, T, Title } from '@/components/ui';
import { C } from '@/constants/theme';
import { CONSENT_VERSION } from '@/constants/types';
import { api } from '@/services/api';
import { useAuth } from '@/services/auth';

export default function Consent() {
  const { profile, refreshProfile } = useAuth();
  const [busy, setBusy] = useState(false);
  const agreed = !!profile?.consent_agreed;

  async function agree() {
    setBusy(true);
    try {
      await api.consent(CONSENT_VERSION);
      await refreshProfile();
    } catch (e: any) {
      Alert.alert('동의 저장 실패', e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen tabs contentStyle={{ gap: 14 }} footer={agreed ? null : <Button label="동의하기" onPress={agree} loading={busy} />}>
      <BackBar onPress={() => router.back()} />
      <Title eyebrow="내 정보">위치·차량 위임 동의</Title>
      <T style={{ color: agreed ? C.success : C.warning, fontSize: 14 }}>
        {agreed ? `동의함 (${profile?.consent_version ?? CONSENT_VERSION})` : '아직 동의하지 않았어요'}
      </T>
      <T style={{ color: C.sub, fontSize: 13, lineHeight: 20 }}>
        충전과 주차를 위해 차량의 위치와 상태를 수집하고, 관제 시스템이 차량을 무인으로 이동·충전하도록 권한을 위임해요.
        요청이 끝나면 위치 수집도 멈춰요.
      </T>
      <View style={{ gap: 10, paddingTop: 4 }}>
        <Item icon={<MapPin size={16} color={C.text} />} text="차량 위치 · 주차 구역" />
        <Item icon={<BatteryCharging size={16} color={C.text} />} text="배터리 잔량 · 충전 상태" />
        <Item icon={<KeyRound size={16} color={C.text} />} text="차량 무인 이동·충전 권한 위임" />
      </View>
      <T style={{ color: C.muted, fontSize: 12, lineHeight: 18, paddingTop: 8 }}>
        동의 철회는 관제실에 문의해 주세요. 동의하지 않으면 충전을 요청할 수 없어요.
      </T>
    </Screen>
  );
}

function Item({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
      {icon}
      <T style={{ fontSize: 13 }}>{text}</T>
    </View>
  );
}
