// 홈: GET /me/status 의 home_state 하나로 화면(01.04~05.06)을 고른다
import { router } from 'expo-router';
import { CarFront, ChevronRight } from 'lucide-react-native';
import { useState } from 'react';
import { ActivityIndicator, Alert, Pressable, View } from 'react-native';

import {
  Banner,
  CarHero,
  contactCenter,
  MetricRow,
  Notice,
  SocBar,
  StatusBlock,
  Steps,
  TopBar,
  type MetricItem,
  type Step,
} from '@/components/home';
import { Dialog } from '@/components/dialog';
import { ParkingMap } from '@/components/parking-map';
import { Button, EmptyHero, Screen, T, Title } from '@/components/ui';
import { areaLabel, chargerNo, clock, clockText, monthDay, won, zoneLabel } from '@/constants/format';
import { C } from '@/constants/theme';
import { EtaState, HomeState, VehicleState, type VehicleStatus } from '@/constants/types';
import { useStatus } from '@/hooks/useStatus';
import { api } from '@/services/api';

const PROGRESS_TITLE: Partial<Record<HomeState, string>> = {
  [HomeState.MOVING_TO_CHARGER]: '충전소로 이동 중',
  [HomeState.CHARGING]: '충전 중이에요',
  [HomeState.CHARGE_DONE]: '충전이 끝났어요',
  [HomeState.MOVING_TO_PARKING]: '주차구역으로 이동 중',
  [HomeState.PARKED]: '주차가 끝났어요',
};
const STEP_TITLES = ['충전소로 이동중', '충전중', '충전완료', '주차구역으로 이동중', '주차완료'];

function progressSteps(v: VehicleStatus): Step[] {
  const cur = v.step ?? 0;
  const zone = areaLabel(v.active_request?.parking_area) ?? zoneLabel(v.zone_id);
  const subs = [
    chargerNo(v.charger_id) ? `${chargerNo(v.charger_id)}으로 이동` : undefined,
    chargerNo(v.charger_id) ?? undefined,
    '곧 주차구역으로 이동해요',
    zone ?? undefined,
    undefined,
  ];
  return STEP_TITLES.map((title, i) => {
    const n = i + 1;
    // 주차 완료(5단계)는 도착 즉시 끝난 단계로 표시
    const status = n < cur || (n === 5 && cur === 5) ? 'done' : n === cur ? 'current' : 'todo';
    return { title, status, sub: status === 'current' ? subs[i] : undefined };
  });
}

function etaMetric(v: VehicleStatus, label = '예상 완료'): MetricItem {
  if (v.eta.state === EtaState.KNOWN && v.eta.at) {
    const c = clock(v.eta.at);
    return { label, value: c.hm, unit: c.ap };
  }
  return { label, value: v.eta.state === EtaState.CALCULATING ? '계산 중' : '—' };
}

function socText(v: VehicleStatus) {
  return v.soc == null ? '—' : String(Math.round(v.soc));
}

