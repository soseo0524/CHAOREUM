import { Stack } from 'expo-router';

import { C } from '@/constants/theme';
import { StatusProvider } from '@/hooks/useStatus';

export const unstable_settings = { initialRouteName: '(tabs)' };

export default function UserLayout() {
  return (
    <StatusProvider>
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: C.bg } }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="vehicle-new" options={{ presentation: 'modal' }} />
      </Stack>
    </StatusProvider>
  );
}
