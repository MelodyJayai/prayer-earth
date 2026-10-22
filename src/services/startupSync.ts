import type { IdentitySession } from "../domain/identity";
import type { Prayer } from "../domain/types";
import type { LocalPrayer, OutboxEvent, PrayerSnapshot } from "./prayerStorage";
import { drainOutbox, type OutboxSendResult } from "./outbox";
import {
  createRemotePrayerRepository,
  type ApiPrayer,
  type PrayerListParams,
  type RemotePrayerRepository,
} from "../repositories/httpPrayerRepository";
import {
  localPrayerRepository,
  type PrayerRepository,
} from "../repositories/prayerRepository";
import { AnonymousIdentityHttpClient } from "./identityHttp";
import { HttpClient } from "./httpClient";
import { runtimeConfig } from "./runtimeConfig";

export type StartupSyncOptions = {
  localRepository?: PrayerRepository;
  identityClient?: AnonymousIdentityHttpClient;
  /** Override remote mode for tests or an explicitly selected environment. */
  remoteEnabled?: boolean;
  apiBaseUrl?: string;
  apiTimeoutMs?: number;
  deviceInstallId?: string;
  listParams?: PrayerListParams;
  /** Dependency injection hook that keeps startup orchestration testable. */
  createRemoteRepository?: (client: HttpClient, cache: PrayerRepository) => StartupRemoteRepository;
};

export type StartupRemoteRepository = Pick<RemotePrayerRepository, "listPrayers" | "sendOutboxEvent">;

export type StartupSyncResult = {
  snapshot: PrayerSnapshot;
  identitySession: IdentitySession | null;
  remoteRepository: StartupRemoteRepository | null;
  remoteEnabled: boolean;
  remotePrayers: Prayer[];
  /** A non-null error means local startup succeeded but one online step failed. */
  remoteError?: unknown;
};

const flagForCountry = (countryCode?: string): string => {
  const code = countryCode?.trim().toUpperCase();
  if (!code || !/^[A-Z]{2}$/.test(code)) return "🌏";
  return String.fromCodePoint(...[...code].map((letter) => 127397 + letter.charCodeAt(0)));
};

/** Converts the wire model to the small UI/cache model used by the reducer. */
export function mapApiPrayerToLocal(prayer: ApiPrayer): LocalPrayer {
  return {
    id: prayer.id,
    title: prayer.title,
    excerpt: prayer.excerpt,
    location: prayer.location?.displayName ?? "全球",
    flag: flagForCountry(prayer.location?.countryCode),
    category: prayer.category,
    prayerCount: Math.max(0, prayer.prayerCount),
    createdAt: prayer.createdAt,
    urgent: prayer.urgent,
    prayedByMe: prayer.prayedByMe,
    source: prayer.source,
    status: prayer.status,
    moderationState: prayer.moderationState,
    version: prayer.version,
  };
}

function mergeRemoteSnapshot(snapshot: PrayerSnapshot, remote: ApiPrayer[]): PrayerSnapshot {
  const remotePrayers = remote
    .filter((item) => item.status !== "deleted" && item.status !== "rejected" && item.status !== "hidden")
    .map(mapApiPrayerToLocal);
  const byId = new Map<string, LocalPrayer>();
  for (const prayer of snapshot.publishedPrayers) byId.set(prayer.id, prayer);
  for (const prayer of remotePrayers) {
    const local = byId.get(prayer.id);
    // Keep an optimistic local edit while its outbox event is pending.
    const hasPending = snapshot.outboxEvents.some((event) => event.aggregateId === prayer.id && event.status !== "succeeded" && event.status !== "dead");
    if (!local || !hasPending) byId.set(prayer.id, prayer);
  }
  const prayedIds = new Set(snapshot.prayedIds);
  for (const prayer of remotePrayers) {
    const pendingAction = snapshot.outboxEvents.some((event) =>
      event.aggregateId === prayer.id &&
      event.aggregateType === "prayer_action" &&
      event.status !== "succeeded" && event.status !== "dead",
    );
    if (prayer.prayedByMe) prayedIds.add(prayer.id);
    else if (!pendingAction) prayedIds.delete(prayer.id);
  }
  return { ...snapshot, publishedPrayers: [...byId.values()].slice(0, 100), prayedIds: [...prayedIds] };
}

