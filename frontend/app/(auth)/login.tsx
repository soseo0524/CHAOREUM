// 01.01 로그인
import { Link } from 'expo-router';
import { useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, View } from 'react-native';

import { Button, Field, Screen, T, Wordmark } from '@/components/ui';
import { C } from '@/constants/theme';
import { supabase, supabaseConfigured } from '@/services/supabase';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  async function onLogin() {
    if (!supabaseConfigured) {
      Alert.alert('설정 필요', 'frontend/.env 에 Supabase Publishable key를 넣고 앱을 다시 시작해 주세요.');
      return;
    }
    setBusy(true);
    const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    setBusy(false);
    if (error) {
      const msg = error.message.includes('Email not confirmed')
        ? '메일 인증이 아직 안 됐어요. 받은 메일의 링크를 눌러 주세요.'
        : '이메일 또는 비밀번호가 맞지 않아요.';
      Alert.alert('로그인 실패', msg);
    }
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen contentStyle={{ gap: 56, paddingTop: 12 }}>
        <Wordmark />
        <View style={{ gap: 16 }}>
          <T style={{ fontSize: 40, letterSpacing: -1.2, lineHeight: 48 }}>{'충전부터\n주차까지 알아서.'}</T>
          <T style={{ color: C.sub, fontSize: 14, lineHeight: 22 }}>
            {'차량을 맡기면 충전 후 주차까지\n자동으로 완료해드려요.'}
          </T>
        </View>
        <View style={{ gap: 12 }}>
          <Field
            label="이메일"
            placeholder="name@example.com"
            keyboardType="email-address"
            autoComplete="email"
            value={email}
            onChangeText={setEmail}
          />
          <Field label="비밀번호" placeholder="비밀번호" secure value={password} onChangeText={setPassword} />
          <Button label="로그인" onPress={onLogin} loading={busy} disabled={!email || !password} style={{ marginTop: 8 }} />
          <View style={{ flexDirection: 'row', gap: 6, justifyContent: 'center', paddingTop: 8 }}>
            <T style={{ color: C.sub, fontSize: 13 }}>계정이 없나요?</T>
            <Link href="/signup">
              <T style={{ fontSize: 13 }}>회원가입</T>
            </Link>
          </View>
          <Link href="/forgot" style={{ alignSelf: 'center' }}>
            <T style={{ color: C.sub, fontSize: 12 }}>비밀번호를 잊었나요?</T>
          </Link>
          <T style={{ color: C.muted, fontSize: 11, textAlign: 'center' }}>관리자는 웹사이트에서 이용해 주세요.</T>
        </View>
      </Screen>
    </KeyboardAvoidingView>
  );
}
