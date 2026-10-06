import { Check, ChevronLeft, ChevronRight, EyeOff, Eye, type LucideIcon } from 'lucide-react-native';
import { useState, type ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type TextInputProps,
  type TextProps,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { C, F } from '@/constants/theme';

export function T({ style, mono, medium, ...p }: TextProps & { mono?: boolean; medium?: boolean }) {
  return (
    <Text
      {...p}
      style={[{ color: C.text, fontFamily: mono ? F.mono : medium ? F.medium : F.regular }, style]}
    />
  );
}

/** 화면 바탕. scroll=false면 내용과 footer를 위아래로 벌린다(space_between). */
export function Screen({
  children,
  footer,
  scroll = true,
  tabs = false,
  contentStyle,
}: {
  children: ReactNode;
  footer?: ReactNode;
  scroll?: boolean;
  tabs?: boolean;
  contentStyle?: ViewStyle;
}) {
  const inner = <View style={[{ gap: 16 }, contentStyle]}>{children}</View>;
  return (
    <SafeAreaView style={s.screen} edges={tabs ? ['top'] : ['top', 'bottom']}>
      {scroll ? (
        <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
          {inner}
          {footer ? <View style={s.footer}>{footer}</View> : null}
        </ScrollView>
      ) : (
        <View style={[s.scroll, { flex: 1, justifyContent: 'space-between' }]}>
          {inner}
          {footer ? <View style={s.footer}>{footer}</View> : null}
        </View>
      )}
    </SafeAreaView>
  );
}

export function Wordmark() {
  return <T style={{ fontSize: 14, letterSpacing: 3 }}>CHAOREUM</T>;
}

export function BackBar({ onPress }: { onPress: () => void }) {
  return (
    <Pressable onPress={onPress} hitSlop={12} style={{ height: 40, justifyContent: 'center' }}>
      <ChevronLeft size={22} color={C.text} />
    </Pressable>
  );
}

export function Title({ children, eyebrow, size = 34 }: { children: ReactNode; eyebrow?: string; size?: number }) {
  return (
    <View style={{ gap: 6 }}>
      {eyebrow ? <T style={{ color: C.sub, fontSize: 12, letterSpacing: 1 }}>{eyebrow}</T> : null}
      <T style={{ fontSize: size, letterSpacing: size >= 34 ? -1.2 : -1, lineHeight: size * 1.3 }}>{children}</T>
    </View>
  );
}

type BtnKind = 'primary' | 'outline' | 'danger' | 'ghost';
export function Button({
  label,
  onPress,
  kind = 'primary',
  loading,
  disabled,
  style,
}: {
  label: string;
  onPress: () => void;
  kind?: BtnKind;
  loading?: boolean;
  disabled?: boolean;
  style?: ViewStyle;
}) {
  const k = {
    primary: { bg: C.primary, border: 'transparent', color: '#000000' },
    outline: { bg: 'transparent', border: C.outline, color: C.text },
    danger: { bg: 'transparent', border: '#ff373766', color: C.error },
    ghost: { bg: 'transparent', border: 'transparent', color: C.sub },
  }[kind];
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        s.btn,
        { backgroundColor: k.bg, borderColor: k.border, opacity: disabled ? 0.4 : pressed ? 0.7 : 1 },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={k.color} />
      ) : (
        <T medium={kind !== 'ghost'} style={{ color: k.color, fontSize: kind === 'ghost' ? 14 : 15 }}>
          {label}
        </T>
      )}
    </Pressable>
  );
}

export function Field({ label, secure, ...p }: TextInputProps & { label: string; secure?: boolean }) {
  const [hidden, setHidden] = useState(true);
  const Eyeicon = hidden ? EyeOff : Eye;
  return (
    <View style={{ gap: 8 }}>
      <T style={{ color: C.sub, fontSize: 12 }}>{label}</T>
      <View style={s.input}>
        <TextInput
          placeholderTextColor={C.muted}
          autoCapitalize="none"
          {...p}
          secureTextEntry={secure && hidden}
          style={{ flex: 1, color: C.text, fontSize: 15, fontFamily: F.regular, height: '100%' }}
        />
        {secure ? (
          <Pressable onPress={() => setHidden(!hidden)} hitSlop={10}>
            <Eyeicon size={18} color={C.muted} />
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

export function Checkbox({ checked, onPress, label }: { checked: boolean; onPress: () => void; label: string }) {
  return (
    <Pressable onPress={onPress} style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
      <View style={[s.check, checked ? { backgroundColor: C.primary } : { borderWidth: 1, borderColor: C.muted }]}>
        {checked ? <Check size={12} color="#000000" strokeWidth={3} /> : null}
      </View>
      <T style={{ color: C.sub, fontSize: 12, flex: 1 }}>{label}</T>
    </Pressable>
  );
}

/** 아래 테두리가 있는 '라벨 — 값 >' 행 */
export function Row({
  label,
  children,
  onPress,
  chevron = !!onPress,
}: {
  label: string;
  children?: ReactNode;
  onPress?: () => void;
  chevron?: boolean;
}) {
  return (
    <Pressable onPress={onPress} disabled={!onPress} style={s.row}>
      <T style={{ color: C.sub, fontSize: 14 }}>{label}</T>
      <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
        {children}
        {chevron ? <ChevronRight size={16} color={C.muted} /> : null}
      </View>
    </Pressable>
  );
}

export function EmptyHero({ icon: Icon, size = 48 }: { icon: LucideIcon; size?: number }) {
  return (
    <View style={s.emptyHero}>
      <Icon size={size} color={C.muted} />
    </View>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  scroll: { paddingHorizontal: 24, paddingTop: 4, paddingBottom: 16, flexGrow: 1, justifyContent: 'space-between' },
  footer: { gap: 10, paddingTop: 18 },
  btn: { height: 48, borderRadius: 9999, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  input: {
    height: 52,
    backgroundColor: C.surface,
    borderRadius: 8,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  check: { width: 18, height: 18, borderRadius: 4, alignItems: 'center', justifyContent: 'center' },
  row: {
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: C.line,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  emptyHero: { height: 110, backgroundColor: C.hero, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
});
