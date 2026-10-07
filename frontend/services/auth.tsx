import type { Session } from '@supabase/supabase-js';
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { Alert } from 'react-native';

import { AppRole, type Profile } from '@/constants/types';
import { api } from './api';
import { supabase } from './supabase';

type AuthCtx = {
  session: Session | null;
  profile: Profile | null;
  loading: boolean;
  refreshProfile: () => Promise<Profile | null>;
  signOut: () => Promise<void>;
  /** 비밀번호 재설정 링크로 들어와 임시 세션이 있는 동안 true. 이때는 홈 대신 새 비밀번호 화면에 머문다 */
  recovering: boolean;
  setRecovering: (v: boolean) => void;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [recovering, setRecovering] = useState(false);

  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
    setProfile(null);
  }, []);

  const refreshProfile = useCallback(async () => {
    try {
      let p = await api.me();
      if (p.app_role === AppRole.ADMIN) {
        Alert.alert('관리자 계정', '관리자는 웹사이트에서 이용해 주세요.');
        await signOut();
        return null;
      }
      // 가입할 때 적은 이름을 첫 로그인 때 프로필에 옮긴다
      const name = (await supabase.auth.getUser()).data.user?.user_metadata?.name;
      if (!p.name && name) p = await api.updateMe({ name });
      setProfile(p);
      return p;
    } catch (e: any) {
      Alert.alert('서버 연결 실패', e.message);
      return null;
    }
  }, [signOut]);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (session && !recovering) refreshProfile();
    else setProfile(null);
  }, [session?.user.id, recovering]); // eslint-disable-line react-hooks/exhaustive-deps

  return <Ctx.Provider value={{ session, profile, loading, refreshProfile, signOut, recovering, setRecovering }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error('AuthProvider missing');
  return c;
}
