import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useMemo } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { PrayerDetail } from "../../src/components/PrayerDetail";
import { usePrayers } from "../../src/context/PrayerContext";
import { colors } from "../../src/theme";

export default function PrayerDetailRoute() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { prayers, hydrated, togglePrayer } = usePrayers();
  const prayer = useMemo(
    () => prayers.find((item) => item.id === id) ?? null,
    [id, prayers],
  );
  const close = useCallback(() => router.back(), [router]);
  if (!hydrated) {
    return (
      <View style={styles.state}>
        <ActivityIndicator color={colors.green} />
      </View>
    );
  }
  if (!prayer) {
    return (
      <View style={styles.state}>
        <Text style={styles.title}>没有找到这条祷告</Text>
        <Text style={styles.body}>它可能已被删除，或链接已经失效。</Text>
        <Pressable
          accessibilityRole="button"
          onPress={close}
          style={styles.button}
        >
          <Text style={styles.buttonText}>返回祷告列表</Text>
        </Pressable>
      </View>
    );
  }
  return (
    <PrayerDetail
      prayer={prayer}
      onClose={close}
      onPray={togglePrayer}
      asModal={false}
    />
  );
}

const styles = StyleSheet.create({
  state: {
    flex: 1,
    backgroundColor: colors.cream,
    alignItems: "center",
    justifyContent: "center",
    padding: 28,
  },
  title: { color: colors.ink, fontSize: 20, fontWeight: "700" },
  body: { color: colors.inkSoft, fontSize: 14, marginTop: 8 },
  button: {
    minHeight: 48,
    borderRadius: 24,
    backgroundColor: colors.green,
    paddingHorizontal: 22,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 22,
  },
  buttonText: { color: colors.white, fontSize: 14, fontWeight: "700" },
});
