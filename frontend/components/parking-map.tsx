// 02.02 전체 지도(손가락으로 확대·이동해서 구역 고르기) → 02.03 구역 안 맵(자리 고르기)
// 고른 자리의 zone_id(PARKING_nn)를 onPick으로 돌려준다. 자동 배정은 null.
import { ChevronLeft, LogIn, Minus, Plus, X } from 'lucide-react-native';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Image, Modal, PanResponder, Pressable, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { C } from '@/constants/theme';
import type { AreaDetail, AreaSummary, AreasOut } from '@/constants/types';
import { api } from '@/services/api';
import { Button, T } from './ui';

const CAR = require('@/assets/car-top.png');
const CAR_RATIO = 377 / 869; // 가로/세로
const WORLD = { w: 340, h: 470 };
// 전체 지도 안에서 구역 위치(앱 안 지도 배치. 실제 주차장 좌표가 정해지면 여기만 고친다)
const LAYOUT: Record<string, { x: number; y: number; w: number; h: number }> = {
  A: { x: 16, y: 24, w: 150, h: 170 },
  B: { x: 174, y: 24, w: 150, h: 170 },
  C: { x: 16, y: 250, w: 308, h: 150 },
};
const SEAT_COLOR = { FREE: '#e5e5e5', TAKEN: '#4a4a4a', MINE: C.active } as const;
const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

type Tf = { x: number; y: number; s: number };

export function ParkingMap({
  visible,
  selected,
  onClose,
  onPick,
}: {
  visible: boolean;
  selected: string | null;
  onClose: () => void;
  onPick: (zoneId: string | null) => void;
}) {
  const insets = useSafeAreaInsets();
  const [areas, setAreas] = useState<AreasOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null); // 전체 지도에서 눌러 둔 구역
  const [areaId, setAreaId] = useState<string | null>(null); // 들어간 구역
  const [seat, setSeat] = useState<string | null>(selected);

  useEffect(() => {
    if (!visible) return;
    setAreaId(null);
    setPending(null);
    setSeat(selected);
    setError(null);
    setAreas(null);
    api
      .parkingAreas()
      .then(setAreas)
      .catch((e) => setError(e.message));
  }, [visible]); // eslint-disable-line react-hooks/exhaustive-deps

  const current = areas?.areas.find((a) => a.area_id === pending) ?? null;

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={areaId ? () => setAreaId(null) : onClose}>
      <View style={{ flex: 1, backgroundColor: C.bg, paddingTop: insets.top + 4, paddingBottom: Math.max(insets.bottom, 16) }}>
        {areaId ? (
          <AreaInside
            areaId={areaId}
            seat={seat}
            onSeat={setSeat}
            onBack={() => setAreaId(null)}
            onConfirm={(z) => onPick(z)}
          />
        ) : (
          <>
            <View style={{ paddingHorizontal: 24, gap: 6, paddingBottom: 12 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <T style={{ color: C.sub, fontSize: 12, letterSpacing: 1 }}>주차 구역</T>
                <Pressable onPress={onClose} hitSlop={12}>
                  <X size={22} color={C.text} />
                </Pressable>
              </View>
              <T style={{ fontSize: 28, letterSpacing: -1 }}>구역을 골라 주세요</T>
              <T style={{ color: C.sub, fontSize: 13 }}>손가락으로 확대하고 움직여서 구역을 눌러 보세요.</T>
            </View>

            <View style={{ flex: 1, marginHorizontal: 16, borderRadius: 12, overflow: 'hidden', backgroundColor: C.hero }}>
              {areas ? (
                <ZoomMap areas={areas.areas} pending={pending} onPick={setPending} />
              ) : error ? (
                <T style={{ color: C.error, fontSize: 13, padding: 24 }}>{error}</T>
              ) : (
                <ActivityIndicator color={C.text} style={{ marginTop: 80 }} />
              )}
            </View>

            <View style={{ paddingHorizontal: 24, paddingTop: 14, gap: 10 }}>
              {current ? (
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                  <T style={{ fontSize: 17 }}>{current.name}</T>
                  <T mono style={{ color: current.state === 'FULL' ? C.error : C.sub, fontSize: 13 }}>
                    {current.state === 'FULL' ? '가득 찼어요' : `빈자리 ${current.free_count} / ${current.seat_total}`}
                  </T>
                </View>
              ) : (
                <T style={{ color: C.muted, fontSize: 13 }}>구역을 누르면 빈자리 수가 보여요.</T>
              )}
              <Button
                label="이 구역 들어가기"
                disabled={!current || current.state === 'FULL'}
                onPress={() => current && setAreaId(current.area_id)}
              />
              <Button kind="ghost" label="자동 배정으로 두기" onPress={() => onPick(null)} />
            </View>
          </>
        )}
      </View>
    </Modal>
  );
}

