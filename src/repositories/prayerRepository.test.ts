import { describe, expect, it } from "vitest";
import {
  createLocalPrayerRepository,
  type PrayerRepository,
  type PrayerStorageAdapter,
} from "./prayerRepository";
import { createOutboxEvent } from "../services/prayerStorage";

function memoryStorage(): PrayerStorageAdapter & { value: string | null } {
  return {
    value: null,
    async getItem() {
      return this.value;
    },
    async setItem(_key, value) {
      this.value = value;
    },
  };
}

describe("LocalPrayerRepository", () => {
  it("persists and restores a snapshot through the storage boundary", async () => {
    const storage = memoryStorage();
    const repository = createLocalPrayerRepository(storage);
    const snapshot = { prayedIds: ["seed-1"], publishedPrayers: [], outboxEvents: [] };

    await repository.saveSnapshot(snapshot);

    await expect(repository.loadSnapshot()).resolves.toEqual(snapshot);
    expect(storage.value).toContain('"version":3');
  });

  it("returns an empty snapshot when persisted data is malformed", async () => {
    const storage = memoryStorage();
    storage.value = "{bad json";

    await expect(
      createLocalPrayerRepository(storage).loadSnapshot(),
    ).resolves.toEqual({ prayedIds: [], publishedPrayers: [], outboxEvents: [] });
  });

  it("deduplicates outbox events by idempotency key", async () => {
    const repository: PrayerRepository = createLocalPrayerRepository(memoryStorage());
    const event = createOutboxEvent({
      aggregateType: "prayer",
      eventType: "prayer.create",
      payload: {},
      idempotencyKey: "same-request",
      now: "2026-09-05T00:00:00.000Z",
    });
    await repository.enqueueOutboxEvent(event);
    await repository.enqueueOutboxEvent({ ...event, id: "retry-with-new-local-id" });
    await expect(repository.loadSnapshot()).resolves.toMatchObject({
      outboxEvents: [
        expect.objectContaining({
          idempotencyKey: "same-request",
          eventType: "prayer.create",
          status: "pending",
        }),
      ],
    });
  });
});
