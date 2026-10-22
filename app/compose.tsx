import { useRouter } from "expo-router";
import { useCallback } from "react";
import { View } from "react-native";
import { PrayerComposer } from "../src/components/PrayerComposer";
import { usePrayers } from "../src/context/PrayerContext";
import type { PrayerCategory } from "../src/domain/types";

export default function ComposeRoute() {
  const router = useRouter();
  const { publishPrayer } = usePrayers();
  const close = useCallback(() => router.back(), [router]);
  const publish = useCallback(
    (input: { title: string; excerpt: string; category: PrayerCategory }) => {
      const prayer = publishPrayer(input);
      router.replace({ pathname: "/prayer/[id]", params: { id: prayer.id } });
    },
    [publishPrayer, router],
  );
  const openGuidelines = useCallback(
    () => router.push("/legal/community"),
    [router],
  );
  return (
    <View style={{ flex: 1 }}>
      <PrayerComposer
        visible
        asModal={false}
        onClose={close}
        onOpenGuidelines={openGuidelines}
        onPublish={publish}
      />
    </View>
  );
}