export default function Home() {
  const { status, error, connected, lastUpdated, refresh, reconnect } = useStatus();
  const [busy, setBusy] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [mapOpen, setMapOpen] = useState(false);

  if (!status) {
    return (
      <Screen tabs scroll={false}>
        <TopBar />
        {error ? (
          <View style={{ gap: 16, paddingTop: 40 }}>
            <Title>서버에 연결할 수 없어요</Title>
            <T style={{ color: C.sub, fontSize: 14, lineHeight: 21 }}>{error}</T>
            <Button kind="outline" label="다시 시도" onPress={refresh} />
          </View>
        ) : (
          <ActivityIndicator color={C.text} style={{ marginTop: 80 }} />
        )}
      </Screen>
    );
  }

  // 01.04 등록 차량 없음
  if (status.vehicles.length === 0) {
    return (
      <Screen tabs footer={<Button label="차량 등록하기" onPress={() => router.push('/vehicle-new')} />}>
        <TopBar />
        <EmptyHero icon={CarFront} />
        <View style={{ gap: 8 }}>
          <Title>등록된 차량이 없어요</Title>
          <T style={{ color: C.sub, fontSize: 14 }}>차량을 등록하면 충전과 주차를 맡길 수 있어요.</T>
        </View>
        <Onboarding current={0} />
      </Screen>
    );
  }

  const v = status.vehicles[0];
  const req = v.active_request;
  const hs = v.home_state;

  // 01.06 차량 배정 대기
  if (hs === HomeState.WAITING_ASSIGNMENT) {
    return (
      <Screen tabs footer={<Button label="내 차량 보기" onPress={() => router.navigate('/me')} />}>
        <TopBar />
        <EmptyHero icon={CarFront} />
        <View style={{ gap: 8 }}>
          <Title>차량 배정을 기다려요</Title>
          <T style={{ color: C.sub, fontSize: 14, lineHeight: 21 }}>
            관리자가 {v.plate_no}을 확인하는 중이에요. 배정되면 알려 드릴게요.
          </T>
        </View>
        <Onboarding current={2} />
      </Screen>
    );
  }

  const cancel = () => setCancelOpen(true);
  async function confirmCancel() {
    if (!req) return;
    setBusy(true);
    try {
      await api.updateRequest(req.id, { cancel: true });
      setCancelOpen(false);
      await refresh();
    } catch (e: any) {
      setCancelOpen(false);
      Alert.alert('취소 실패', e.message);
    } finally {
      setBusy(false);
    }
  }

  const goRequest = () => router.navigate('/request');
  const banner = !connected ? (
    <Banner
      title="연결이 끊겼어요"
      sub={lastUpdated ? `마지막 갱신 ${clockText(lastUpdated)}` : '다시 연결하는 중'}
      action="다시 연결"
      onAction={reconnect}
    />
  ) : hs === HomeState.VEHICLE_OFFLINE ? (
    <Banner
      title="차량 신호가 없어요"
      sub={`마지막 수신 ${v.last_seen_at ? clockText(v.last_seen_at) : '—'} · 다시 찾는 중`}
      action="관제 문의"
      actionColor={C.active}
      onAction={contactCenter}
    />
  ) : null;

  const metrics: MetricItem[] = [
    { label: '배터리', value: socText(v), unit: '%' },
    { label: '목표', value: req ? String(req.target_soc) : '80', unit: '%' },
    etaMetric(v),
  ];
  let title = '';
  let titleColor: string = C.text;
  let body: React.ReactNode = null;
  let footer: React.ReactNode = null;
  let showMetrics = true;
  let showCharge = false;

  switch (hs) {
    case HomeState.NO_DATA:
      // 배정은 됐지만 관제가 아직 이 차 상태를 한 번도 보내지 않음(관제 미연결 포함). 끝없는 로딩 대신 이유를 보여 준다
      title = '차량 정보를 기다려요';
      titleColor = C.sub;
      showMetrics = false;
      body = (
        <Notice
          eyebrow="상황"
          body={`관제 시스템에서 ${v.plate_no}의 배터리·위치 정보를 아직 받지 못했어요.`}
          sub="정보가 들어오면 자동으로 바뀌어요. 그 전에도 충전 요청은 할 수 있어요."
        />
      );
      footer = req ? null : <Button label="충전 요청하기" onPress={goRequest} />;
      break;
    case HomeState.NO_REQUEST: {
      title = '충전 요청이 없어요';
      metrics[1] = { label: '추천 목표', value: '80', unit: '%' };
      metrics[2] = { label: '충전 시간', value: '—' };
      const ls = v.last_session;
      body = ls ? (
        <View style={{ gap: 10, paddingTop: 14 }}>
          <T style={{ color: C.sub, fontSize: 12, letterSpacing: 1 }}>최근 충전</T>
          <Pressable onPress={() => router.navigate('/me')} style={{ flexDirection: 'row', alignItems: 'center' }}>
            <View style={{ flex: 1, gap: 2 }}>
              <T style={{ fontSize: 14 }}>
                {monthDay(ls.ended_at)}
                {ls.end_soc != null ? ` · ${ls.end_soc}%까지` : ''}
              </T>
              <T style={{ color: C.sub, fontSize: 12 }}>
                {ls.energy_kwh.toFixed(1)} kWh · {won(ls.cost_won)}원
              </T>
            </View>
            <ChevronRight size={18} color={C.muted} />
          </Pressable>
        </View>
      ) : null;
      footer = <Button label="충전 요청하기" onPress={goRequest} />;
      break;
    }
    case HomeState.QUEUED: {
      title = req?.queue_position ? `${req.queue_position}번째로 기다리는 중` : '요청을 접수했어요';
      const ahead = req?.queue_position ? req.queue_position - 1 : null;
      const sub = [
        ahead != null ? `앞에 ${ahead}대` : null,
        req?.estimated_wait_min != null ? `약 ${req.estimated_wait_min}분 대기` : null,
      ]
        .filter(Boolean)
        .join(' · ');
      body = (
        <Steps
          steps={[
            { title: '요청 접수', status: 'done' },
            { title: '충전 대기', status: 'current', sub: sub || undefined },
            { title: '충전중', status: 'todo' },
            { title: '주차구역으로 이동중', status: 'todo' },
            { title: '주차완료', status: 'todo' },
          ]}
        />
      );
      footer = (
        <View style={{ flexDirection: 'row', gap: 10 }}>
          <Button kind="outline" label="요청 수정" onPress={goRequest} style={{ flex: 1 }} />
          <Button kind="danger" label="요청 취소" onPress={cancel} loading={busy} style={{ flex: 1 }} />
        </View>
      );
      break;
    }
    case HomeState.MOVING_TO_CHARGER:
    case HomeState.CHARGING:
    case HomeState.CHARGE_DONE:
    case HomeState.MOVING_TO_PARKING:
    case HomeState.PARKED:
      title = PROGRESS_TITLE[hs]!;
      titleColor = C.active;
      showCharge = !!v.charge;
      body = <Steps steps={progressSteps(v)} />;
      if (hs === HomeState.MOVING_TO_CHARGER || hs === HomeState.CHARGING)
        footer = <Button kind="outline" label="충전 요청 취소" onPress={cancel} loading={busy} />;
      if (hs === HomeState.PARKED) footer = <Button label="결과 보기" onPress={() => router.push('/result')} />;
      break;
    case HomeState.VEHICLE_OFFLINE:
      title = '차량 신호를 기다려요';
      titleColor = C.sub;
      body = v.step ? <Steps steps={progressSteps(v)} /> : null;
      if (req) footer = <Button kind="outline" label="충전 요청 취소" onPress={cancel} loading={busy} />;
      break;
    case HomeState.CANCELING: {
      const moving = v.state === VehicleState.MOVING_TO_CHARGER || v.state === VehicleState.MOVING_TO_PARKING;
      title = moving ? '차량을 옮기는 중' : '취소를 접수했어요';
      showMetrics = false;
      body = (
        <Steps
          steps={[
            {
              title: '취소 접수',
              status: moving ? 'done' : 'current',
              sub: moving ? undefined : '관제에 취소를 전달하고 있어요',
            },
            {
              title: '안전한 지점으로 이동',
              status: moving ? 'current' : 'todo',
              sub: moving ? '충전을 멈추고 안전한 지점으로 가요' : undefined,
            },
            { title: '취소 완료', status: 'todo' },
          ]}
        />
      );
      break;
    }
    case HomeState.CANCELLED:
      title = '취소가 끝났어요';
      showMetrics = false;
      body = (
        <Steps
          steps={[
            { title: '취소 접수', status: 'done' },
            { title: '안전한 지점으로 이동', status: 'done' },
            { title: '취소 완료', status: 'done' },
          ]}
        />
      );
      footer = <Button label="다시 요청하기" onPress={goRequest} />;
      break;
    case HomeState.REQUEST_FAILED:
      title = '충전을 못 했어요';
      showMetrics = false;
      body = (
        <Notice
          eyebrow="사유"
          body={v.last_request?.failure_reason ?? '요청을 처리하지 못했어요.'}
          sub="차량은 원래 자리에 그대로 있어요. 시각을 바꿔 다시 요청해 주세요."
        />
      );
      footer = <Button label="다시 요청하기" onPress={goRequest} />;
      break;
    case HomeState.FAULT:
      title = '차량 점검 중';
      showMetrics = false;
      body = (
        <Notice
          alert
          eyebrow="상황"
          body="이상이 감지되어 관제가 확인하고 있어요. 차량은 안전한 상태로 멈춰 있어요."
          sub="확인이 끝나면 알려 드릴게요. 급한 일이 있으면 아래로 문의해 주세요."
        />
      );
      footer = <Button kind="outline" label="관제에 문의하기" onPress={contactCenter} />;
      break;
  }

  return (
    <Screen tabs footer={footer}>
      <TopBar />
      {banner}
      <CarHero height={banner ? 120 : 160} onMap={() => setMapOpen(true)} />
      <StatusBlock plate={v.plate_no} title={title} color={titleColor} />
      {showMetrics ? (
        <View style={{ gap: 12 }}>
          <MetricRow items={metrics} />
          <SocBar soc={v.soc} target={req?.target_soc ?? 80} />
          {showCharge && v.charge ? (
            <MetricRow
              items={[
                { label: '충전량', value: v.charge.energy_kwh.toFixed(1), unit: 'kWh' },
                { label: '충전 금액', value: won(v.charge.cost_won), unit: '원' },
              ]}
            />
          ) : null}
        </View>
      ) : null}
      {body}
      <Dialog
        visible={cancelOpen}
        title="요청을 취소할까요?"
        body={
          hs === HomeState.QUEUED
            ? '취소하면 대기 순서가 사라져요. 다시 충전하려면 새로 요청해야 해요.'
            : '진행 중인 이동·충전을 멈추고 차량을 안전한 지점으로 옮겨요.'
        }
        keepLabel="계속 유지"
        confirmLabel="요청 취소"
        loading={busy}
        onKeep={() => setCancelOpen(false)}
        onConfirm={confirmCancel}
      />
      {/* 전체 구역 지도. 요청 전이면 고른 자리로 충전 요청 화면을 연다 */}
      <ParkingMap
        visible={mapOpen}
        selected={req?.parking_area ?? null}
        onClose={() => setMapOpen(false)}
        onPick={(a) => {
          setMapOpen(false);
          if (!req && a) router.navigate({ pathname: '/request', params: { area: a } });
        }}
      />
    </Screen>
  );
}

function Onboarding({ current }: { current: number }) {
  return (
    <View style={{ gap: 12, paddingTop: 8 }}>
      {['차량 등록', '관리자 배정', '충전 요청'].map((t, i) => {
        const n = i + 1;
        const color = n < current ? C.text : n === current ? C.warning : C.muted;
        return (
          <View key={t} style={{ flexDirection: 'row', gap: 14 }}>
            <T mono style={{ color, fontSize: 14 }}>
              {n}
            </T>
            <T style={{ fontSize: 15 }}>{t}</T>
          </View>
        );
      })}
    </View>
  );
}
