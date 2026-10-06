// 01.03 이메일 인증 안내
import { router, useLocalSearchParams } from 'expo-router';
import { Mail } from 'lucide-react-native';
import { useEffect, useState } from 'react';
import { Alert, Linking, View } from 'react-native';

import { BackBar, Button, EmptyHero, Screen, T, Title } from '@/components/ui';
import { C } from '@/constants/theme';
import { supabase } from '@/services/supabase';

const COOLDOWN = 60;

export default function Verify() {
  const { email } = useLocalSearchParams<{ email: string }>();
  const [left, setLeft] = useState(COOLDOWN);

  useEffect(() => {
    if (left <= 0) return;
    const t = setTimeout(() => setLeft(left - 1), 1000);
    return () => clearTimeout(t);
  }, [left]);

  async function resend() {
    const { error } = await supabase.auth.resend({ type: 'signup', email });
    if (error) return Alert.alert('다시 보내기 실패', error.message);
    setLeft(COOLDOWN);
  }

  return (
    <Screen
      scroll={false}
      footer={
        <>
          <Button label="메일 앱 열기" onPress={() => Linking.openURL('message://').catch(() => {})} />
          <Button
            kind="outline"
            label={left > 0 ? `인증 메일 다시 보내기 (${left}초)` : '인증 메일 다시 보내기'}
            onPress={resend}
            disabled={left > 0}
          />
          <Button kind="ghost" label="인증했어요 · 로그인하기" onPress={() => router.replace('/login')} />
        </>
      }
    >
      <BackBar onPress={() => router.replace('/login')} />
      <EmptyHero icon={Mail} size={40} />
      <View style={{ gap: 8, paddingTop: 4 }}>
        <Title>메일을 보냈어요</Title>
        <T style={{ color: C.sub, fontSize: 14, lineHeight: 21 }}>
          {email}으로 인증 링크를 보냈어요. 링크를 누르면 가입이 끝나요.
        </T>
      </View>
    </Screen>
  );
}