/**
 * Performs the online portion of app startup while retaining offline behavior:
 * restore local cache, establish anonymous identity, fetch the first page, then
 * drain due outbox events. Any online failure is returned to the caller and the
 * last good local snapshot is still persisted.
 */
export async function runStartupSync(options: StartupSyncOptions = {}): Promise<StartupSyncResult> {
  const local = options.localRepository ?? localPrayerRepository;
  let snapshot: PrayerSnapshot;
  try {
    snapshot = await local.loadSnapshot();
  } catch {
    // Keep startup usable if the platform storage is temporarily unavailable.
    snapshot = { prayedIds: [], publishedPrayers: [], outboxEvents: [] };
  }
  const baseUrl = (options.apiBaseUrl ?? runtimeConfig.apiBaseUrl).replace(/\/$/, "");
  const enabled = options.remoteEnabled ?? (runtimeConfig.enableRemoteContent && Boolean(baseUrl));
  if (!enabled || !baseUrl) return { snapshot, identitySession: null, remoteRepository: null, remoteEnabled: false, remotePrayers: [] };

  const identity = options.identityClient ?? new AnonymousIdentityHttpClient({ baseUrl, timeoutMs: options.apiTimeoutMs });
  let session: IdentitySession;
  try {
    session = await identity.getOrCreateAnonymous(options.deviceInstallId);
  } catch (error) {
    return { snapshot, identitySession: null, remoteRepository: null, remoteEnabled: true, remotePrayers: [], remoteError: error };
  }
  const client = new HttpClient({
    baseUrl,
    timeoutMs: options.apiTimeoutMs ?? runtimeConfig.apiTimeoutMs,
    accessToken: () => identity.tokenManager.getAccessTokenOrUndefined(),
  });
  const createRemote = options.createRemoteRepository ?? ((http, cache) => createRemotePrayerRepository({ client: http, cache }));
  const remote = createRemote(client, local);
  let merged = snapshot;
  let remotePrayers: Prayer[] = [];
  let remoteError: unknown;
  try {
    const page = await remote.listPrayers({ limit: 50, ...(options.listParams ?? {}) });
    remotePrayers = page.data
      .filter((item) => item.status !== "deleted" && item.status !== "rejected" && item.status !== "hidden")
      .map((item) => {
        const mapped = mapApiPrayerToLocal(item);
        const pending = snapshot.outboxEvents
          .filter((event) => event.aggregateType === "prayer_action" && event.aggregateId === item.id && event.status !== "succeeded" && event.status !== "dead")
          .sort((a, b) => Date.parse(a.createdAt) - Date.parse(b.createdAt))
          .at(-1);
        const desired = pending?.payload.prayed;
        if (typeof desired !== "boolean" || desired === mapped.prayedByMe) return mapped;
        return {
          ...mapped,
          prayedByMe: desired,
          prayerCount: Math.max(0, mapped.prayerCount + (desired ? 1 : -1)),
        };
      });
    merged = mergeRemoteSnapshot(merged, page.data);
    await local.saveSnapshot(merged);
  } catch (error) {
    remoteError = error;
  }
  try {
    merged = await drainOutbox(merged, (event: OutboxEvent): Promise<OutboxSendResult> => remote.sendOutboxEvent(event));
    await local.saveSnapshot(merged);
  } catch (error) {
    remoteError ??= error;
  }
  return { snapshot: merged, identitySession: session, remoteRepository: remote, remoteEnabled: true, remotePrayers, ...(remoteError ? { remoteError } : {}) };
}
