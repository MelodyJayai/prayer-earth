import { describe, expect, it } from "vitest";
import type { Prayer } from "../domain/types";
import {
  initialPrayerState,
  persistedPrayedIds,
  persistedPublishedPrayers,
  prayerReducer,
} from "./prayerReducer";

const userPrayer: Prayer = {
  id: "user-1",
  title: "为家人祷告",
  excerpt: "愿家人平安。",
  location: "来自你的祷告",
  flag: "🌏",
  category: "家庭",
  prayerCount: 1,
  createdAt: "2026-08-24T00:00:00.000Z",
  urgent: false,
  prayedByMe: false,
  source: "user",
};

const seedPrayer: Prayer = {
  ...userPrayer,
  id: "seed-sudan-peace",
  title: "种子",
  source: "seed",
  prayerCount: 12847,
};

describe("prayerReducer", () => {
  it("starts without the bundled seed prayers", () => {
    expect(initialPrayerState.prayers).toEqual([]);
  });

  it("hydrates user prayers, hides stored seeds, and keeps their prayed ids", () => {
    const next = prayerReducer(initialPrayerState, {
      type: "hydrate",
      snapshot: {
        prayedIds: [seedPrayer.id, userPrayer.id],
        publishedPrayers: [userPrayer, seedPrayer],
        outboxEvents: [],
      },
    });
    expect(next.prayers.map((prayer) => prayer.id)).toEqual([userPrayer.id]);
    expect(next.prayers[0].prayedByMe).toBe(true);
    expect(next.prayers[0].prayerCount).toBe(1);
    expect(next.retainedPrayers.map((prayer) => prayer.id)).toEqual([seedPrayer.id]);
    expect(persistedPublishedPrayers(next).map((prayer) => prayer.id)).toEqual([userPrayer.id, seedPrayer.id]);
    expect(persistedPrayedIds(next)).toEqual([seedPrayer.id, userPrayer.id]);
  });

  it("toggles a local flag without changing the stored count", () => {
    const hydrated = prayerReducer(initialPrayerState, {
      type: "hydrate",
      snapshot: { prayedIds: [], publishedPrayers: [userPrayer], outboxEvents: [] },
    });
    const prayed = prayerReducer(hydrated, { type: "toggle", id: userPrayer.id });
    const undone = prayerReducer(prayed, { type: "toggle", id: userPrayer.id });
    expect(prayed.prayers[0].prayedByMe).toBe(true);
    expect(prayed.prayers[0].prayerCount).toBe(1);
    expect(persistedPrayedIds(undone)).toEqual([]);
  });

  it("prepends a newly published prayer", () => {
    const next = prayerReducer(initialPrayerState, { type: "publish", prayer: userPrayer });
    expect(next.prayers).toEqual([userPrayer]);
  });

  it("replaces routed news without dropping local prayers or prayed flags", () => {
    const hydrated = prayerReducer(initialPrayerState, {
      type: "hydrate",
      snapshot: { prayedIds: ["news-20261027-0123456789ab"], publishedPrayers: [userPrayer], outboxEvents: [] },
    });
    const news: Prayer = {
      ...userPrayer,
      id: "news-20261027-0123456789ab",
      title: "信徒遭监禁",
      source: "news",
      category: "代祷",
      verified: false,
      sourceUrl: "https://example.com/church",
      prayerCount: 99,
    };
    const next = prayerReducer(hydrated, { type: "replaceNews", prayers: [news] });
    expect(next.feedStatus).toBe("ready");
    expect(next.prayers.map((prayer) => prayer.id)).toEqual([news.id, userPrayer.id]);
    expect(next.prayers[0].prayedByMe).toBe(true);
    expect(next.prayers[0].prayerCount).toBe(0);
    expect(next.prayers[0].source).toBe("news");
    const failed = prayerReducer(next, { type: "feedFailed" });
    expect(failed.feedStatus).toBe("ready");
    expect(prayerReducer(initialPrayerState, { type: "feedFailed" }).feedStatus).toBe("error");
  });

  it("merges remote prayers without losing local user content", () => {
    const local = prayerReducer(initialPrayerState, { type: "publish", prayer: userPrayer });
    const remote: Prayer = { ...userPrayer, id: "remote-1", title: "来自云端", source: "seed" };
    const next = prayerReducer(local, { type: "syncRemote", prayers: [remote] });
    expect(next.prayers.find(({ id }) => id === "remote-1")?.title).toBe("来自云端");
    expect(next.prayers.find(({ id }) => id === "user-1")).toBeDefined();
  });

  it("keeps an optimistic prayer action while its outbox event is pending", () => {
    const hydrated = prayerReducer(initialPrayerState, {
      type: "hydrate",
      snapshot: { prayedIds: [], publishedPrayers: [userPrayer], outboxEvents: [] },
    });
    const prayed = prayerReducer(hydrated, { type: "toggle", id: userPrayer.id });
    const remote = { ...userPrayer, prayedByMe: false };
    const next = prayerReducer(prayed, {
      type: "syncRemote",
      prayers: [remote],
      pendingPrayerIds: [userPrayer.id],
    });
    expect(next.prayers[0].prayedByMe).toBe(true);
    expect(next.prayers[0].prayerCount).toBe(userPrayer.prayerCount);
  });
});
