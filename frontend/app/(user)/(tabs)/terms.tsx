// 이용약관 · 개인정보 처리방침 (초안 문구 — 정식 문서로 바꿔야 함)
import { router } from 'expo-router';
import { View } from 'react-native';

import { BackBar, Screen, T, Title } from '@/components/ui';
import { C } from '@/constants/theme';

const SECTIONS = [
  {
    title: '서비스 내용',
    body: '등록한 차량을 관제 시스템이 충전소로 옮겨 충전하고, 끝나면 고른 주차 구역으로 옮겨 드려요.',
  },
  {
    title: '수집하는 정보',
    body: '이름, 이메일, 휴대전화(선택), 차량 번호·모델·배터리 용량, 충전 요청 기록, 차량 위치와 배터리 상태(요청 진행 중에만).',
  },
  {
    title: '이용 목적과 보관 기간',
    body: '충전·주차 처리, 알림 발송, 요금 계산에만 써요. 회원 탈퇴 시 개인정보는 바로 지우고, 충전 이력은 개인을 알아볼 수 없게 해서 남겨요.',
  },
  {
    title: '문의',
    body: '개인정보 관련 문의는 관제실로 연락해 주세요.',
  },
];

export default function Terms() {
  return (
    <Screen tabs contentStyle={{ gap: 20 }}>
      <BackBar onPress={() => router.back()} />
      <Title eyebrow="내 정보" size={32}>
        이용약관 · 개인정보 처리방침
      </Title>
      {SECTIONS.map((s) => (
        <View key={s.title} style={{ gap: 6 }}>
          <T style={{ fontSize: 15 }}>{s.title}</T>
          <T style={{ color: C.sub, fontSize: 13, lineHeight: 20 }}>{s.body}</T>
        </View>
      ))}
    </Screen>
  );
}
