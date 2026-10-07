// 09.01 비밀번호 재설정
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, Pressable, View } from 'react-native';

import { BackBar, Button, Field, Screen, T, Title } from '@/components/ui';
import { C } from '@/constants/theme';
import { sendResetMail } from '@/services/supabase';

export default function Forgot() {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);

  async function send() {
    setBusy(true);
    const { error } = await sendResetMail(email.trim());
    setBusy(false);
    if (error) return Alert.alert('메일을 보내지 못했어요', error.message);
    router.replace({ pathname: '/forgot-sent', params: { email: email.trim() } });
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen
        footer={
          <>
            <Button label="재설정 메일 보내기" onPress={send} loading={busy} disabled={!email.includes('@')} />
            <View style={{ flexDirection: 'row', gap: 6, justifyContent: 'center', paddingVertical: 6 }}>
              <T style={{ color: C.sub, fontSize: 13 }}>기억났나요?</T>
              <Pressable onPress={() => router.back()}>
                <T style={{ color: C.primaryText, fontSize: 13 }}>로그인</T>
              </Pressable>
            </View>
          </>
        }
      >
        <BackBar onPress={() => router.back()} />
        <View style={{ gap: 8, paddingTop: 4, paddingBottom: 12 }}>
          <Title>비밀번호 재설정</Title>
          <T style={{ color: C.sub, fontSize: 14, lineHeight: 21 }}>
            가입한 이메일을 입력하면 재설정 링크를 보내 드려요.
          </T>
        </View>
        <Field
          label="이메일"
          placeholder="name@example.com"
          keyboardType="email-address"
          value={email}
          onChangeText={setEmail}
        />
      </Screen>
    </KeyboardAvoidingView>
  );
}
