// 02.01 충전 요청 / 02-A.04 접수된 요청 수정 / 02.04 위임 동의 시트
import DateTimePicker, { DateTimePickerAndroid } from '@react-native-community/datetimepicker';
import Slider from '@react-native-community/slider';
import { router } from 'expo-router';
import { BatteryCharging, FileText, KeyRound, MapPin } from 'lucide-react-native';
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Modal, Platform, Pressable, ScrollView, View } from 'react-native';

import { Button, Checkbox, Row, Screen, T, Title } from '@/components/ui';
import { clockText, dayClock, zoneLabel } from '@/constants/format';
import { C } from '@/constants/theme';
import { HomeState, type Feasibility, type ParkingZone } from '@/constants/types';
import { useStatus } from '@/hooks/useStatus';
import { api } from '@/services/api';
import { useAuth } from '@/services/auth';

const CONSENT_VERSION = 'v1';
const MIN_SOC_OPTIONS = [0, 20, 40, 60];
const EDITABLE = new Set<string>([HomeState.QUEUED]);

function defaultFinish() {
  const d = new Date(Date.now() + 2 * 3600_000);
  d.setMinutes(Math.ceil(d.getMinutes() / 10) * 10, 0, 0);
  return d;
}

export default function Request() {
  const { status, refresh } = useStatus();
  const { profile, refreshProfile } = useAuth();
  const v = status?.vehicles[0];
  const active = v?.active_request ?? null;
  const editing = !!active && EDITABLE.has(v!.home_state);

  const [finish, setFinish] = useState(defaultFinish);
  const [target, setTarget] = useState(80);
  const [minSoc, setMinSoc] = useState(0);
  const [zone, setZone] = useState<string | null>(null);
  const [agree, setAgree] = useState(false);
  const [feas, setFeas] = useState<Feasibility | null>(null);
  const [checking, setChecking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [iosPicker, setIosPicker] = useState(false);
  const [zones, setZones] = useState<ParkingZone[] | null>(null);
  const [sheet, setSheet] = useState(false);

  // 수정 모드면 접수된 값으로 채운다
  useEffect(() => {
    if (!active) return;
    setFinish(new Date(active.desired_finish_at));
    setTarget(active.target_soc);
    setMinSoc(active.min_soc);
    setZone(active.parking_zone_id);
  }, [active?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (profile?.consent_agreed) setAgree(true);
  }, [profile?.consent_agreed]);

  // 조건이 바뀌면 dry_run으로 가능 여부 미리보기
  useEffect(() => {
    if (!v?.assigned || editing || finish <= new Date()) return;
    setChecking(true);
    const t = setTimeout(async () => {
      try {
        const r = await api.createRequest({
          vehicle_id: v.vehicle_id,
          desired_finish_at: finish.toISOString(),
          target_soc: target,
          min_soc: Math.min(minSoc, target),
          parking_zone_id: zone,
          dry_run: true,
        });
        setFeas(r.feasibility);
      } catch {
        setFeas(null);
      } finally {
        setChecking(false);
      }
    }, 400);
    return () => clearTimeout(t);
  }, [v?.vehicle_id, v?.assigned, editing, finish.getTime(), target, minSoc, zone]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!v) {
    return (
      <Screen tabs footer={<Button label="차량 등록하기" onPress={() => router.push('/vehicle-new')} />}>
        <Title eyebrow="새 요청" size={32}>
          충전 요청
        </Title>
        <T style={{ color: C.sub, fontSize: 14 }}>먼저 차량을 등록해 주세요.</T>
      </Screen>
    );
  }
  if (!v.assigned) {
    return (
      <Screen tabs>
        <Title eyebrow="새 요청" size={32}>
          충전 요청
        </Title>
        <T style={{ color: C.sub, fontSize: 14, lineHeight: 21 }}>
          관리자가 차량을 배정하면 충전을 요청할 수 있어요.
        </T>
      </Screen>
    );
  }
  if (active && !editing) {
    return (
      <Screen tabs footer={<Button label="홈에서 진행 상황 보기" onPress={() => router.navigate('/')} />}>
        <Title eyebrow="진행 중" size={32}>
          충전 요청
        </Title>
        <T style={{ color: C.sub, fontSize: 14, lineHeight: 21 }}>
          이미 진행 중인 요청이 있어요. 차량이 움직이기 시작하면 요청을 바꿀 수 없어요.
        </T>
      </Screen>
    );
  }

  function pickTime() {
    if (Platform.OS === 'ios') return setIosPicker(true);
    DateTimePickerAndroid.open({
      value: finish,
      mode: 'date',
      minimumDate: new Date(),
      onValueChange: (_e, date) => {
        DateTimePickerAndroid.open({
          value: date,
          mode: 'time',
          onValueChange: (_e2, time) => setFinish(time),
        });
      },
    });
  }

  function pickMinSoc() {
    Alert.alert('최소 필요 충전량', '시간이 부족해도 이만큼은 먼저 충전해요.', [
      ...MIN_SOC_OPTIONS.filter((o) => o <= target).map((o) => ({
        text: o === 0 ? '없음' : `${o}%`,
        onPress: () => setMinSoc(o),
      })),
      { text: '닫기', style: 'cancel' as const },
    ]);
  }

  async function openZones() {
    setZones([]);
    try {
      setZones(await api.parkingZones());
    } catch (e: any) {
      setZones(null);
      Alert.alert('주차 구역', e.message);
    }
  }

  async function submit(consented = profile?.consent_agreed) {
    if (!consented) return setSheet(true);
    if (finish <= new Date()) return Alert.alert('주차 완료 시각', '지금보다 나중 시각을 골라 주세요.');
    setBusy(true);
    try {
      if (editing && active) {
        await api.updateRequest(active.id, {
          desired_finish_at: finish.toISOString(),
          target_soc: target,
          min_soc: Math.min(minSoc, target),
          ...(zone && zone !== active.parking_zone_id ? { parking_zone_id: zone } : {}),
        });
      } else {
        await api.createRequest({
          vehicle_id: v!.vehicle_id,
          desired_finish_at: finish.toISOString(),
          target_soc: target,
          min_soc: Math.min(minSoc, target),
          parking_zone_id: zone,
        });
      }
      await refresh();
      router.navigate('/');
    } catch (e: any) {
      const f: Feasibility | undefined = e.details?.feasibility;
      Alert.alert(
        '요청할 수 없어요',
        f?.earliest_parked_at ? `${e.message}\n가장 빠른 완료: ${dayClock(new Date(f.earliest_parked_at))}` : e.message,
      );
    } finally {
      setBusy(false);
    }
  }

  async function agreeAndSubmit() {
    try {
      await api.consent(CONSENT_VERSION);
      await refreshProfile();
      setSheet(false);
      setAgree(true);
      await submit(true);
    } catch (e: any) {
      Alert.alert('동의 저장 실패', e.message);
    }
  }

  return (
    <Screen
      tabs
      contentStyle={{ gap: 0 }}
      footer={
        <View style={{ gap: 14 }}>
          {editing ? null : (
            <Checkbox
              checked={agree}
              onPress={() => (profile?.consent_agreed ? null : setSheet(true))}
              label="차량 운행 및 위치 정보 이용에 동의합니다."
            />
          )}
          <Button label={editing ? '요청 수정하기' : '충전 요청하기'} onPress={() => submit()} loading={busy} />
        </View>
      }
    >
      <View style={{ paddingBottom: 20 }}>
        <Title eyebrow={editing ? '접수된 요청' : '새 요청'} size={32}>
          {editing ? '요청 수정' : '충전 요청'}
        </Title>
      </View>
      <Row label="차량">
        <T style={{ fontSize: 15 }}>{v.plate_no}</T>
        <T mono style={{ color: C.sub, fontSize: 13 }}>
          {v.soc == null ? '—' : `${Math.round(v.soc)}%`}
        </T>
      </Row>
      <Row label="주차 완료 시각" onPress={pickTime}>
        <T style={{ fontSize: 15 }}>{dayClock(finish)}</T>
      </Row>
      <View style={{ gap: 14, paddingTop: 14, paddingBottom: 18, borderBottomWidth: 1, borderBottomColor: C.line }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end' }}>
          <T style={{ color: C.sub, fontSize: 14 }}>목표 충전량</T>
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 2 }}>
            <T mono style={{ fontSize: 28, letterSpacing: -1 }}>
              {target}
            </T>
            <T mono style={{ color: C.sub, fontSize: 13, paddingBottom: 5 }}>
              %
            </T>
          </View>
        </View>
        <Slider
          minimumValue={60}
          maximumValue={100}
          step={5}
          value={target}
          onValueChange={(x) => setTarget(Math.round(x))}
          minimumTrackTintColor={C.primary}
          maximumTrackTintColor={C.line}
          thumbTintColor="#FFFFFF"
        />
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <T mono style={{ color: C.muted, fontSize: 11 }}>
            60%
          </T>
          <T mono style={{ color: C.muted, fontSize: 11 }}>
            100%
          </T>
        </View>
      </View>
      <Row label="최소 필요 충전량" onPress={pickMinSoc}>
        <T style={{ fontSize: 15 }}>{minSoc === 0 ? '없음' : `${minSoc}%`}</T>
      </Row>
      <Row label="주차 구역" onPress={openZones}>
        <T mono style={{ fontSize: 15 }}>
          {zoneLabel(zone) ?? '자동 배정'}
        </T>
        <T style={{ color: C.primaryText, fontSize: 13 }}>선택</T>
      </Row>
      {editing ? null : <FeasibilityView f={feas} checking={checking} />}

      {/* iOS 시각 선택 */}
      <Modal visible={iosPicker} transparent animationType="slide" onRequestClose={() => setIosPicker(false)}>
        <Pressable style={{ flex: 1, backgroundColor: '#000000B3' }} onPress={() => setIosPicker(false)} />
        <View style={{ backgroundColor: C.surface, padding: 24, paddingBottom: 40, gap: 12 }}>
          <DateTimePicker
            value={finish}
            mode="datetime"
            display="spinner"
            minimumDate={new Date()}
            minuteInterval={10}
            themeVariant="dark"
            onValueChange={(_e, d) => setFinish(d)}
          />
          <Button label="완료" onPress={() => setIosPicker(false)} />
        </View>
      </Modal>

      {/* 주차 구역 선택(지도 화면은 다음 단계) */}
      <Modal visible={zones !== null} transparent animationType="slide" onRequestClose={() => setZones(null)}>
        <Pressable style={{ flex: 1, backgroundColor: '#000000B3' }} onPress={() => setZones(null)} />
        <View style={{ backgroundColor: C.surface, maxHeight: '60%', borderTopLeftRadius: 16, borderTopRightRadius: 16 }}>
          <T style={{ fontSize: 20, padding: 24, paddingBottom: 8 }}>주차 구역</T>
          <ScrollView contentContainerStyle={{ paddingHorizontal: 24, paddingBottom: 40 }}>
            {zones?.length === 0 ? <ActivityIndicator color={C.text} style={{ margin: 24 }} /> : null}
            <Row label="자동 배정" onPress={() => (setZone(null), setZones(null))} chevron={false}>
              {zone === null ? <T style={{ color: C.active, fontSize: 13 }}>선택됨</T> : null}
            </Row>
            {zones?.map((z) => (
              <Row
                key={z.id}
                label={z.name}
                chevron={false}
                onPress={z.is_available || z.id === zone ? () => (setZone(z.id), setZones(null)) : undefined}
              >
                <T style={{ color: z.id === zone ? C.active : z.is_available ? C.sub : C.error, fontSize: 13 }}>
                  {z.id === zone ? '선택됨' : z.is_available ? '비어 있음' : '이미 선정됨'}
                </T>
              </Row>
            ))}
          </ScrollView>
        </View>
      </Modal>

      {/* 02.04 위임 동의 시트 */}
      <Modal visible={sheet} transparent animationType="slide" onRequestClose={() => setSheet(false)}>
        <Pressable style={{ flex: 1, backgroundColor: '#000000B3' }} onPress={() => setSheet(false)} />
        <View
          style={{
            backgroundColor: C.surface,
            borderTopLeftRadius: 16,
            borderTopRightRadius: 16,
            paddingHorizontal: 24,
            paddingTop: 10,
            paddingBottom: 28,
            gap: 14,
          }}
        >
          <View style={{ alignItems: 'center' }}>
            <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: C.line }} />
          </View>
          <T style={{ fontSize: 20 }}>차량 위치·위임에 동의해 주세요</T>
          <T style={{ color: C.sub, fontSize: 13, lineHeight: 20 }}>
            충전과 주차를 위해 차량의 위치와 상태를 수집하고, 관제 시스템이 차량을 무인으로 이동·충전하도록 권한을
            위임해요. 요청이 끝나면 위치 수집도 멈춰요.
          </T>
          <View style={{ gap: 10 }}>
            <SheetItem icon={<MapPin size={16} color={C.text} />} text="차량 위치 · 주차 구역" />
            <SheetItem icon={<BatteryCharging size={16} color={C.text} />} text="배터리 잔량 · 충전 상태" />
            <SheetItem icon={<KeyRound size={16} color={C.text} />} text="차량 무인 이동·충전 권한 위임" />
            <SheetItem icon={<FileText size={16} color={C.muted} />} text="내용 전체 보기" color={C.primaryText} />
          </View>
          <Button label="동의하고 요청하기" onPress={agreeAndSubmit} loading={busy} />
          <Button kind="outline" label="나중에" onPress={() => setSheet(false)} />
        </View>
      </Modal>
    </Screen>
  );
}