/** 한 손가락 이동, 두 손가락 확대·축소(지도 앱처럼). 구역 블록을 누르면 선택. */
function ZoomMap({
  areas,
  pending,
  onPick,
}: {
  areas: AreaSummary[];
  pending: string | null;
  onPick: (id: string) => void;
}) {
  const [box, setBox] = useState({ w: 0, h: 0 });
  const [tf, setTf] = useState<Tf>({ x: 0, y: 0, s: 1 });
  const tfRef = useRef(tf);
  tfRef.current = tf;
  const fit = useRef<Tf>({ x: 0, y: 0, s: 1 });

  useEffect(() => {
    if (!box.w) return;
    const s = Math.min(box.w / WORLD.w, box.h / WORLD.h);
    fit.current = { s, x: (box.w - WORLD.w * s) / 2, y: (box.h - WORLD.h * s) / 2 };
    setTf(fit.current);
  }, [box.w, box.h]);

  const pan = useMemo(() => {
    let base: Tf = { x: 0, y: 0, s: 1 };
    let origin = { dx: 0, dy: 0 };
    let count = 0;
    let pinch: { d: number; s: number } | null = null;
    return PanResponder.create({
      onStartShouldSetPanResponder: () => false,
      onMoveShouldSetPanResponder: (e, g) =>
        e.nativeEvent.touches.length > 1 || Math.abs(g.dx) > 4 || Math.abs(g.dy) > 4,
      onPanResponderGrant: (_e, g) => {
        base = tfRef.current;
        origin = { dx: g.dx, dy: g.dy };
        count = 1;
        pinch = null;
      },
      onPanResponderMove: (e, g) => {
        const t = e.nativeEvent.touches;
        if (t.length !== count) {
          // 손가락 수가 바뀌면 기준을 다시 잡는다
          base = tfRef.current;
          origin = { dx: g.dx, dy: g.dy };
          count = t.length;
          pinch = null;
        }
        if (t.length >= 2) {
          const d = Math.hypot(t[0].pageX - t[1].pageX, t[0].pageY - t[1].pageY);
          if (!pinch) pinch = { d, s: tfRef.current.s };
          const s = clamp((pinch.s * d) / pinch.d, 0.6, 3);
          setTf({ ...tfRef.current, s });
        } else {
          setTf({ s: tfRef.current.s, x: base.x + g.dx - origin.dx, y: base.y + g.dy - origin.dy });
        }
      },
    });
  }, []);

  const zoom = (f: number) => setTf((t) => ({ ...t, s: clamp(t.s * f, 0.6, 3) }));

  return (
    <View style={{ flex: 1 }} onLayout={(e) => setBox({ w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height })} {...pan.panHandlers}>
      <View
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          width: WORLD.w,
          height: WORLD.h,
          transform: [{ translateX: tf.x }, { translateY: tf.y }, { translateX: -(WORLD.w / 2) * (1 - tf.s) }, { translateY: -(WORLD.h / 2) * (1 - tf.s) }, { scale: tf.s }],
        }}
      >
        {/* 통로 */}
        <View style={{ position: 'absolute', left: 16, right: 16, top: 206, height: 32, borderTopWidth: 1, borderBottomWidth: 1, borderColor: C.line, borderStyle: 'dashed' }} />
        <View style={{ position: 'absolute', left: 0, right: 0, top: 424, alignItems: 'center', gap: 4 }}>
          <LogIn size={18} color={C.sub} style={{ transform: [{ rotate: '90deg' }] }} />
          <T style={{ color: C.sub, fontSize: 11, letterSpacing: 1 }}>입구</T>
        </View>
        {areas.map((a) => (
          <AreaBlock key={a.area_id} a={a} on={pending === a.area_id} onPress={() => onPick(a.area_id)} />
        ))}
      </View>

      <View style={{ position: 'absolute', right: 12, bottom: 12, gap: 8 }}>
        <ZoomBtn onPress={() => zoom(1.3)}>
          <Plus size={18} color={C.text} />
        </ZoomBtn>
        <ZoomBtn onPress={() => zoom(1 / 1.3)}>
          <Minus size={18} color={C.text} />
        </ZoomBtn>
      </View>
    </View>
  );
}

