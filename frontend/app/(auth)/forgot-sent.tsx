// 09.02 재설정 메일 발송
import { router, useLocalSearchParams } from 'expo-router';
import { MailCheck } from 'lucide-react-native';
import { useState } from 'react';
import { Alert, View } from 'react-native';

import { BackBar, Button, Screen, T, Title } from '@/components/ui';
import { C } from '@/constants/theme';
import { sendResetMail } from '@/services/supabase';

export default function ForgotSent() {
  const { email } = useLocalSearchParams<{ email: string }>();
  const [busy, setBusy] = useState(false);

  async function resend() {
    setBusy(true);
    const { error } = await sendResetMail(email);
    setBusy(false);
    Alert.alert(error ? '메일을 보내지 못했어요' : '다시 보냈어요', error?.message ?? `${email}을 확인해 주세요.`);
  }

  return (
    <Screen
      scroll={false}
      footer={
        <>
          <Button label="로그인으로" onPress={() => router.replace('/login')} />
          <Button kind="outline" label="메일 다시 보내기" onPress={resend} loading={busy} />
        </>
      }
    >
      <BackBar onPress={() => router.replace('/login')} />
      <View style={{ height: 110, backgroundColor: C.hero, borderRadius: 8, alignItems: 'center', justifyContent: 'center' }}>
        <MailCheck size={40} color={C.success} />
      </View>
      <View style={{ gap: 8, paddingTop: 4 }}>
        <Title>메일을 확인해 주세요</Title>
        <T style={{ color: C.sub, fontSize: 14, lineHeight: 21 }}>
          재설정 링크를 보냈어요. 메일이 안 보이면 스팸함을 확인해 주세요. 링크는 30분 동안 유효해요.
        </T>
      </View>
    </Screen>
  );
}
