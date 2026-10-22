import { describe, expect, it, vi } from "vitest";
import type { IdentitySession } from "../domain/identity";
import type { ApiPrayer, RemotePrayerRepository } from "../repositories/httpPrayerRepository";
import type { PrayerRepository } from "../repositories/prayerRepository";
import { createOutboxEvent, type PrayerSnapshot } from "./prayerStorage";
import { runStartupSync } from "./startupSync";

const session: IdentitySession = {
  identity: { id: "anon-1", kind: "anonymous", authProviders: ["anonymous"], status: "active", createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z" },
  accessToken: "token",
};
const prayer: ApiPrayer = {
  id: "remote-1", title: "Remote", excerpt: "From API", category: "和平", urgent: true,
  location: { countryCode: "US", displayName: "纽约，美国" }, locale: "zh-CN", source: "seed",
  status: "published", moderationState: "approved", prayerCount: 4, prayedByMe: true,
  canEdit: false, canDelete: false, createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z", version: 2,
};
const snapshot = (): PrayerSnapshot => ({ prayedIds: [], publishedPrayers: [], outboxEvents: [createOutboxEvent({ aggregateType: "prayer_action", aggregateId: "local-1", eventType: "prayer.pray", payload: { prayed: true }, now: "2026-01-01T00:00:00Z" })] });

function memoryRepository(initial: PrayerSnapshot): PrayerRepository & { current: PrayerSnapshot } {
  const value = { current: initial };
  return {
    get current() { return value.current; },
    set current(next) { value.current = next; },
    loadSnapshot: async () => value.current,
    saveSnapshot: async (next) => { value.current = next; },
    enqueueOutboxEvent: async () => undefined,
  };
}

describe("runStartupSync", () => {
  it("restores identity, merges first page and drains outbox", async () => {
    const local = memoryRepository(snapshot());
    const sendOutboxEvent = vi.fn(async () => ({ ok: true as const }));
    const remote = { listPrayers: vi.fn(async () => ({ data: [prayer], page: { limit: 50, nextCursor: null } })), sendOutboxEvent } as unknown as RemotePrayerRepository;
    const identity = { getOrCreateAnonymous: vi.fn(async () => session), tokenManager: { getAccessTokenOrUndefined: async () => "token" } } as never;
    const result = await runStartupSync({ localRepository: local, identityClient: identity, remoteEnabled: true, apiBaseUrl: "https://api.test", createRemoteRepository: () => remote });
    expect(result.identitySession).toEqual(session);
    expect(remote.listPrayers).toHaveBeenCalled();
    expect(sendOutboxEvent).toHaveBeenCalledTimes(1);
    expect(result.snapshot.publishedPrayers[0]).toMatchObject({ id: "remote-1", flag: "🇺🇸", source: "seed" });
    expect(result.snapshot.prayedIds).toContain("remote-1");
    expect(result.snapshot.outboxEvents[0].status).toBe("succeeded");
  });

  it("keeps local snapshot when identity service is unavailable", async () => {
    const local = memoryRepository(snapshot());
    const identity = { getOrCreateAnonymous: vi.fn(async () => { throw new Error("offline"); }), tokenManager: {} } as never;
    const result = await runStartupSync({ localRepository: local, identityClient: identity, remoteEnabled: true, apiBaseUrl: "https://api.test" });
    expect(result.remoteRepository).toBeNull();
    expect(result.snapshot.outboxEvents[0].status).toBe("pending");
    expect(result.remoteError).toBeInstanceOf(Error);
  });
});

