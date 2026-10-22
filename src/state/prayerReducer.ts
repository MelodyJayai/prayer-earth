import { seedPrayers } from "../data";
import type { Prayer } from "../domain/types";
import type { PrayerSnapshot } from "../services/prayerStorage";

export type PrayerState = {
  prayers: Prayer[];
  hydrated: boolean;
};

export type PrayerAction =
  | { type: "hydrate"; snapshot: PrayerSnapshot }
  | { type: "syncRemote"; prayers: Prayer[]; pendingPrayerIds?: string[] }
  | { type: "toggle"; id: string }
  | { type: "publish"; prayer: Prayer };

export const initialPrayerState: PrayerState = {
  prayers: seedPrayers,
  hydrated: false,
};

export function prayerReducer(
  state: PrayerState,
  action: PrayerAction,
): PrayerState {
  switch (action.type) {
    case "hydrate": {
      const publishedIds = new Set(
        action.snapshot.publishedPrayers.map(({ id }) => id),
      );
      const prayedIds = new Set(action.snapshot.prayedIds);
      const merged = [
        ...action.snapshot.publishedPrayers,
        ...seedPrayers.filter(({ id }) => !publishedIds.has(id)),
      ].map((prayer) => {
        const prayedByMe = prayedIds.has(prayer.id);
        return {
          ...prayer,
          prayedByMe,
          prayerCount:
            prayedByMe && !prayer.prayedByMe
              ? prayer.prayerCount + 1
              : prayer.prayerCount,
        };
      });
      return { prayers: merged, hydrated: true };
    }
    case "toggle":
      return {
        ...state,
        prayers: state.prayers.map((prayer) => {
          if (prayer.id !== action.id) return prayer;
          return {
            ...prayer,
            prayedByMe: !prayer.prayedByMe,
            prayerCount: Math.max(
              0,
              prayer.prayerCount + (prayer.prayedByMe ? -1 : 1),
            ),
          };
        }),
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
