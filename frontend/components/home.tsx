// 홈 화면(03.xx) 조각: 차량 사진, 수치, SOC 막대, 진행 단계, 배너
import { Bell, Check, Map as MapIcon, TriangleAlert, WifiOff } from 'lucide-react-native';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert, Image, Linking, Pressable, StyleSheet, View } from 'react-native';

import { C } from '@/constants/theme';
import { api } from '@/services/api';
import { T, Wordmark } from './ui';

/** 로고 + 알림함(08.01) 버튼. 안 읽은 알림이 있으면 점을 찍는다 */
export function TopBar() {
  const [unread, setUnread] = useState(false);
  useFocusEffect(
    useCallback(() => {
      api
        .notifications()
        .then((rows) => setUnread(rows.some((n) => !n.read_at)))
        .catch(() => {});
    }, []),
  );
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
      <Wordmark />
      <Pressable onPress={() => router.push('/notifications')} hitSlop={12}>
        <Bell size={22} color={C.text} />
        {unread ? <View style={s.unread} /> : null}
      </Pressable>
    </View>
  );
}

/** 관제 문의: EXPO_PUBLIC_SUPPORT_PHONE이 있으면 전화를 건다 */
export function contactCenter() {
  const tel = process.env.EXPO_PUBLIC_SUPPORT_PHONE;
  if (tel) Linking.openURL(`tel:${tel}`).catch(() => {});
  else Alert.alert('관제 문의', '관제실 연락처가 아직 등록되지 않았어요. 관리자에게 문의해 주세요.');
}

export function CarHero({ height = 160, onMap }: { height?: number; onMap?: () => void }) {
  return (
    <View style={[s.hero, { height }]}>
      <Image
        source={require('@/assets/car.png')}
        style={{ width: height === 160 ? 260 : 200, height: height - 10 }}
        resizeMode="contain"
      />
      <Pressable style={s.chip} onPress={onMap} disabled={!onMap} hitSlop={6}>
        <MapIcon size={14} color={C.text} />
        <T style={{ fontSize: 12 }}>전체 구역 선택</T>
      </Pressable>
    </View>
  );
}

export function StatusBlock({ plate, title, color = C.text }: { plate: string; title: string; color?: string }) {
  return (
    <View style={{ gap: 6 }}>
      <T style={{ color: C.sub, fontSize: 13 }}>{plate}</T>
      <T style={{ color, fontSize: 34, letterSpacing: -1.2, lineHeight: 44 }}>{title}</T>
    </View>
  );
}

export type MetricItem = { label: string; value: string; unit?: string };
export function MetricRow({ items }: { items: MetricItem[] }) {
  return (
    <View style={{ flexDirection: 'row' }}>
      {items.map((m) => (
        <View key={m.label} style={{ flex: 1, gap: 4 }}>
          <T style={{ color: C.sub, fontSize: 12 }}>{m.label}</T>
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 3 }}>
            <T mono style={{ fontSize: 26, letterSpacing: -1 }}>
              {m.value}
            </T>
            {m.unit ? (
              <T mono style={{ color: C.sub, fontSize: 12, paddingBottom: 5 }}>
                {m.unit}
              </T>
            ) : null}
          </View>
        </View>
      ))}
    </View>
  );
}

export function SocBar({ soc, target }: { soc: number | null; target?: number | null }) {
  return (
    <View style={s.track}>
      <View style={[s.fill, { width: `${Math.max(0, Math.min(100, soc ?? 0))}%` }]} />
      {target != null ? <View style={[s.mark, { left: `${target}%` }]} /> : null}
    </View>
  );
}

