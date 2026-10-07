// 09.03 새 비밀번호 입력 → 09.04 비밀번호 변경 완료
// 재설정 메일 링크가 '<앱 주소>/reset-password#access_token=…&refresh_token=…&type=recovery'로 앱을 연다.
import * as Linking from 'expo-linking';
import { router } from 'expo-router';
import { MailCheck } from 'lucide-react-native';
import { useEffect, useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, View } from 'react-native';

import { BackBar, Button, Field, Screen, T, Title } from '@/components/ui';
import { C } from '@/constants/theme';
import { useAuth } from '@/services/auth';
import { supabase } from '@/services/supabase';

function tokensFrom(url: string) {
  const raw = url.split('#')[1] ?? url.split('?')[1] ?? '';
  const p = new URLSearchParams(raw);
  return {
    access: p.get('access_token'),
    refresh: p.get('refresh_token'),
    error: p.get('error_description'),
  };
}

export default function ResetPassword() {
  const url = Linking.useURL();
  const { session, setRecovering, signOut } = useAuth();
  const [linkError, setLinkError] = useState<string | null>(null);
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!url) return;
    const t = tokensFrom(url);
    if (t.error) return setLinkError(t.error.replace(/\+/g, ' '));
    if (!t.access || !t.refresh) return;
    setRecovering(true); // 세션이 생겨도 홈으로 넘어가지 않게 먼저 표시
    supabase.auth.setSession({ access_token: t.access, refresh_token: t.refresh }).then(({ error }) => {
      if (error) {
        setRecovering(false);
        setLinkError('링크가 만료됐어요. 재설정 메일을 다시 받아 주세요.');
      }
    });
  }, [url]); // eslint-disable-line react-hooks/exhaustive-deps

  async function change() {
    if (pw.length < 8 || !/[A-Za-z]/.test(pw) || !/[0-9]/.test(pw))
      return Alert.alert('새 비밀번호', '8자 이상, 영문과 숫자를 함께 써 주세요.');
    if (pw !== pw2) return Alert.alert('새 비밀번호', '비밀번호가 서로 달라요.');
    setBusy(true);
    const { error } = await supabase.auth.updateUser({ password: pw });
    setBusy(false);
    if (error) return Alert.alert('변경 실패', error.message);
    setDone(true);
  }

  async function toLogin() {
    if (session) await supabase.auth.signOut({ scope: 'global' }).catch(() => signOut());
    setRecovering(false);
    router.replace('/login');
  }

  if (done) {
    return (
      <Screen scroll={false} footer={<Button label="로그인하기" onPress={toLogin} />}>
        <BackBar onPress={toLogin} />
        <View style={{ height: 110, backgroundColor: C.hero, borderRadius: 8, alignItems: 'center', justifyContent: 'center' }}>
          <MailCheck size={40} color={C.success} />
        </View>
        <View style={{ gap: 8, paddingTop: 4 }}>
          <Title>비밀번호를 바꿨어요</Title>
          <T style={{ color: C.sub, fontSize: 14, lineHeight: 21 }}>
            새 비밀번호로 로그인해 주세요. 다른 기기는 모두 로그아웃돼요.
          </T>
        </View>
      </Screen>
    );
  }

  const ready = !!session && !linkError;
  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen
        contentStyle={{ gap: 16 }}
        footer={<Button label="비밀번호 변경하기" onPress={change} loading={busy} disabled={!ready || !pw || !pw2} />}
      >
        <BackBar onPress={toLogin} />
        <View style={{ gap: 8, paddingTop: 4, paddingBottom: 12 }}>
          <Title>새 비밀번호 설정</Title>
          <T style={{ color: linkError ? C.error : C.sub, fontSize: 14, lineHeight: 21 }}>
            {linkError ?? (ready ? '8자 이상, 영문과 숫자를 함께 써 주세요.' : '재설정 링크를 확인하는 중이에요…')}
          </T>
        </View>
        <Field label="새 비밀번호" placeholder="8자 이상" secure value={pw} onChangeText={setPw} />
        <Field label="새 비밀번호 확인" placeholder="한 번 더 입력" secure value={pw2} onChangeText={setPw2} />
      </Screen>
    </KeyboardAvoidingView>
  );
}
