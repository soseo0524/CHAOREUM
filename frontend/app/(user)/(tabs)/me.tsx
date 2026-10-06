// 06.01 내 정보 (+ 06.04 로그아웃 확인)
import { ChevronRight } from 'lucide-react-native';
import { router } from 'expo-router';
import { Alert, Pressable, View } from 'react-native';

import { Button, Screen, T, Title } from '@/components/ui';
import { C } from '@/constants/theme';
import { useStatus } from '@/hooks/useStatus';
import { useAuth } from '@/services/auth';

export default function Me() {
  const { profile, session, signOut } = useAuth();
  const { status } = useStatus();
  const name = profile?.name ?? session?.user.user_metadata?.name ?? '사용자';
  const email = profile?.email ?? session?.user.email ?? '';
  const plates = status?.vehicles.map((v) => v.plate_no).join(', ') || '없음';
  const soon = () => Alert.alert('준비 중', '다음 단계에서 만들 화면이에요.');

  function logout() {
    Alert.alert('로그아웃할까요?', '', [
      { text: '취소', style: 'cancel' },
      { text: '로그아웃', style: 'destructive', onPress: signOut },
    ]);
  }

  return (
    <Screen
      tabs
      contentStyle={{ gap: 20 }}
      footer={
        <>
          <Button kind="ghost" label="로그아웃" onPress={logout} />
          <Pressable onPress={soon} style={{ height: 32, alignItems: 'center', justifyContent: 'center' }}>
            <T style={{ color: C.error, fontSize: 13 }}>회원 탈퇴</T>
          </Pressable>
        </>
      }
    >
      <Title eyebrow="계정">내 정보</Title>
      <View style={{ flexDirection: 'row', gap: 14, alignItems: 'center', paddingTop: 8, paddingBottom: 12 }}>
        <View
          style={{
            width: 56,
            height: 56,
            borderRadius: 28,
            backgroundColor: C.surface,
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <T style={{ fontSize: 22 }}>{name.slice(0, 1)}</T>
        </View>
        <View style={{ gap: 2 }}>
          <T style={{ fontSize: 18 }}>{name}</T>
          <T style={{ color: C.sub, fontSize: 13 }}>{email}</T>
        </View>
      </View>
      <View>
        <MenuRow label="내 차량" value={plates} />
        <MenuRow label="충전 이력" onPress={() => router.push('/history')} />
        <MenuRow label="알림 설정" onPress={soon} />
        <MenuRow label="위치·차량 위임 동의" value={profile?.consent_agreed ? '동의함' : '미동의'} />
        <MenuRow label="이용약관 · 개인정보 처리방침" onPress={soon} />
      </View>
    </Screen>
  );
}

function MenuRow({ label, value, onPress }: { label: string; value?: string; onPress?: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress}
      style={{
        height: 56,
        borderBottomWidth: 1,
        borderBottomColor: C.line,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}
    >
      <T style={{ fontSize: 15 }}>{label}</T>
      {value ? (
        <T style={{ color: C.sub, fontSize: 14 }}>{value}</T>
      ) : (
        <ChevronRight size={18} color={C.muted} />
      )}
    </Pressable>
  );
}