export type Step = { title: string; sub?: string; status: 'done' | 'current' | 'todo' };
export function Steps({ eyebrow = '진행 상황', steps }: { eyebrow?: string; steps: Step[] }) {
  return (
    <View style={{ gap: 10, paddingTop: 14 }}>
      <T style={{ color: C.sub, fontSize: 12, letterSpacing: 1 }}>{eyebrow}</T>
      {steps.map((st, i) => (
        <View key={st.title} style={{ flexDirection: 'row', gap: 14 }}>
          <View style={{ alignItems: 'center' }}>
            {st.status === 'done' ? (
              <View style={[s.node, { backgroundColor: C.text }]}>
                <Check size={11} color="#000000" strokeWidth={3} />
              </View>
            ) : st.status === 'current' ? (
              <View style={[s.node, { borderWidth: 1, borderColor: C.warning }]}>
                <View style={s.dot} />
              </View>
            ) : (
              <View style={[s.node, { borderWidth: 1, borderColor: C.line }]} />
            )}
            {i < steps.length - 1 ? <View style={s.connector} /> : null}
          </View>
          <View style={{ flexDirection: 'row', gap: 8, height: 18, alignItems: 'center', flex: 1 }}>
            <T style={{ fontSize: 14, color: st.status === 'todo' ? C.muted : C.text }}>{st.title}</T>
            {st.sub ? (
              <T numberOfLines={1} style={{ color: C.sub, fontSize: 12, flexShrink: 1 }}>
                {st.sub}
              </T>
            ) : null}
          </View>
        </View>
      ))}
    </View>
  );
}

export function Banner({
  title,
  sub,
  action,
  actionColor = C.primaryText,
  onAction,
}: {
  title: string;
  sub: string;
  action?: string;
  actionColor?: string;
  onAction?: () => void;
}) {
  return (
    <View style={s.banner}>
      <WifiOff size={18} color={C.warning} />
      <View style={{ flex: 1, gap: 2 }}>
        <T style={{ fontSize: 14 }}>{title}</T>
        <T style={{ color: C.sub, fontSize: 12 }}>{sub}</T>
      </View>
      {action ? (
        <Pressable onPress={onAction} hitSlop={10}>
          <T style={{ color: actionColor, fontSize: 13 }}>{action}</T>
        </Pressable>
      ) : null}
    </View>
  );
}

/** 요청 실패·차량 이상 화면의 '사유/상황' 블록 */
export function Notice({ eyebrow, body, sub, alert }: { eyebrow: string; body: string; sub: string; alert?: boolean }) {
  return (
    <View style={{ gap: 10, paddingTop: 14 }}>
      <T style={{ color: C.sub, fontSize: 12, letterSpacing: 1 }}>{eyebrow}</T>
      <View style={{ flexDirection: 'row', gap: 10 }}>
        {alert ? <TriangleAlert size={18} color={C.error} /> : null}
        <T style={{ fontSize: 14, lineHeight: 21, flex: 1 }}>{body}</T>
      </View>
      <T style={{ color: C.sub, fontSize: 12, lineHeight: 18 }}>{sub}</T>
    </View>
  );
}

const s = StyleSheet.create({
  unread: { position: 'absolute', top: 0, right: 0, width: 7, height: 7, borderRadius: 4, backgroundColor: C.primaryText },
  hero: { backgroundColor: C.hero, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  chip: {
    position: 'absolute',
    right: 12,
    bottom: 12,
    flexDirection: 'row',
    gap: 6,
    alignItems: 'center',
    backgroundColor: C.surface,
    borderRadius: 980,
    paddingVertical: 7,
    paddingHorizontal: 12,
  },
  track: { height: 4, backgroundColor: C.line, borderRadius: 2 },
  fill: { position: 'absolute', left: 0, top: 0, height: 4, backgroundColor: C.primary, borderRadius: 2 },
  mark: { position: 'absolute', top: -4, width: 2, height: 12, backgroundColor: C.text },
  node: { width: 18, height: 18, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: C.warning },
  connector: { width: 1, height: 16, backgroundColor: C.line },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: C.surface,
    borderRadius: 8,
    paddingVertical: 12,
    paddingHorizontal: 14,
  },
});