function SheetItem({ icon, text, color = C.text }: { icon: React.ReactNode; text: string; color?: string }) {
  return (
    <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
      {icon}
      <T style={{ color, fontSize: 13 }}>{text}</T>
    </View>
  );
}

function FeasibilityView({ f, checking }: { f: Feasibility | null; checking: boolean }) {
  const parts = useMemo(() => {
    const b = f?.breakdown;
    if (!b) return null;
    return [
      { s: b.wait_s, o: 0.25, label: '대기' },
      { s: b.move_to_charger_s, o: 0.5, label: '이동' },
      { s: b.charge_s, o: 1, label: '충전' },
      { s: b.move_to_parking_s, o: 0.5, label: '주차 이동' },
    ];
  }, [f]);
  if (!f) {
    return (
      <View style={{ paddingTop: 16 }}>
        <T style={{ color: C.muted, fontSize: 13 }}>{checking ? '가능 여부 계산 중…' : ''}</T>
      </View>
    );
  }
  const at = f.estimated_parked_at ?? f.earliest_parked_at;
  return (
    <View style={{ gap: 12, paddingTop: 16, paddingBottom: 4, opacity: checking ? 0.5 : 1 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', flexShrink: 1 }}>
          <View
            style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: f.feasible ? C.success : C.warning }}
          />
          <T style={{ fontSize: 15, flexShrink: 1 }}>
            {f.feasible ? '시간 안에 가능해요' : (f.message ?? '희망 시간 안에는 어려워요')}
          </T>
        </View>
        {at ? (
          <T mono style={{ color: C.sub, fontSize: 13 }}>
            {clockText(at)} {f.feasible ? '완료' : '가능'}
          </T>
        ) : null}
      </View>
      {parts ? (
        <>
          <View style={{ flexDirection: 'row', gap: 3 }}>
            {parts
              .filter((p) => p.s > 0)
              .map((p) => (
                <View
                  key={p.label}
                  style={{ flex: p.s, height: 4, borderRadius: 2, backgroundColor: '#ffffff', opacity: p.o }}
                />
              ))}
          </View>
          <T style={{ color: C.muted, fontSize: 12 }}>
            {parts.map((p) => `${p.label} ${Math.round(p.s / 60)}분`).join(' · ')}
          </T>
        </>
      ) : null}
    </View>
  );
}
