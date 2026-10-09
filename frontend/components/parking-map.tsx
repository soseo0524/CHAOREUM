// 02.02 전체 지도(손가락으로 확대·이동해서 구역 고르기)
// 사용자는 구역(A·B·C)만 고르고, 구역 안의 빈 칸은 관제가 고른다. 고른 구역을 onPick으로 돌려준다. 자동 배정은 null.
import { LogIn, Minus, Plus, X } from 'lucide-react-native';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Modal, PanResponder, Pressable, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { C } from '@/constants/theme';
import type { AreaSummary, AreasOut } from '@/constants/types';
import { api } from '@/services/api';
import { Button, T } from './ui';

// ---- 전체 지도(02.02): 실제 주차장 구조. A(윗줄 17칸) / B(가운데 두 줄 13+13) / C(아랫줄 14칸)
// 자리 박스는 구역 안 맵과 같은 비율(1 : 1.78), 구역 사이에는 차가 지나가는 길
const WORLD = { w: 716, h: 660 };
const OV = { seatW: 30, seatH: 53, radius: 5, scale: 0.36, left: 20, row1: 68, row2: 137 };
const LAYOUT: Record<string, { x: number; y: number; w: number; h: number }> = {
  A: { x: 16, y: 24, w: 684, h: 137 },
  B: { x: 16, y: 209, w: 684, h: 206 },
  C: { x: 16, y: 463, w: 684, h: 137 },
};
const LANES = [161, 415]; // 길(높이 48)이 시작하는 y
// 줄별 자리 번호(왼쪽→오른쪽)와 사진 속 가로 위치(3칸씩 묶인 간격을 그대로 살리는 데 쓴다)
const OV_ROWS: Record<string, [number, number][][]> = {
  A: [[[61, 174], [45, 275], [43, 386], [42, 500], [40, 595], [41, 689], [38, 827], [37, 921], [36, 1014], [58, 1148], [33, 1243], [32, 1338], [59, 1462], [29, 1556], [28, 1651], [62, 1784], [26, 1887]]],
  B: [
    [[0, 498], [1, 594], [2, 689], [3, 825], [4, 919], [5, 1013], [6, 1149], [7, 1237], [8, 1324], [9, 1461], [10, 1552], [11, 1644], [60, 1782]],
    [[25, 485], [24, 579], [23, 672], [22, 810], [21, 905], [20, 999], [19, 1137], [18, 1232], [17, 1327], [16, 1459], [15, 1555], [13, 1650], [63, 1783]],
  ],
  C: [[[57, 571], [56, 665], [46, 799], [47, 893], [48, 987], [49, 1124], [50, 1217], [51, 1311], [52, 1450], [53, 1542], [54, 1635], [65, 1768], [55, 1864], [64, 1960]]],
};
const SEAT_COLOR = { FREE: '#d1d1d6', TAKEN: '#3a3a3c', MINE: C.active } as const;

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

type Tf = { x: number; y: number; s: number };

export function ParkingMap({
  visible,
  selected,
  onClose,
  onPick,
}: {
  visible: boolean;
  selected: string | null; // 이미 고른 구역(A·B·C)
  onClose: () => void;
  onPick: (area: string | null) => void;
}) {
  const insets = useSafeAreaInsets();
  const [areas, setAreas] = useState<AreasOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(selected); // 지도에서 눌러 둔 구역

  useEffect(() => {
    if (!visible) return;
    setPending(selected);
    setError(null);
    setAreas(null);
    api
      .parkingAreas()
      .then(setAreas)
      .catch((e) => setError(e.message));
  }, [visible]); // eslint-disable-line react-hooks/exhaustive-deps

  const current = areas?.areas.find((a) => a.area_id === pending) ?? null;

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: C.bg, paddingTop: insets.top + 4, paddingBottom: Math.max(insets.bottom, 16) }}>
        <>
            <View style={{ paddingHorizontal: 24, gap: 6, paddingBottom: 12 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <T style={{ color: C.sub, fontSize: 12, letterSpacing: 1 }}>주차 구역</T>
                <Pressable onPress={onClose} hitSlop={12}>
                  <X size={22} color={C.text} />
                </Pressable>
              </View>
              <T style={{ fontSize: 28, letterSpacing: -1 }}>구역을 골라 주세요</T>
            </View>

            <View style={{ flex: 1, marginHorizontal: 16, borderRadius: 12, overflow: 'hidden', backgroundColor: C.hero }}>
              {areas ? (
                <PanZoom worldW={WORLD.w} worldH={WORLD.h} focus={{ x: 175, y: 250, s: 1 }} focusKey="overview" minS={0.4} maxS={2}>
                  {/* 길: 구역 사이(차가 지나가는 공간) */}
                  {LANES.map((y) => (
                    <View key={y} style={{ position: 'absolute', left: 16, width: 684, top: y, height: 48, borderTopWidth: 1, borderBottomWidth: 1, borderColor: C.line, borderStyle: 'dashed' }} />
                  ))}
                  <View style={{ position: 'absolute', left: 0, width: WORLD.w, top: 616, alignItems: 'center', gap: 4 }}>
                    <LogIn size={18} color={C.sub} style={{ transform: [{ rotate: '90deg' }] }} />
                    <T style={{ color: C.sub, fontSize: 11, letterSpacing: 1 }}>입구</T>
                  </View>
                  {areas.areas.map((a) => (
                    <AreaBlock key={a.area_id} a={a} on={pending === a.area_id} onPress={() => setPending(a.area_id)} />
                  ))}
                </PanZoom>
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
                <T style={{ color: C.muted, fontSize: 13 }}>구역을 누르면 빈자리 수가 보여요. 자리는 관제가 정해요.</T>
              )}
              <Button
                label={current ? `${current.name}으로 할게요` : '구역을 골라 주세요'}
                disabled={!current || current.state === 'FULL'}
                onPress={() => current && onPick(current.area_id)}
              />
              <Button kind="ghost" label="자동 배정으로 두기" onPress={() => onPick(null)} />
            </View>
        </>
      </View>
    </Modal>
  );
}

