import { JetBrainsMono_400Regular } from '@expo-google-fonts/jetbrains-mono';
import { NotoSansKR_400Regular, NotoSansKR_500Medium } from '@expo-google-fonts/noto-sans-kr';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { C } from '@/constants/theme';
import { AuthProvider, useAuth } from '@/services/auth';

function RootStack() {
  const { session, loading, recovering } = useAuth();
  if (loading) return <View style={{ flex: 1, backgroundColor: C.bg }} />;
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: C.bg } }}>
      <Stack.Protected guard={!session && !recovering}>
        <Stack.Screen name="(auth)" />
      </Stack.Protected>
      <Stack.Protected guard={!!session && !recovering}>
        <Stack.Screen name="(user)" />
      </Stack.Protected>
      {/* 09.03 재설정 메일의 링크(aiot://reset-password#access_token=...)로 들어오는 화면 */}
      <Stack.Protected guard={!session || recovering}>
        <Stack.Screen name="reset-password" />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  const [fontsLoaded] = useFonts({ NotoSansKR_400Regular, NotoSansKR_500Medium, JetBrainsMono_400Regular });
  if (!fontsLoaded) return <View style={{ flex: 1, backgroundColor: C.bg }} />;
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <StatusBar style="light" />
        <RootStack />
      </AuthProvider>
    </SafeAreaProvider>
  );
}
