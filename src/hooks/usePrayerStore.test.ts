import { describe, expect, it } from "vitest";
import type { PrayerRepository } from "../repositories/prayerRepository";
import type { PrayerSnapshot } from "../services/prayerStorage";
import { loadSnapshotWithinTimeout } from "./usePrayerStore";

const emptySnapshot: PrayerSnapshot = {
  prayedIds: [],
  publishedPrayers: [],
  outboxEvents: [],
};

const repository = (loadSnapshot: PrayerRepository["loadSnapshot"]): PrayerRepository => ({
  loadSnapshot,
  saveSnapshot: async () => undefined,
  enqueueOutboxEvent: async () => undefined,
});

describe("loadSnapshotWithinTimeout", () => {
  it("returns an empty fallback when storage never resolves", async () => {
    const result = await loadSnapshotWithinTimeout(
      repository(() => new Promise<PrayerSnapshot>(() => undefined)),
      5,
    );

    expect(result).toEqual({ snapshot: emptySnapshot, timedOut: true });
  });

  it("keeps storage errors bounded and reports them to the caller", async () => {
    const error = new Error("storage unavailable");
    const result = await loadSnapshotWithinTimeout(
      repository(async () => {
        throw error;
      }),
      100,
    );

    expect(result.snapshot).toEqual(emptySnapshot);
    expect(result.timedOut).toBe(false);
    expect(result.error).toBe(error);
  });

  it("handles storage adapters that throw before returning a promise", async () => {
    const error = new Error("storage permission denied");
    const result = await loadSnapshotWithinTimeout(
      repository(() => {
        throw error;
      }),
      100,
    );

    expect(result.snapshot).toEqual(emptySnapshot);
    expect(result.timedOut).toBe(false);
    expect(result.error).toBe(error);
  });

  it("returns the cache when storage responds before the deadline", async () => {
    const snapshot: PrayerSnapshot = {
      prayedIds: ["prayer-1"],
      publishedPrayers: [],
      outboxEvents: [],
    };
    const result = await loadSnapshotWithinTimeout(
      repository(async () => snapshot),
      100,
    );

    expect(result).toEqual({ snapshot, timedOut: false });
  });
});
