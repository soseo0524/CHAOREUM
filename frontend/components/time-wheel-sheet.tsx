// 02.01-A 주차 완료 시각 선택 — 아이폰 시간 설정처럼 돌려서 고르는 아래 시트
import { useEffect, useRef, useState } from 'react';
import { Modal, Pressable, ScrollView, View, type NativeScrollEvent, type NativeSyntheticEvent } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { dayClock } from '@/constants/format';
import { C } from '@/constants/theme';
import { Button, T } from './ui';

const ROW = 40;
const H = 220;
const SIZE = [22, 20, 18, 16];
const OPACITY = [1, 0.55, 0.3, 0.14];
const AMPM = ['오전', '오후'];
const HOURS = Array.from({ length: 12 }, (_, i) => String(i + 1));
const MINUTES = Array.from({ length: 12 }, (_, i) => String(i * 5).padStart(2, '0'));

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

function Wheel({
  items,
  index,
  onIndex,
  unit,
}: {
  items: string[];
  index: number;
  onIndex: (i: number) => void;
  unit?: string;
}) {
  const ref = useRef<ScrollView>(null);
  const [cur, setCur] = useState(index);

  useEffect(() => {
    // 처음 열릴 때 현재 값 위치로 맞춘다
    const t = setTimeout(() => ref.current?.scrollTo({ y: index * ROW, animated: false }), 0);
    return () => clearTimeout(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const at = (e: NativeSyntheticEvent<NativeScrollEvent>) =>
    clamp(Math.round(e.nativeEvent.contentOffset.y / ROW), 0, items.length - 1);

  return (
    <View style={{ flex: 1, height: H }}>
      <ScrollView
        ref={ref}
        showsVerticalScrollIndicator={false}
        snapToInterval={ROW}
        decelerationRate="fast"
        scrollEventThrottle={16}
        onScroll={(e) => setCur(at(e))}
        onMomentumScrollEnd={(e) => onIndex(at(e))}
        onScrollEndDrag={(e) => onIndex(at(e))}
        contentContainerStyle={{ paddingVertical: (H - ROW) / 2 }}
      >
        {items.map((t, i) => {
          const d = Math.min(Math.abs(i - cur), 3);
          return (
            <Pressable
              key={t}
              onPress={() => {
                ref.current?.scrollTo({ y: i * ROW, animated: true });
                setCur(i);
                onIndex(i);
              }}
              style={{ height: ROW, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, opacity: OPACITY[d] }}
            >
              <T medium={d === 0} style={{ fontSize: SIZE[d] }}>
                {t}
              </T>
              {d === 0 && unit ? (
                <T medium style={{ fontSize: 16 }}>
                  {unit}
                </T>
              ) : null}
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

function build(day: number, ap: number, hi: number, mi: number): Date {
  const d = new Date();
  d.setDate(d.getDate() + day);
  d.setHours(((hi + 1) % 12) + (ap ? 12 : 0), mi * 5, 0, 0);
  return d;
}

function dayDiff(d: Date): number {
  const t = new Date();
  const a = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const b = new Date(t.getFullYear(), t.getMonth(), t.getDate()).getTime();
  return clamp(Math.round((a - b) / 86400000), 0, 1);
}

export function TimeWheelSheet({
  visible,
  value,
  onClose,
  onDone,
}: {
  visible: boolean;
  value: Date;
  onClose: () => void;
  onDone: (d: Date) => void;
}) {
  const insets = useSafeAreaInsets();
  const [day, setDay] = useState(0);
  const [ap, setAp] = useState(1);
  const [hi, setHi] = useState(5);
  const [mi, setMi] = useState(6);
  const [round, setRound] = useState(0); // 열 때마다 휠을 새로 만든다

  useEffect(() => {
    if (!visible) return;
    const h = value.getHours();
    setDay(dayDiff(value));
    setAp(h >= 12 ? 1 : 0);
    setHi((h % 12 || 12) - 1);
    setMi(clamp(Math.round(value.getMinutes() / 5), 0, 11));
    setRound((r) => r + 1);
  }, [visible]); // eslint-disable-line react-hooks/exhaustive-deps

  const picked = build(day, ap, hi, mi);
  const past = picked.getTime() <= Date.now();

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={{ flex: 1, backgroundColor: '#000000A0' }} onPress={onClose} />
      <View
        style={{
          backgroundColor: '#151517',
          borderTopLeftRadius: 26,
          borderTopRightRadius: 26,
          paddingHorizontal: 24,
          paddingTop: 8,
          paddingBottom: Math.max(insets.bottom, 16) + 12,
          gap: 14,
        }}
      >
        <View style={{ alignItems: 'center' }}>
          <View style={{ width: 38, height: 5, borderRadius: 3, backgroundColor: '#48484a' }} />
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', height: 32 }}>
          <Pressable onPress={onClose} hitSlop={10}>
            <T style={{ color: C.sub, fontSize: 15 }}>취소</T>
          </Pressable>
          <T medium style={{ fontSize: 17 }}>
            주차 완료 시각
          </T>
          <Pressable onPress={() => !past && onDone(picked)} hitSlop={10} disabled={past}>
            <T medium style={{ color: C.active, fontSize: 15, opacity: past ? 0.4 : 1 }}>
              완료
            </T>
          </Pressable>
        </View>

        <View style={{ flexDirection: 'row', gap: 8 }}>
          {['오늘', '내일'].map((label, i) => (
            <Pressable
              key={label}
              onPress={() => setDay(i)}
              style={{
                height: 32,
                paddingHorizontal: 16,
                borderRadius: 16,
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: day === i ? '#ffffff' : '#2c2c2e',
              }}
            >
              <T medium style={{ color: day === i ? '#000000' : C.sub, fontSize: 13 }}>
                {label}
              </T>
            </Pressable>
          ))}
        </View>

        <View style={{ height: H }}>
          <View
            pointerEvents="none"
            style={{
              position: 'absolute',
              left: 0,
              right: 0,
              top: (H - ROW) / 2,
              height: ROW,
              borderRadius: ROW / 2,
              backgroundColor: '#2c2c2e',
            }}
          />
          <View style={{ flexDirection: 'row' }} key={round}>
            <Wheel items={AMPM} index={ap} onIndex={setAp} />
            <Wheel items={HOURS} index={hi} onIndex={setHi} unit="시" />
            <Wheel items={MINUTES} index={mi} onIndex={setMi} unit="분" />
          </View>
        </View>

        <T style={{ color: past ? C.warning : C.sub, fontSize: 13, textAlign: 'center' }}>
          {past ? '지금보다 나중 시각을 골라 주세요' : `${dayClock(picked)}까지 주차 완료`}
        </T>
        <Button label="이 시각으로 설정" onPress={() => onDone(picked)} disabled={past} />
      </View>
    </Modal>
  );
}
