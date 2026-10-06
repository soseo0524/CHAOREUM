// 01.02 회원가입
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, Pressable, View } from 'react-native';

import { BackBar, Button, Checkbox, Field, Screen, T, Title } from '@/components/ui';
import { C } from '@/constants/theme';
import { supabase } from '@/services/supabase';

export default function Signup() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSignup() {
    if (pw.length < 8) return Alert.alert('비밀번호', '비밀번호는 8자 이상이어야 해요.');
    if (pw !== pw2) return Alert.alert('비밀번호', '비밀번호가 서로 달라요.');
    setBusy(true);
    const { data, error } = await supabase.auth.signUp({
      email: email.trim(),
      password: pw,
      options: { data: { name: name.trim() } },
    });
    setBusy(false);
    if (error) return Alert.alert('가입 실패', error.message);
    // 메일 인증이 꺼진 프로젝트면 바로 세션이 생겨 홈으로 간다
    if (!data.session) router.replace({ pathname: '/verify', params: { email: email.trim() } });
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen
        footer={
          <>
            <Button
              label="가입하기"
              onPress={onSignup}
              loading={busy}
              disabled={!name || !email || !pw || !pw2 || !agree}
            />
            <View style={{ flexDirection: 'row', gap: 6, justifyContent: 'center', paddingVertical: 6 }}>
              <T style={{ color: C.sub, fontSize: 13 }}>이미 계정이 있나요?</T>
              <Pressable onPress={() => router.back()}>
                <T style={{ color: C.primaryText, fontSize: 13 }}>로그인</T>
              </Pressable>
            </View>
          </>
        }
      >
        <BackBar onPress={() => router.back()} />
        <View style={{ paddingTop: 4, paddingBottom: 12 }}>
          <Title>계정 만들기</Title>
        </View>
        <Field label="이름" placeholder="이름" value={name} onChangeText={setName} autoCapitalize="words" />
        <Field
          label="이메일"
          placeholder="name@example.com"
          keyboardType="email-address"
          value={email}
          onChangeText={setEmail}
        />
        <Field label="비밀번호" placeholder="8자 이상" secure value={pw} onChangeText={setPw} />
        <Field label="비밀번호 확인" placeholder="한 번 더 입력" secure value={pw2} onChangeText={setPw2} />
        <View style={{ paddingTop: 6 }}>
          <Checkbox
            checked={agree}
            onPress={() => setAgree(!agree)}
            label="이용약관 및 개인정보 처리방침에 동의합니다. (필수)"
          />
        </View>
      </Screen>
    </KeyboardAvoidingView>
  );
}
