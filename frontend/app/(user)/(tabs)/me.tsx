// 06.01 내 정보 (+ 06.04 로그아웃 확인, 06.05 회원 탈퇴 확인)
import { router } from 'expo-router';
import { ChevronRight } from 'lucide-react-native';
import { useState } from 'react';
import { Alert, Pressable, View } from 'react-native';

import { Dialog } from '@/components/dialog';
import { Button, Screen, T, Title } from '@/components/ui';
import { C } from '@/constants/theme';
import { useStatus } from '@/hooks/useStatus';
import { api } from '@/services/api';
import { useAuth } from '@/services/auth';

export default function Me() {
  const { profile, session, signOut } = useAuth();
  const { status } = useStatus();
  const [dialog, setDialog] = useState<'logout' | 'withdraw' | null>(null);
  const [busy, setBusy] = useState(false);
  const name = profile?.name ?? session?.user.user_metadata?.name ?? '사용자';
  const email = profile?.email ?? session?.user.email ?? '';
  const plates = status?.vehicles.map((v) => v.plate_no).join(', ') || '없음';

  async function withdraw() {
    setBusy(true);
    try {
      await api.withdraw();
      setDialog(null);
      await signOut();
    } catch (e: any) {
      setDialog(null);
      Alert.alert('탈퇴할 수 없어요', e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen
      tabs
      contentStyle={{ gap: 20 }}
      footer={
        <>
          <Button kind="ghost" label="로그아웃" onPress={() => setDialog('logout')} />
          <Pressable
            onPress={() => setDialog('withdraw')}
            style={{ height: 32, alignItems: 'center', justifyContent: 'center' }}
          >
            <T style={{ color: C.error, fontSize: 13 }}>회원 탈퇴</T>
          </Pressable>
        </>
      }
    >
      <Title eyebrow="계정">내 정보</Title>
      <Pressable
        onPress={() => router.push('/profile')}
        style={{ flexDirection: 'row', gap: 14, alignItems: 'center', paddingTop: 8, paddingBottom: 12 }}
      >
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
        <View style={{ gap: 2, flex: 1 }}>
          <T style={{ fontSize: 18 }}>{name}</T>
          <T style={{ color: C.sub, fontSize: 13 }}>{email}</T>
        </View>
        <ChevronRight size={18} color={C.muted} />
      </Pressable>
      <View>
        <MenuRow label="내 차량" value={plates} onPress={() => router.push('/vehicles')} />
        <MenuRow label="충전 이력" onPress={() => router.push('/history')} />
        <MenuRow label="알림 설정" onPress={() => router.push('/notification-settings')} />
        <MenuRow label="위치·차량 위임 동의" onPress={() => router.push('/consent')} />
        <MenuRow label="이용약관 · 개인정보 처리방침" onPress={() => router.push('/terms')} />
      </View>

      <Dialog
        visible={dialog === 'logout'}
        title="로그아웃할까요?"
        body="진행 중인 충전 요청은 그대로 이어져요. 다시 로그인하면 현황을 볼 수 있어요."
        confirmLabel="로그아웃"
        onKeep={() => setDialog(null)}
        onConfirm={() => (setDialog(null), signOut())}
      />
      <Dialog
        visible={dialog === 'withdraw'}
        title="정말 탈퇴할까요?"
        body="차량 정보와 충전 이력이 모두 삭제되고 되돌릴 수 없어요. 진행 중인 요청이 있으면 먼저 취소해야 해요."
        confirmLabel="탈퇴"
        loading={busy}
        onKeep={() => setDialog(null)}
        onConfirm={withdraw}
      />
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
