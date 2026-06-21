import { Tabs } from "expo-router";
import { Text } from "react-native";

import { Colors } from "@/lib/colors";

function TabIcon({ emoji, focused }: { emoji: string; focused: boolean }) {
  return <Text style={{ fontSize: 22, opacity: focused ? 1 : 0.55 }}>{emoji}</Text>;
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: Colors.orange,
        tabBarInactiveTintColor: "#94A3B8",
        tabBarStyle: {
          backgroundColor: Colors.navy,
          borderTopColor: Colors.navy,
          height: 64,
          paddingBottom: 8,
          paddingTop: 6,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "800" },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: "Mi Ruta", tabBarIcon: ({ focused }) => <TabIcon emoji="🗺️" focused={focused} /> }}
      />
      <Tabs.Screen
        name="progreso"
        options={{ title: "Progreso", tabBarIcon: ({ focused }) => <TabIcon emoji="📊" focused={focused} /> }}
      />
      <Tabs.Screen
        name="ranking"
        options={{ title: "Ranking", tabBarIcon: ({ focused }) => <TabIcon emoji="🏆" focused={focused} /> }}
      />
    </Tabs>
  );
}
