import { beforeEach, describe, expect, it, vi } from "vitest";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  createOutboxEvent,
  loadPrayerSnapshot,
  markOutboxFailed,
  parsePrayerSnapshot,
  STORAGE_SCHEMA_VERSION,
} from "./prayerStorage";

vi.mock("@react-native-async-storage/async-storage", () => ({
  default: { getItem: vi.fn(), setItem: vi.fn() },
}));

describe("parsePrayerSnapshot", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns an empty snapshot for corrupt or old data", () => {
    expect(parsePrayerSnapshot("not-json")).toEqual({
      prayedIds: [],
      publishedPrayers: [],
      outboxEvents: [],
    });
    expect(parsePrayerSnapshot(JSON.stringify({ version: 1 }))).toEqual({
      prayedIds: [],
      publishedPrayers: [],
      outboxEvents: [],
    });
  });

  it("deduplicates ids and rejects invalid published records", () => {
    const result = parsePrayerSnapshot(
      JSON.stringify({
        version: STORAGE_SCHEMA_VERSION,
        prayedIds: ["a", "a", 2],
        publishedPrayers: [{ id: "partial" }],
      }),
    );
    expect(result).toEqual({ prayedIds: ["a"], publishedPrayers: [], outboxEvents: [] });
  });

  it("accepts a valid bounded user prayer", () => {
    const prayer = {
      id: "user-1",
      title: "为家人祷告",
      excerpt: "愿家人每天都有平安与力量。",
      location: "来自你的祷告",
      flag: "🌏",
      category: "家庭",
      prayerCount: 1,
      createdAt: "2026-08-24T00:00:00.000Z",
      urgent: false,
      prayedByMe: true,
      source: "user",
    };
    const result = parsePrayerSnapshot(
      JSON.stringify({
        version: STORAGE_SCHEMA_VERSION,
        prayedIds: [prayer.id],
        publishedPrayers: [prayer],
      }),
    );
    expect(result.publishedPrayers).toHaveLength(1);
  });

  it("migrates v2 prayers and prayed ids into a v3 outbox", async () => {
    const prayer = {
      id: "user-1", title: "为家人祷告", excerpt: "愿家人每天都有平安与力量。", location: "来自你的祷告",
      flag: "🌏", category: "家庭", prayerCount: 1, createdAt: "2026-08-24T00:00:00.000Z",
      urgent: false, prayedByMe: true, source: "user",
    };
    vi.mocked(AsyncStorage.getItem).mockImplementation(async (key) =>
      key.endsWith(":v2") ? JSON.stringify({ version: 2, prayedIds: ["user-1"], publishedPrayers: [prayer] }) : null,
    );
    const migrated = await loadPrayerSnapshot();
    expect(migrated.publishedPrayers[0]).toMatchObject({ status: "pending", moderationState: "queued", version: 1 });
    expect(migrated.outboxEvents).toHaveLength(1);
    expect(migrated.outboxEvents?.[0].eventType).toBe("prayer.pray");
    expect(AsyncStorage.setItem).toHaveBeenCalled();
  });

  it("moves non-retryable failures to dead and retries with backoff", () => {
    const event = createOutboxEvent({ aggregateType: "prayer", eventType: "prayer.create", payload: {}, now: "2026-09-05T00:00:00.000Z" });
    const retry = markOutboxFailed(event, "NETWORK_ERROR", true, new Date("2026-09-05T00:00:00.000Z"));
    expect(retry.status).toBe("failed");
    expect(retry.nextAttemptAt).toBe("2026-09-05T00:00:01.000Z");
    expect(markOutboxFailed(event, "VALIDATION_ERROR", false).status).toBe("dead");
  });

  it("backs up an unsupported legacy envelope instead of discarding it", async () => {
    vi.mocked(AsyncStorage.getItem).mockImplementation(async (key) =>
      key.endsWith(":v2") ? JSON.stringify({ version: 1, stale: true }) : null,
    );
    const snapshot = await loadPrayerSnapshot();
    expect(snapshot).toEqual({ prayedIds: [], publishedPrayers: [], outboxEvents: [] });
    expect(AsyncStorage.setItem).toHaveBeenCalledWith(
      "prayer-earth:state:v2:backup",
      JSON.stringify({ version: 1, stale: true }),
    );
  });
});
