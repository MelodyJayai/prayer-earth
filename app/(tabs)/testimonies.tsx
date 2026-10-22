import { useRouter } from "expo-router";
import { useCallback } from "react";
import { ScreenFrame } from "../../src/components/ScreenFrame";
import { useContentFeed } from "../../src/hooks/useContentFeed";
import { ContentLibraryScreen } from "../../src/screens/ContentLibraryScreen";

export default function TestimoniesRoute() {
  const router = useRouter();
  const { items, refresh, refreshing, error } = useContentFeed();
  const openContent = useCallback(
    (id: string) => router.push({ pathname: "/content/[id]", params: { id } }),
    [router],
  );
  return (
    <ScreenFrame>{() => <ContentLibraryScreen items={items} onOpen={openContent} onRefresh={refresh} refreshing={refreshing} updateError={error} />}</ScreenFrame>
  );
}
