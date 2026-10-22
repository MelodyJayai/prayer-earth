import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import type { Prayer, PrayerCategory, PrayerFilter } from "../domain/types";
import {
  createOutboxEvent,
  type OutboxEvent,
  type PrayerSnapshot,
} from "../services/prayerStorage";
import {
  localPrayerRepository,
  type PrayerRepository,
} from "../repositories/prayerRepository";
import { initialPrayerState, prayerReducer } from "../state/prayerReducer";
import { runStartupSync } from "../services/startupSync";

/**
 * Local storage is normally synchronous on web and quick over the native
 * bridge.  A broken browser storage provider must not leave the whole app on
 * the splash screen forever, though, so the first render has a bounded wait.
 */
export const LOCAL_HYDRATION_TIMEOUT_MS = 2500;

const emptySnapshot = (): PrayerSnapshot => ({
  prayedIds: [],
  publishedPrayers: [],
  outboxEvents: [],
});

export type LocalHydrationResult = {
  snapshot: PrayerSnapshot;
  timedOut: boolean;
  error?: unknown;
};

/**
 * Load the local cache without allowing a stalled storage implementation to
 * block the navigation tree indefinitely.  The storage promise is still
 * observed so a late rejection cannot become an unhandled rejection.
 */
export async function loadSnapshotWithinTimeout(
  repository: PrayerRepository,
  timeoutMs = LOCAL_HYDRATION_TIMEOUT_MS,
): Promise<LocalHydrationResult> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const load = Promise.resolve()
    .then(() => repository.loadSnapshot())
    .then((snapshot) => ({ snapshot, timedOut: false as const }))
    .catch((error: unknown) => ({ snapshot: emptySnapshot(), timedOut: false as const, error }));
  const timeout = new Promise<LocalHydrationResult>((resolve) => {
    timer = setTimeout(() => resolve({ snapshot: emptySnapshot(), timedOut: true }), timeoutMs);
  });
  try {
    return await Promise.race([load, timeout]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

type NewPrayer = {
  title: string;
  excerpt: string;
  category: PrayerCategory;
};

export function usePrayerStore(repository: PrayerRepository = localPrayerRepository) {
  const [state, dispatch] = useReducer(prayerReducer, initialPrayerState);
  const [storageWarning, setStorageWarning] = useState<string | null>(null);
  const [persistenceReady, setPersistenceReady] = useState(false);
  const persistenceReadyRef = useRef(false);
  const saveQueue = useRef<Promise<void>>(Promise.resolve());
  const outboxEvents = useRef<OutboxEvent[]>([]);

  useEffect(() => {
    let active = true;
    void loadSnapshotWithinTimeout(repository).then(({ snapshot, timedOut, error }) => {
      if (!active) return;
      outboxEvents.current = snapshot.outboxEvents;
      if (timedOut) {
        // Do not write this fallback over a cache that may still be readable.
        // Content remains usable for this session; local persistence resumes
        // on the next load once storage responds normally.
        setStorageWarning("本地记录读取较慢，已继续打开内容；本次祷告记录暂不保存。");
      } else if (error) {
        setStorageWarning("本地记录暂时无法读取，本次使用仍可继续。");
      } else {
        persistenceReadyRef.current = true;
        setPersistenceReady(true);
      }
      dispatch({ type: "hydrate", snapshot });
    });
    return () => {
      active = false;
    };
  }, [repository]);

  useEffect(() => {
    if (!state.hydrated || !persistenceReady) return;
    const snapshot: PrayerSnapshot = {
      prayedIds: state.prayers
        .filter(({ prayedByMe }) => prayedByMe)
        .map(({ id }) => id),
      publishedPrayers: state.prayers
        .filter(({ source }) => source === "user" || source === "seed")
        .slice(0, 100),
      outboxEvents: outboxEvents.current,
    };
    saveQueue.current = saveQueue.current
      .catch(() => undefined)
      .then(() => repository.saveSnapshot(snapshot))
      .catch(() => setStorageWarning("祷告记录暂时未能保存，请稍后重试。"));
  }, [persistenceReady, repository, state.hydrated, state.prayers]);

  useEffect(() => {
    if (!state.hydrated) return;
    let active = true;
    runStartupSync({ localRepository: repository })
      .then((result) => {
        if (!active) return;
        outboxEvents.current = result.snapshot.outboxEvents;
        if (result.remotePrayers.length) {
          dispatch({
            type: "syncRemote",
            prayers: result.remotePrayers,
            pendingPrayerIds: result.snapshot.outboxEvents
              .filter(
                ({ aggregateType, aggregateId, status }) =>
                  aggregateType === "prayer_action" &&
                  Boolean(aggregateId) &&
                  status !== "succeeded" &&
                  status !== "dead",
              )
              .map(({ aggregateId }) => aggregateId as string),
          });
        }
        if (result.remoteError) {
          setStorageWarning("云端同步暂时不可用，当前仍可继续离线使用。");
        }
      })
      .catch(() => {
        if (active) setStorageWarning("云端同步暂时不可用，当前仍可继续离线使用。");
      });
    return () => {
      active = false;
    };
  }, [repository, state.hydrated]);

  const togglePrayer = useCallback((id: string) => {
    const current = state.prayers.find(({ id: prayerId }) => prayerId === id);
    if (!current) return;
    const prayed = !current.prayedByMe;
    const event = createOutboxEvent({
      aggregateType: "prayer_action",
      aggregateId: id,
      eventType: prayed ? "prayer.pray" : "prayer.unpray",
      payload: { prayed, prayerId: id },
    });
    if (!outboxEvents.current.some(({ idempotencyKey }) => idempotencyKey === event.idempotencyKey)) {
      outboxEvents.current = [...outboxEvents.current, event];
    }
    dispatch({ type: "toggle", id });
    if (!persistenceReadyRef.current) {
      setStorageWarning("本地记录尚未准备好，当前祷告仅保留在本次页面中。");
      return;
    }
    saveQueue.current = saveQueue.current
      .catch(() => undefined)
      .then(() => repository.enqueueOutboxEvent(event))
      .catch(() => setStorageWarning("祷告动作已暂存，但暂时无法加入同步队列。"));
  }, [repository, state.prayers]);

  const clearStorageWarning = useCallback(() => setStorageWarning(null), []);

  const publishPrayer = useCallback((input: NewPrayer): Prayer => {
    const prayer: Prayer = {
      id: `user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      title: input.title,
      excerpt: input.excerpt,
      location: "来自你的祷告",
      flag: "🌏",
      category: input.category,
      prayerCount: 1,
      createdAt: new Date().toISOString(),
      urgent: false,
      prayedByMe: true,
      source: "user",
    };
    const event = createOutboxEvent({
      aggregateType: "prayer",
      aggregateId: prayer.id,
      eventType: "prayer.create",
      payload: { prayer },
      idempotencyKey: `prayer-create:${prayer.id}`,
    });
    outboxEvents.current = [...outboxEvents.current, event];
    dispatch({ type: "publish", prayer });
    if (!persistenceReadyRef.current) {
      setStorageWarning("本地记录尚未准备好，当前祷告仅保留在本次页面中。");
      return prayer;
    }
    saveQueue.current = saveQueue.current
      .catch(() => undefined)
      .then(() => repository.enqueueOutboxEvent(event))
      .catch(() => setStorageWarning("祷告已显示，但暂时无法加入同步队列。"));
    return prayer;
  }, [repository]);

  const getFilteredPrayers = useCallback(
    (filter: PrayerFilter) =>
      state.prayers.filter(
        (prayer) =>
          filter === "全部" ||
          (filter === "紧急" ? prayer.urgent : prayer.category === filter),
      ),
    [state.prayers],
  );

  return useMemo(
    () => ({
      prayers: state.prayers,
      hydrated: state.hydrated,
      storageWarning,
      clearStorageWarning,
      togglePrayer,
      publishPrayer,
      getFilteredPrayers,
    }),
    [
      clearStorageWarning,
      getFilteredPrayers,
      publishPrayer,
      state.hydrated,
      state.prayers,
      storageWarning,
      togglePrayer,
    ],
  );
}
