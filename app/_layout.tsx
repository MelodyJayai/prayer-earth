import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import {
  SafeAreaProvider,
  initialWindowMetrics,
} from "react-native-safe-area-context";
import { AppErrorBoundary } from "../src/components/AppErrorBoundary";
import { PrayerProvider } from "../src/context/PrayerContext";

export default function RootLayout() {
  return (
    <AppErrorBoundary>
      <SafeAreaProvider initialMetrics={initialWindowMetrics}>
        <StatusBar style="dark" />
        <PrayerProvider>
          <Stack screenOptions={{ headerShown: false }}>
            <Stack.Screen name="(tabs)" />
            <Stack.Screen name="compose" options={{ presentation: "modal" }} />
            <Stack.Screen name="content/[id]" />
            <Stack.Screen
              name="prayer/[id]"
              options={{ presentation: "transparentModal", animation: "fade" }}
            />
          </Stack>
        </PrayerProvider>
      </SafeAreaProvider>
    </AppErrorBoundary>
  );
}
