import { Tabs, usePathname, useRouter, type Href } from "expo-router";
import { useCallback } from "react";
import { BottomNav } from "../../src/components/BottomNav";
import type { AppTab } from "../../src/domain/types";

const routes: Record<AppTab, Href> = {
  首页: "/",
  祷告: "/prayers",
  见证: "/testimonies",
  我的: "/profile",
};

export default function TabsLayout() {
  const router = useRouter();
  const pathname = usePathname();
  const active: AppTab = pathname.startsWith("/prayers")
    ? "祷告"
    : pathname.startsWith("/testimonies")
      ? "见证"
      : pathname.startsWith("/profile")
        ? "我的"
        : "首页";
  const navigate = useCallback(
    (tab: AppTab) => router.navigate(routes[tab]),
    [router],
  );
  const compose = useCallback(() => router.push("/compose"), [router]);

  return (
    <Tabs
      screenOptions={{ headerShown: false, lazy: true }}
      tabBar={() => (
        <BottomNav tab={active} onTab={navigate} onCompose={compose} />
      )}
    >
      <Tabs.Screen name="index" options={{ title: "首页" }} />
      <Tabs.Screen name="prayers" options={{ title: "祷告" }} />
      <Tabs.Screen name="testimonies" options={{ title: "晨修与宣教" }} />
      <Tabs.Screen name="profile" options={{ title: "我的" }} />
    </Tabs>
  );
}
