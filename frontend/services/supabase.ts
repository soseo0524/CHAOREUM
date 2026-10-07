import 'expo-sqlite/localStorage/install';
import { createClient } from '@supabase/supabase-js';
import * as Linking from 'expo-linking';
import { AppState } from 'react-native';

const url = process.env.EXPO_PUBLIC_SUPABASE_URL ?? '';
const key = process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? '';

export const supabaseConfigured = Boolean(url && key);

export const supabase = createClient(url || 'https://invalid.supabase.co', key || 'missing', {
  auth: { storage: localStorage, autoRefreshToken: true, persistSession: true, detectSessionInUrl: false },
});

AppState.addEventListener('change', (s) => {
  if (s === 'active') supabase.auth.startAutoRefresh();
  else supabase.auth.stopAutoRefresh();
});

/** 비밀번호 재설정 메일. 링크는 앱의 /reset-password로 돌아온다(Supabase > Authentication > URL Configuration의 Redirect URLs에 등록 필요) */
export function sendResetMail(email: string) {
  return supabase.auth.resetPasswordForEmail(email, { redirectTo: Linking.createURL('reset-password') });
}
