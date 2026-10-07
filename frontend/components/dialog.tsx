// 확인 대화상자(02-A.05, 06.04, 06.05, 07.03)와 토글(06.03)
import { Modal, Pressable, View } from 'react-native';

import { C } from '@/constants/theme';
import { Button, T } from './ui';

export function Dialog({
  visible,
  title,
  body,
  keepLabel = '취소',
  confirmLabel,
  onKeep,
  onConfirm,
  loading,
}: {
  visible: boolean;
  title: string;
  body: string;
  keepLabel?: string;
  confirmLabel: string;
  onKeep: () => void;
  onConfirm: () => void;
  loading?: boolean;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onKeep}>
      <Pressable
        onPress={onKeep}
        style={{ flex: 1, backgroundColor: '#000000B3', justifyContent: 'center', paddingHorizontal: 32 }}
      >
        <Pressable
          style={{
            backgroundColor: C.surface,
            borderRadius: 8,
            borderWidth: 1,
            borderColor: C.line,
            padding: 24,
            gap: 12,
          }}
        >
          <T style={{ fontSize: 18 }}>{title}</T>
          <T style={{ color: C.sub, fontSize: 13, lineHeight: 20 }}>{body}</T>
          <View style={{ flexDirection: 'row', gap: 10, paddingTop: 8 }}>
            <Button kind="outline" label={keepLabel} onPress={onKeep} style={{ flex: 1 }} />
            <Button kind="destructive" label={confirmLabel} onPress={onConfirm} loading={loading} style={{ flex: 1 }} />
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

export function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <Pressable
      onPress={() => onChange(!value)}
      hitSlop={8}
      style={{
        width: 46,
        height: 28,
        borderRadius: 14,
        padding: 3,
        backgroundColor: value ? '#ffffff' : '#2a2a2a',
        alignItems: value ? 'flex-end' : 'flex-start',
        justifyContent: 'center',
      }}
    >
      <View style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: value ? '#000000' : C.muted }} />
    </Pressable>
  );
}
