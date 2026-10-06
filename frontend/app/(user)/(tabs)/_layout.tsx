import { Tabs } from 'expo-router';
import { House, User, Zap } from 'lucide-react-native';

import { C, F } from '@/constants/theme';

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: C.bg },
        tabBarActiveTintColor: C.text,
        tabBarInactiveTintColor: C.muted,
        tabBarStyle: { backgroundColor: C.bg, borderTopWidth: 0, paddingTop: 8 },
        tabBarLabelStyle: { fontFamily: F.regular, fontSize: 10, marginTop: 3 },
      }}
    >
      <Tabs.Screen name="index" options={{ title: '홈', tabBarIcon: ({ color }) => <House size={22} color={color} /> }} />
      <Tabs.Screen
        name="request"
        options={{ title: '충전 요청', tabBarIcon: ({ color }) => <Zap size={22} color={color} /> }}
      />
      <Tabs.Screen name="me" options={{ title: '내 정보', tabBarIcon: ({ color }) => <User size={22} color={color} /> }} />
      <Tabs.Screen name="history" options={{ href: null }} />
      <Tabs.Screen name="history-detail" options={{ href: null }} />
    </Tabs>
  );
}
