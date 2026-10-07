// 06.02 프로필 수정
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, View } from 'react-native';

import { BackBar, Button, Field, Screen, T, Title } from '@/components/ui';
import { C } from '@/constants/theme';
import { api } from '@/services/api';
import { useAuth } from '@/services/auth';

export default function Profile() {
  const { profile, session, refreshProfile } = useAuth();
  const [name, setName] = useState(profile?.name ?? '');
  const [phone, setPhone] = useState(profile?.phone ?? '');
  const [busy, setBusy] = useState(false);

  async function save() {
    if (phone && !/^[0-9+\-]{8,20}$/.test(phone)) return Alert.alert('휴대전화', '번호를 확인해 주세요. 예: 010-0000-0000');
    setBusy(true);
    try {
      await api.updateMe({ name: name.trim() || undefined, phone: phone.trim() || undefined });
      await refreshProfile();
      router.back();
    } catch (e: any) {
      Alert.alert('저장 실패', e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen tabs contentStyle={{ gap: 14 }} footer={<Button label="저장하기" onPress={save} loading={busy} disabled={!name.trim()} />}>
        <BackBar onPress={() => router.back()} />
        <Title eyebrow="내 정보">프로필 수정</Title>
        <Field label="이름" placeholder="이름" value={name} onChangeText={setName} autoCapitalize="words" />
        <Field label="이메일" value={profile?.email ?? session?.user.email ?? ''} editable={false} />
        <Field
          label="휴대전화"
          placeholder="010-0000-0000"
          keyboardType="phone-pad"
          value={phone}
          onChangeText={setPhone}
        />
        <View>
          <T style={{ color: C.sub, fontSize: 13, lineHeight: 20 }}>이메일은 바꿀 수 없어요.</T>
        </View>
      </Screen>
    </KeyboardAvoidingView>
  );
}
