import { useRouter } from "expo-router";
import { useCallback, useMemo } from "react";
import { Linking, Platform } from "react-native";
import { ScreenFrame } from "../../src/components/ScreenFrame";
import { usePrayers } from "../../src/context/PrayerContext";
import { ProfileScreen } from "../../src/screens/ProfileScreen";

export default function ProfileRoute() {
  const router = useRouter();
  const { prayers } = usePrayers();
  const prayerCount = useMemo(
    () => prayers.filter(({ prayedByMe }) => prayedByMe).length,
    [prayers],
  );
  const openPrivacy = useCallback(
    () => router.push("/legal/privacy"),
    [router],
  );
  const openCommunity = useCallback(
    () => router.push("/legal/community"),
    [router],
  );
  const openAbout = useCallback(() => router.push("/about"), [router]);
  const openAdmin = useCallback(() => {
    if (Platform.OS === "web" && typeof window !== "undefined") window.location.assign("/admin");
    else void Linking.openURL("https://prayer.diagport.com/admin");
  }, []);
  return (
    <ScreenFrame>
      {() => (
        <ProfileScreen
          prayerCount={prayerCount}
          onPrivacy={openPrivacy}
          onCommunity={openCommunity}
          onAbout={openAbout}
          onAdmin={openAdmin}
        />
      )}
    </ScreenFrame>
  );
}
