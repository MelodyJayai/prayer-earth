import { describe, expect, it } from "vitest";
import type { Prayer } from "../domain/types";
import { initialPrayerState, prayerReducer } from "./prayerReducer";

describe("prayerReducer", () => {
  it("hydrates prayed state without mutating seed data", () => {
    const target = initialPrayerState.prayers[0];
    const next = prayerReducer(initialPrayerState, {
      type: "hydrate",
      snapshot: { prayedIds: [target.id], publishedPrayers: [], outboxEvents: [] },
    });
    expect(next.hydrated).toBe(true);
    expect(next.prayers[0].prayedByMe).toBe(true);
    expect(next.prayers[0].prayerCount).toBe(target.prayerCount + 1);
    expect(initialPrayerState.prayers[0].prayedByMe).toBe(false);
  });

  it("toggles only the selected prayer and keeps count consistent", () => {
    const target = initialPrayerState.prayers[0];
    const prayed = prayerReducer(initialPrayerState, {
      type: "toggle",
      id: target.id,
    });
    const undone = prayerReducer(prayed, { type: "toggle", id: target.id });
    expect(prayed.prayers[0].prayedByMe).toBe(true);
    expect(prayed.prayers[0].prayerCount).toBe(target.prayerCount + 1);
    expect(prayed.prayers[1]).toBe(initialPrayerState.prayers[1]);
    expect(undone.prayers[0].prayerCount).toBe(target.prayerCount);
  });

  it("prepends a newly published prayer", () => {
    const prayer: Prayer = {
      ...initialPrayerState.prayers[0],
      id: "user-test",
      source: "user",
    };
    const next = prayerReducer(initialPrayerState, { type: "publish", prayer });
    expect(next.prayers[0]).toBe(prayer);
    expect(next.prayers).toHaveLength(initialPrayerState.prayers.length + 1);
  });

  it("merges remote prayers without losing local user content", () => {
    const local = prayerReducer(initialPrayerState, {
      type: "publish",
      prayer: { ...initialPrayerState.prayers[0], id: "user-local", source: "user" },
    });
    const remote = { ...initialPrayerState.prayers[0], id: "remote-1", title: "来自云端", source: "seed" as const };
    const next = prayerReducer(local, { type: "syncRemote", prayers: [remote] });
    expect(next.prayers.find(({ id }) => id === "remote-1")?.title).toBe("来自云端");
    expect(next.prayers.find(({ id }) => id === "user-local")).toBeDefined();
  });

  it("keeps an optimistic prayer action while its outbox event is pending", () => {
    const target = initialPrayerState.prayers[0];
    const prayed = prayerReducer(initialPrayerState, { type: "toggle", id: target.id });
    const remote = { ...target, prayedByMe: false, prayerCount: target.prayerCount };
    const next = prayerReducer(prayed, {
      type: "syncRemote",
      prayers: [remote],
      pendingPrayerIds: [target.id],
    });
    expect(next.prayers[0].prayedByMe).toBe(true);
    expect(next.prayers[0].prayerCount).toBe(target.prayerCount + 1);
  });
});