/**
 * 지도처럼 쓰는 판: 한 손가락 이동, 두 손가락 확대·축소, +/- 버튼.
 * focus가 있으면 그 지점(월드 좌표)을 가운데에 두고 focus.s 배율로 시작하고, 없으면 판 전체가 보이게 맞춘다.
 * focusKey가 바뀔 때마다 처음 위치로 다시 맞춘다.
 */
function PanZoom({
  worldW,
  worldH,
  focus,
  focusKey,
  minS = 0.3,
  maxS = 3,
  children,
}: {
  worldW: number;
  worldH: number;
  focus?: { x: number; y: number; s: number };
  focusKey: string;
  minS?: number;
  maxS?: number;
  children: React.ReactNode;
}) {
  const [box, setBox] = useState({ w: 0, h: 0 });
  const [tf, setTf] = useState<Tf>({ x: 0, y: 0, s: 1 });
  const tfRef = useRef(tf);
  tfRef.current = tf;
  const boxRef = useRef(box);
  boxRef.current = box;
  const limits = useRef({ minS, maxS });
  limits.current = { minS, maxS };

  useEffect(() => {
    if (!box.w) return;
    if (focus) {
      const s = clamp(focus.s, minS, maxS);
      setTf({ s, x: box.w / 2 - focus.x * s, y: box.h / 2 - focus.y * s });
    } else {
      const s = Math.min(box.w / worldW, box.h / worldH);
      setTf({ s, x: (box.w - worldW * s) / 2, y: (box.h - worldH * s) / 2 });
    }
  }, [box.w, box.h, focusKey]); // eslint-disable-line react-hooks/exhaustive-deps

  /** 화면 가운데를 기준으로 배율 바꾸기 */
  const zoomAround = (t: Tf, s2: number): Tf => {
    const b = boxRef.current;
    const cx = b.w / 2;
    const cy = b.h / 2;
    const k = s2 / t.s;
    return { s: s2, x: cx - (cx - t.x) * k, y: cy - (cy - t.y) * k };
  };

  const pan = useMemo(() => {
    let base: Tf = { x: 0, y: 0, s: 1 };
    let origin = { dx: 0, dy: 0 };
    let count = 0;
    let pinch: { d: number; t: Tf } | null = null;
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
          if (!pinch) pinch = { d, t: tfRef.current };
          const { minS: lo, maxS: hi } = limits.current;
          setTf(zoomAround(pinch.t, clamp((pinch.t.s * d) / pinch.d, lo, hi)));
        } else {
          setTf({ s: tfRef.current.s, x: base.x + g.dx - origin.dx, y: base.y + g.dy - origin.dy });
        }
      },
    });
  }, []);

  const zoom = (f: number) => setTf((t) => zoomAround(t, clamp(t.s * f, limits.current.minS, limits.current.maxS)));

  return (
    <View style={{ flex: 1 }} onLayout={(e) => setBox({ w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height })} {...pan.panHandlers}>
      <View
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          width: worldW,
          height: worldH,
          transform: [{ translateX: tf.x }, { translateY: tf.y }, { translateX: -(worldW / 2) * (1 - tf.s) }, { translateY: -(worldH / 2) * (1 - tf.s) }, { scale: tf.s }],
        }}
      >
        {children}
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
  const p = LAYOUT[a.area_id] ?? { x: 16, y: 24, w: 684, h: 137 };
  const full = a.state === 'FULL';
  const border = on ? C.active : a.has_mine ? C.active : full ? '#ff373766' : C.line;
  const stateOf = new Map(a.seats.map((s) => [s.seat_no, s.state] as const));
  const rows = OV_ROWS[a.area_id] ?? [];
  return (
    <Pressable
      onPress={onPress}
      style={{
        position: 'absolute',
        left: p.x,
        top: p.y,
        width: p.w,
        height: p.h,
        borderRadius: 22,
        borderWidth: on ? 2 : 1,
        borderColor: border,
        backgroundColor: on ? '#68D2C31F' : '#141416',
      }}
    >
      <T mono style={{ position: 'absolute', left: 16, top: 10, fontSize: 30, letterSpacing: -1 }}>{a.area_id}</T>
      <T mono style={{ position: 'absolute', left: 16, top: 44, color: full ? C.error : on ? C.active : C.sub, fontSize: 12 }}>
        {full ? '만차' : `빈자리 ${a.free_count} / ${a.seat_total}`}
      </T>
      {rows.map((row, r) => {
        const x0 = Math.min(...row.map(([, c]) => c));
        return row.map(([n, c]) => {
          const st = stateOf.get(n) ?? 'TAKEN';
          return (
            <View
              key={n}
              style={{
                position: 'absolute',
                left: OV.left + (c - x0) * OV.scale,
                top: r === 0 ? OV.row1 : OV.row2,
                width: OV.seatW,
                height: OV.seatH,
                borderRadius: OV.radius,
                backgroundColor: SEAT_COLOR[st],
              }}
            />
          );
        });
      })}
      {a.has_mine ? <T style={{ color: C.active, fontSize: 11, position: 'absolute', right: 16, top: 14 }}>내 자리</T> : null}
    </Pressable>
  );
}

/** 구역 안 맵: 지도처럼 확대·이동. 빈자리는 비어 있고, 차 있는 자리에는 차가 있다. */
