import { useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ScreenFrame } from "../../src/components/ScreenFrame";
import { usePrayers } from "../../src/context/PrayerContext";
import type { PrayerFilter } from "../../src/domain/types";
import { PrayerListScreen } from "../../src/screens/PrayerListScreen";

export default function PrayersRoute() {
  const router = useRouter();
  const [filter, setFilter] = useState<PrayerFilter>("全部");
  const { togglePrayer, prayers, feedStatus } = usePrayers();
  const openPrayer = useCallback(
    (id: string) => router.push({ pathname: "/prayer/[id]", params: { id } }),
    [router],
  );
  return (
    <ScreenFrame>
      {() => (
        <PrayerListScreen
          filter={filter}
          onFilter={setFilter}
          prayers={prayers}
          feedStatus={feedStatus}
          onPray={togglePrayer}
          onOpen={openPrayer}
        />
      )}
    </ScreenFrame>
  );
}
