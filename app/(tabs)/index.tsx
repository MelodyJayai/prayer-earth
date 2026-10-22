import { useRouter, type Href } from "expo-router";
import { useCallback } from "react";
import { ScreenFrame } from "../../src/components/ScreenFrame";
import { usePrayers } from "../../src/context/PrayerContext";
import type { AppTab } from "../../src/domain/types";
import { useContentFeed } from "../../src/hooks/useContentFeed";
import { HomeScreen } from "../../src/screens/HomeScreen";

const tabRoutes: Record<AppTab, Href> = {
  首页: "/",
  祷告: "/prayers",
  见证: "/testimonies",
  我的: "/profile",
};

export default function HomeRoute() {
  const router = useRouter();
  const { prayers, togglePrayer } = usePrayers();
  const { items } = useContentFeed();
  const openPrayer = useCallback(
    (id: string) => router.push({ pathname: "/prayer/[id]", params: { id } }),
    [router],
  );
  const openTab = useCallback(
    (tab: AppTab) => router.navigate(tabRoutes[tab]),
    [router],
  );
  return (
    <ScreenFrame>
      {(wide) => (
        <HomeScreen
          wide={wide}
          prayers={prayers}
          contentItems={items}
          onPray={togglePrayer}
          onOpen={openPrayer}
          onTab={openTab}
        />
      )}
    </ScreenFrame>
  );
}
