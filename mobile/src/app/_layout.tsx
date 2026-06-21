import { useEffect } from "react";
import { ActivityIndicator, View } from "react-native";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";

import { AuthProvider, useAuth } from "@/lib/auth";
import { Colors } from "@/lib/colors";

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  return (
    <AuthProvider>
      <RootNavigator />
    </AuthProvider>
  );
}

function RootNavigator() {
  const { user, loading } = useAuth();

  useEffect(() => {
    if (!loading) SplashScreen.hideAsync();
  }, [loading]);

  if (loading) {
    // El splash sigue visible encima; este fallback evita parpadeos.
    return (
      <View style={{ flex: 1, backgroundColor: Colors.navy, alignItems: "center", justifyContent: "center" }}>
        <ActivityIndicator color={Colors.orange} size="large" />
      </View>
    );
  }

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={!!user}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen
          name="leccion/[id]/estudiar"
          options={{ headerShown: true, title: "Estudiar", headerTintColor: Colors.navy }}
        />
        <Stack.Screen
          name="leccion/[id]/practicar"
          options={{ headerShown: true, title: "Practicar", headerTintColor: Colors.navy }}
        />
      </Stack.Protected>
      <Stack.Protected guard={!user}>
        <Stack.Screen name="login" />
      </Stack.Protected>
    </Stack>
  );
}
