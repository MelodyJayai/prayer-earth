import {
  parsePrayerSnapshot,
  loadPrayerSnapshot,
  savePrayerSnapshot,
  enqueueOutboxEvent,
  STORAGE_KEY,
  STORAGE_SCHEMA_VERSION,
  type PrayerSnapshot,
  type OutboxEvent,
} from "../services/prayerStorage";

/**
 * Persistence boundary consumed by the state layer.
 *
 * A future HTTP backed implementation can satisfy this interface without
 * leaking a vendor SDK into hooks or screens. The snapshot shape intentionally
 * carries the v3 local cache and outbox contract while the online adapter is
 * introduced incrementally.
 */
export interface PrayerRepository {
  loadSnapshot(): Promise<PrayerSnapshot>;
  saveSnapshot(snapshot: PrayerSnapshot): Promise<void>;
  enqueueOutboxEvent(event: OutboxEvent): Promise<void>;
}

export interface PrayerStorageAdapter {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
}

/** AsyncStorage implementation used by the offline first client. */
export class LocalPrayerRepository implements PrayerRepository {
  constructor(private readonly storage?: PrayerStorageAdapter) {}

  async loadSnapshot(): Promise<PrayerSnapshot> {
    // Use the service entry point for the default adapter so schema migration
    // (v2 → v3) and backup behavior remain centralized.
    if (!this.storage) return loadPrayerSnapshot();
    return parsePrayerSnapshot(await this.storage.getItem(STORAGE_KEY));
  }

  async saveSnapshot(snapshot: PrayerSnapshot): Promise<void> {
    if (!this.storage) {
      await savePrayerSnapshot(snapshot);
      return;
    }
    await this.storage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        version: STORAGE_SCHEMA_VERSION,
        ...snapshot,
        outboxEvents: snapshot.outboxEvents ?? [],
      }),
    );
  }

  async enqueueOutboxEvent(event: OutboxEvent): Promise<void> {
    if (!this.storage) {
      await enqueueOutboxEvent(event);
      return;
    }
    const snapshot = await this.loadSnapshot();
    if (snapshot.outboxEvents.some(({ idempotencyKey }) => idempotencyKey === event.idempotencyKey)) return;
    await this.saveSnapshot({
      ...snapshot,
      outboxEvents: [...snapshot.outboxEvents, event],
    });
  }
}

/** Factory exported for tests and for dependency injection at app startup. */
export function createLocalPrayerRepository(
  storage?: PrayerStorageAdapter,
): PrayerRepository {
  return new LocalPrayerRepository(storage);
}

/** Shared default instance used by the current hook. */
export const localPrayerRepository: PrayerRepository =
  new LocalPrayerRepository();