function ZoomBtn({ children, onPress }: { children: React.ReactNode; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={{ width: 38, height: 38, borderRadius: 19, backgroundColor: '#2a2a2a', alignItems: 'center', justifyContent: 'center' }}
    >
      {children}
    </Pressable>
  );
}

function AreaBlock({ a, on, onPress }: { a: AreaSummary; on: boolean; onPress: () => void }) {
  const p = LAYOUT[a.area_id] ?? { x: 16, y: 24, w: 150, h: 150 };
  const full = a.state === 'FULL';
  const border = on ? C.active : a.has_mine ? C.active : full ? '#ff373766' : C.line;
  return (
    <Pressable
      onPress={onPress}
      style={{
        position: 'absolute',
        left: p.x,
        top: p.y,
        width: p.w,
        height: p.h,
        borderRadius: 12,
        borderWidth: on ? 2 : 1,
        borderColor: border,
        backgroundColor: on ? '#68D2C31F' : '#171717',
        padding: 14,
        justifyContent: 'space-between',
      }}
    >
      <View style={{ gap: 4 }}>
        <T style={{ fontSize: 20, letterSpacing: -0.5 }}>{a.name}</T>
        <T mono style={{ color: full ? C.error : C.sub, fontSize: 12 }}>
          {full ? '만차' : `빈자리 ${a.free_count} / ${a.seat_total}`}
        </T>
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 5 }}>
        {a.seats.map((s) => (
          <View key={s.zone_id} style={{ width: 12, height: 18, borderRadius: 3, backgroundColor: SEAT_COLOR[s.state], opacity: s.state === 'FREE' ? 0.9 : 1 }} />
        ))}
      </View>
      {a.has_mine ? <T style={{ color: C.active, fontSize: 11, position: 'absolute', right: 12, top: 14 }}>내 자리</T> : null}
    </Pressable>
  );
}

