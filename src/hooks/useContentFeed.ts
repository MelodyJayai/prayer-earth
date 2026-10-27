import { useFocusEffect } from "expo-router";
import { useCallback, useEffect, useSyncExternalStore } from "react";
import { Platform } from "react-native";
import { importedContentItems } from "../contentData";
import { fetchContentFeed, type FeedItem } from "../services/contentFeed";

type FeedSnapshot = {
  items: FeedItem[];
  hasChecked: boolean;
  refreshing: boolean;
  error: string | null;
};

// All routes share the latest successful feed. The archive is available immediately.
let snapshot: FeedSnapshot = {
  items: importedContentItems,
  hasChecked: Platform.OS !== "web",
  refreshing: false,
  error: null,
};
const listeners = new Set<() => void>();
let pending: Promise<void> | undefined;
let lastAttempt = 0;

function update(next: FeedSnapshot) {
  snapshot = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function refreshContentFeed(force = false): Promise<void> {
  if (Platform.OS !== "web") return Promise.resolve();
  if (pending) return pending;
  if (!force && Date.now() - lastAttempt < 1500) return Promise.resolve();
  lastAttempt = Date.now();
  update({ ...snapshot, refreshing: true });
  pending = fetchContentFeed()
    .then((items) => { update({ items, refreshing: false, hasChecked: true, error: null }); })
    .catch(() => {
      update({ ...snapshot, refreshing: false, hasChecked: true, error: "暂时无法获取最新内容，已保留可阅读的内容。" });
    })
    .finally(() => { pending = undefined; });
  return pending;
}

export function useContentFeed() {
  const feed = useSyncExternalStore(subscribe, () => snapshot, () => snapshot);
  const refresh = useCallback(() => refreshContentFeed(true), []);

  useFocusEffect(useCallback(() => { void refreshContentFeed(); }, []));

  useEffect(() => {
    if (Platform.OS !== "web" || typeof window === "undefined") return;
    const resume = () => {
      if (document.visibilityState === "visible") void refreshContentFeed();
    };
    window.addEventListener("focus", resume);
    document.addEventListener("visibilitychange", resume);
    return () => {
      window.removeEventListener("focus", resume);
      document.removeEventListener("visibilitychange", resume);
    };
  }, []);

  return { ...feed, refresh };
}
