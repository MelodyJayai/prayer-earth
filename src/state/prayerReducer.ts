import type { Prayer } from "../domain/types";
import type { PrayerSnapshot } from "../services/prayerStorage";

export type PrayerFeedStatus = "loading" | "ready" | "error";

export type PrayerState = {
  prayers: Prayer[];
  retainedPrayers: Prayer[];
  rememberedPrayedIds: string[];
  hydrated: boolean;
  feedStatus: PrayerFeedStatus;
};

export type PrayerAction =
  | { type: "hydrate"; snapshot: PrayerSnapshot }
  | { type: "syncRemote"; prayers: Prayer[]; pendingPrayerIds?: string[] }
  | { type: "replaceNews"; prayers: Prayer[] }
  | { type: "feedFailed" }
  | { type: "toggle"; id: string }
  | { type: "publish"; prayer: Prayer };

export const initialPrayerState: PrayerState = {
  prayers: [],
  retainedPrayers: [],
  rememberedPrayedIds: [],
  hydrated: false,
  feedStatus: "loading",
};

export function persistedPrayedIds(state: PrayerState): string[] {
  const prayed = new Set(state.rememberedPrayedIds);
  for (const prayer of state.prayers) {
    if (prayer.prayedByMe) prayed.add(prayer.id);
    else prayed.delete(prayer.id);
  }
  return [...prayed];
}

/** User prayers stay visible. Previously stored seed rows are written back and not shown. */
export function persistedPublishedPrayers(state: PrayerState): Prayer[] {
  return [
    ...state.prayers.filter((prayer) => prayer.source === "user"),
    ...state.retainedPrayers.filter((prayer) => prayer.source === "seed" || prayer.source === "user"),
  ].slice(0, 100);
}

export function prayerReducer(state: PrayerState, action: PrayerAction): PrayerState {
  switch (action.type) {
    case "hydrate": {
      const prayedIds = action.snapshot.prayedIds;
      const published = action.snapshot.publishedPrayers;
      const users = published
        .filter((prayer) => prayer.source === "user")
        .map((prayer) => ({ ...prayer, prayedByMe: prayedIds.includes(prayer.id) }));
      return {
        ...state,
        prayers: users,
        retainedPrayers: published.filter((prayer) => prayer.source !== "user"),
        rememberedPrayedIds: [...prayedIds],
        hydrated: true,
        feedStatus: "loading",
      };
    }
    case "toggle": {
      const current = state.prayers.find((prayer) => prayer.id === action.id);
      if (!current) return state;
      const prayedByMe = !current.prayedByMe;
      const remembered = new Set(state.rememberedPrayedIds);
      if (prayedByMe) remembered.add(action.id);
      else remembered.delete(action.id);
      return {
        ...state,
        rememberedPrayedIds: [...remembered],
        prayers: state.prayers.map((prayer) =>
          prayer.id === action.id ? { ...prayer, prayedByMe } : prayer,
        ),
      };
    }
    case "replaceNews": {
      const prayed = new Set(persistedPrayedIds(state));
      const users = state.prayers.filter((prayer) => prayer.source === "user");
      const news = action.prayers.map((prayer) => ({
        ...prayer,
        source: "news" as const,
        prayedByMe: prayed.has(prayer.id),
        prayerCount: 0,
      }));
      return { ...state, prayers: [...news, ...users], feedStatus: "ready" };
    }
    case "feedFailed":
      return {
        ...state,
        feedStatus: state.prayers.some((prayer) => prayer.source === "news") ? "ready" : "error",
      };
    case "syncRemote": {
      const byId = new Map(state.prayers.map((prayer) => [prayer.id, prayer]));
      const pendingIds = new Set(action.pendingPrayerIds ?? []);
      for (const prayer of action.prayers) {
        const local = byId.get(prayer.id);
        if (local?.source === "user") {
          byId.set(prayer.id, { ...prayer, ...local });
        } else if (local && pendingIds.has(prayer.id)) {
          byId.set(prayer.id, {
            ...prayer,
            prayedByMe: local.prayedByMe,
            prayerCount: local.prayerCount,
          });
        } else {
          byId.set(prayer.id, prayer);
        }
      }
      return { ...state, prayers: [...byId.values()] };
    }
    case "publish":
      return { ...state, prayers: [action.prayer, ...state.prayers] };
    default:
      return state;
  }
}
