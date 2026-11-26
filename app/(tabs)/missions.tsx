import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ScreenFrame } from "../../src/components/ScreenFrame";
import { MissionsScreen, type MissionsStatus } from "../../src/screens/MissionsScreen";
import { fetchMissions, type MissionItem } from "../../src/services/missionsFeed";

export default function MissionsRoute() {
  const router = useRouter();
  const [items, setItems] = useState<MissionItem[]>([]);
  const [status, setStatus] = useState<MissionsStatus>("loading");
  const [reloadKey, setReloadKey] = useState(0);
  useEffect(() => {
    let alive = true;
    fetchMissions().then(
      (next) => {
        if (!alive) return;
        setItems(next);
        setStatus("ready");
      },
      () => {
        if (alive) setStatus("error");
      },
    );
    return () => {
      alive = false;
    };
  }, [reloadKey]);
  const refresh = useCallback(() => {
    setStatus("loading");
    setReloadKey((value) => value + 1);
  }, []);
  const switchSection = useCallback(() => router.navigate("/prayers"), [router]);
  return (
    <ScreenFrame>
      {() => <MissionsScreen items={items} status={status} onRefresh={refresh} onSwitchSection={switchSection} />}
    </ScreenFrame>
  );
}
