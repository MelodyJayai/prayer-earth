import type { PrayerCategory } from "../domain/types";
import type { OutboxEvent, PrayerSnapshot } from "../services/prayerStorage";
import { HttpClient } from "../services/httpClient";
import type { OutboxSendResult } from "../services/outbox";
import {
  localPrayerRepository,
  type PrayerRepository,
} from "./prayerRepository";

export type ApiPrayerLocation = {
  countryCode?: string;
  admin1?: string;
  city?: string;
  displayName: string;
};

/** API representation from docs/API_CONTRACT.md (kept separate from UI fixture type). */
export type ApiPrayer = {
  id: string;
  title: string;
  excerpt: string;
  body?: string;
  category: PrayerCategory;
  urgent: boolean;
  location?: ApiPrayerLocation;
  locale: string;
  authorIdentityId?: string;
  publicAuthor?: { displayName?: string; avatarUrl?: string };
  source: "seed" | "user";
  status: "pending" | "published" | "rejected" | "hidden" | "deleted";
  moderationState: "not_required" | "queued" | "approved" | "rejected" | "hidden";
  prayerCount: number;
  prayedByMe: boolean;
  canEdit: boolean;
  canDelete: boolean;
  createdAt: string;
  updatedAt: string;
  publishedAt?: string;
  deletedAt?: string;
  version: number;
};

export type CursorPage<T> = { data: T[]; page: { limit: number; nextCursor: string | null } };
export type PrayerListParams = {
  cursor?: string;
  limit?: number;
  category?: PrayerCategory;
  urgent?: boolean;
  locale?: string;
  country?: string;
};
export type CreatePrayerInput = {
  title: string;
  excerpt: string;
  body?: string;
  category: PrayerCategory;
  urgent?: boolean;
  location?: ApiPrayerLocation;
  locale?: string;
  clientCreatedAt?: string;
};
export type ReportInput = {
  targetType: "prayer" | "testimony" | "identity";
  targetId: string;
  reason: "spam" | "harassment" | "self_harm" | "violence" | "privacy" | "copyright" | "misinformation" | "other";
  details?: string;
};
export type ApiReport = ReportInput & {
  id: string;
  reporterIdentityId: string;
  status: "open" | "triaged" | "actioned" | "dismissed" | "duplicate";
  priority: "low" | "normal" | "high" | "critical";
  createdAt: string;
  updatedAt: string;
  resolvedAt?: string;
};
export type OutboxBatchResult = {
  idempotencyKey: string;
  status: "accepted" | "succeeded" | "failed";
  resource?: unknown;
  error?: { code: string; message?: string; retryable?: boolean };
};

export type RemotePrayerRepositoryOptions = {
  client: HttpClient;
  /** Local cache remains the persistence boundary used by usePrayerStore. */
  cache?: PrayerRepository;
};

function unwrapData<T>(value: T | { data?: T }): T {
  if (value && typeof value === "object" && "data" in (value as object)) {
    const data = (value as { data?: T }).data;
    if (data !== undefined) return data;
  }
  return value as T;
}

/** HTTP adapter for the provider-neutral API contract. */
export class RemotePrayerRepository implements PrayerRepository {
  private readonly client: HttpClient;
  private readonly cache: PrayerRepository;

  constructor(options: RemotePrayerRepositoryOptions) {
    this.client = options.client;
    this.cache = options.cache ?? localPrayerRepository;
  }

  loadSnapshot(): Promise<PrayerSnapshot> { return this.cache.loadSnapshot(); }
  saveSnapshot(snapshot: PrayerSnapshot): Promise<void> { return this.cache.saveSnapshot(snapshot); }
  enqueueOutboxEvent(event: OutboxEvent): Promise<void> { return this.cache.enqueueOutboxEvent(event); }

  listPrayers(params: PrayerListParams = {}): Promise<CursorPage<ApiPrayer>> {
    const query = new URLSearchParams();
    if (params.cursor) query.set("cursor", params.cursor);
    if (params.limit !== undefined) query.set("limit", String(Math.min(50, Math.max(1, params.limit))));
    if (params.category) query.set("category", params.category);
    if (params.urgent !== undefined) query.set("urgent", String(params.urgent));
    if (params.locale) query.set("locale", params.locale);
    if (params.country) query.set("country", params.country);
    const suffix = query.toString();
    // Public reads work without a token, while including one enables the
    // server to calculate prayedByMe/canEdit for the current identity.
    return this.client.get<CursorPage<ApiPrayer>>(`/v1/prayers${suffix ? `?${suffix}` : ""}`);
  }

  getPrayer(id: string): Promise<ApiPrayer> {
    return this.client.get<ApiPrayer | { data: ApiPrayer }>(`/v1/prayers/${encodeURIComponent(id)}`).then(unwrapData);
  }

  createPrayer(input: CreatePrayerInput, idempotencyKey: string): Promise<ApiPrayer> {
    return this.client.post<ApiPrayer | { data: ApiPrayer }>("/v1/prayers", input, { idempotencyKey }).then(unwrapData);
  }

  togglePrayer(id: string, prayed: boolean, idempotencyKey: string): Promise<{ prayed: boolean; prayer?: ApiPrayer }> {
    return this.client.post<{ prayed: boolean; prayer?: ApiPrayer } | { data: { prayed: boolean; prayer?: ApiPrayer } }>(`/v1/prayers/${encodeURIComponent(id)}/prayer-action`, { prayed }, { idempotencyKey }).then(unwrapData);
  }

  deletePrayer(id: string, version: number, idempotencyKey: string): Promise<void> {
    return this.client.delete(`/v1/prayers/${encodeURIComponent(id)}`, { ifMatch: version, idempotencyKey });
  }

  report(input: ReportInput, idempotencyKey: string): Promise<ApiReport> {
    return this.client.post<ApiReport | { data: ApiReport }>("/v1/reports", input, { idempotencyKey }).then(unwrapData);
  }

  sendOutboxBatch(events: OutboxEvent[]): Promise<{ results: OutboxBatchResult[] }> {
    return this.client.post<{ results: OutboxBatchResult[] }>("/v1/outbox/batch", { events: events.slice(0, 50) });
  }

  async sendOutboxEvent(event: OutboxEvent): Promise<OutboxSendResult> {
    const result = (await this.sendOutboxBatch([event])).results[0];
    if (!result) return { ok: false, errorCode: "EMPTY_BATCH_RESPONSE", retryable: true };
    if (result.status === "succeeded" || result.status === "accepted") return { ok: true };
    return {
      ok: false,
      errorCode: result.error?.code ?? "OUTBOX_EVENT_FAILED",
      retryable: result.error?.retryable ?? false,
    };
  }
}

export function createRemotePrayerRepository(options: RemotePrayerRepositoryOptions): RemotePrayerRepository {
  return new RemotePrayerRepository(options);
}

/** Backwards-friendly name for callers that refer to the adapter as HTTP. */
export const HttpPrayerRepository = RemotePrayerRepository;
export const createHttpPrayerRepository = createRemotePrayerRepository;