/** 구역 안 맵: 빈자리는 비어 있고, 차 있는 자리에는 차가 있다. */
function AreaInside({
  areaId,
  seat,
  onSeat,
  onBack,
  onConfirm,
}: {
  areaId: string;
  seat: string | null;
  onSeat: (z: string) => void;
  onBack: () => void;
  onConfirm: (z: string) => void;
}) {
  const [d, setD] = useState<AreaDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [w, setW] = useState(0);

  useEffect(() => {
    let alive = true;
    api
      .parkingArea(areaId, seat)
      .then((r) => alive && setD(r))
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [areaId, seat]);

  const GAP = 10;
  const slotW = d && w ? (w - GAP * (d.cols - 1)) / d.cols : 0;
  const slotH = Math.min(slotW * 1.5, 130);
  const chosen = d?.seats.find((s) => s.zone_id === seat) ?? null;
  const bad = d?.selected_ok === false || chosen?.state === 'TAKEN';
  const canConfirm = !!chosen && !bad;

  return (
    <>
      <View style={{ paddingHorizontal: 24, gap: 6, paddingBottom: 14 }}>
        <Pressable onPress={onBack} hitSlop={12} style={{ height: 32, justifyContent: 'center' }}>
          <ChevronLeft size={22} color={C.text} />
        </Pressable>
        <T style={{ color: C.sub, fontSize: 12, letterSpacing: 1 }}>주차 자리</T>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end' }}>
          <T style={{ fontSize: 28, letterSpacing: -1 }}>{d?.name ?? `${areaId}구역`}</T>
          {d ? (
            <T mono style={{ color: C.sub, fontSize: 13, paddingBottom: 4 }}>
              빈자리 {d.free_count} / {d.seat_total}
            </T>
          ) : null}
        </View>
      </View>

      <View style={{ flex: 1, marginHorizontal: 16, borderRadius: 12, backgroundColor: C.hero, padding: 16, justifyContent: 'center' }}>
        {d ? (
          <View style={{ gap: GAP }} onLayout={(e) => setW(e.nativeEvent.layout.width)}>
            {Array.from({ length: d.rows }, (_, row) => (
              <View key={row} style={{ flexDirection: 'row', gap: GAP, height: slotH }}>
                {Array.from({ length: d.cols }, (_, col) => {
                  const s = d.seats.find((x) => x.row === row && x.col === col);
                  if (s) return <Seat key={col} s={s} w={slotW} h={slotH} on={seat === s.zone_id} bad={seat === s.zone_id && bad} onPress={() => onSeat(s.zone_id)} />;
                  const isEntrance = d.entrance.row === row && d.entrance.col === col;
                  return (
                    <View key={col} style={{ width: slotW, height: slotH, alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                      {isEntrance ? (
                        <>
                          <LogIn size={18} color={C.sub} style={{ transform: [{ rotate: '90deg' }] }} />
                          <T style={{ color: C.sub, fontSize: 11, letterSpacing: 1 }}>입구</T>
                        </>
                      ) : null}
                    </View>
                  );
                })}
              </View>
            ))}
          </View>
        ) : error ? (
          <T style={{ color: C.error, fontSize: 13 }}>{error}</T>
        ) : (
          <ActivityIndicator color={C.text} />
        )}
      </View>

      <View style={{ paddingHorizontal: 24, paddingTop: 14, gap: 10 }}>
        <T style={{ color: bad ? C.error : chosen ? C.active : C.muted, fontSize: 13 }}>
          {bad
            ? '이미 선정된 자리예요. 다른 자리를 골라 주세요.'
            : chosen
              ? `${chosen.seat_no}번 자리를 골랐어요`
              : '빈자리를 눌러서 골라 주세요.'}
        </T>
        <Button label="이 자리로 선택" disabled={!canConfirm} onPress={() => chosen && onConfirm(chosen.zone_id)} />
      </View>
    </>
  );
}

function Seat({
  s,
  w,
  h,
  on,
  bad,
  onPress,
}: {
  s: AreaDetail['seats'][number];
  w: number;
  h: number;
  on: boolean;
  bad: boolean;
  onPress: () => void;
}) {
  const taken = s.state === 'TAKEN';
  const mine = s.state === 'MINE';
  const border = bad ? C.error : on || mine ? C.active : C.line;
  const bg = bad ? '#ff373722' : on || mine ? '#68D2C322' : taken ? '#141414' : '#262626';
  const carH = h - 34;
  return (
    <Pressable
      onPress={onPress}
      style={{
        width: w,
        height: h,
        borderRadius: 8,
        borderWidth: on || mine || bad ? 2 : 1,
        borderColor: border,
        backgroundColor: bg,
        alignItems: 'center',
        justifyContent: 'flex-end',
        paddingBottom: 6,
      }}
    >
      <T mono style={{ position: 'absolute', left: 7, top: 5, fontSize: 11, color: bad ? C.error : on || mine ? C.active : C.muted }}>
        {s.seat_no}
      </T>
      {taken || mine ? (
        <Image
          source={CAR}
          resizeMode="contain"
          style={{ width: carH * CAR_RATIO * 1.1, height: carH, opacity: taken ? 0.75 : 1 }}
        />
      ) : null}
      {mine ? <T style={{ position: 'absolute', right: 6, top: 5, fontSize: 10, color: C.active }}>내 차</T> : null}
    </Pressable>
  );
}
