import AsyncStorage from "@react-native-async-storage/async-storage";
import { PRAYER_CATEGORIES, type Prayer } from "../domain/types";

export const STORAGE_KEY = "prayer-earth:state:v3";
export const LEGACY_STORAGE_KEY = "prayer-earth:state:v2";
export const LEGACY_BACKUP_KEY = `${LEGACY_STORAGE_KEY}:backup`;
export const STORAGE_SCHEMA_VERSION = 3;

export type OutboxAggregateType = "prayer" | "testimony" | "prayer_action" | "report" | "identity";
export type OutboxEventType = "prayer.create" | "prayer.pray" | "prayer.unpray" | "prayer.delete" | "testimony.create" | "report.create" | "identity.upgrade";
export type OutboxStatus = "pending" | "in_flight" | "succeeded" | "failed" | "dead";
export type OutboxEvent = {
  id: string; aggregateType: OutboxAggregateType; aggregateId?: string; eventType: OutboxEventType;
  payload: Record<string, unknown>; idempotencyKey: string; status: OutboxStatus; attempts: number;
  nextAttemptAt?: string; lastErrorCode?: string; createdAt: string; updatedAt: string;
};
export type LocalPrayer = Prayer & {
  status?: "pending" | "published" | "rejected" | "hidden" | "deleted";
  moderationState?: "not_required" | "queued" | "approved" | "rejected" | "hidden";
  version?: number;
};
export type PrayerSnapshot = { prayedIds: string[]; publishedPrayers: LocalPrayer[]; outboxEvents: OutboxEvent[] };
const emptySnapshot = (): PrayerSnapshot => ({ prayedIds: [], publishedPrayers: [], outboxEvents: [] });

function isPrayer(value: unknown): value is LocalPrayer {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<Prayer>;
  return typeof item.id === "string" && typeof item.title === "string" && item.title.length > 0 && item.title.length <= 60 &&
    typeof item.excerpt === "string" && item.excerpt.length > 0 && item.excerpt.length <= 500 && typeof item.location === "string" &&
    typeof item.flag === "string" && typeof item.category === "string" && PRAYER_CATEGORIES.some((category) => category === item.category) &&
    typeof item.prayerCount === "number" && Number.isFinite(item.prayerCount) && item.prayerCount >= 0 && typeof item.createdAt === "string" &&
    Number.isFinite(Date.parse(item.createdAt)) && typeof item.urgent === "boolean" && typeof item.prayedByMe === "boolean" && (item.source === "user" || item.source === "seed");
}
function isOutboxEvent(value: unknown): value is OutboxEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Partial<OutboxEvent>;
  return typeof event.id === "string" && typeof event.idempotencyKey === "string" &&
    ["prayer", "testimony", "prayer_action", "report", "identity"].includes(event.aggregateType as string) &&
    ["prayer.create", "prayer.pray", "prayer.unpray", "prayer.delete", "testimony.create", "report.create", "identity.upgrade"].includes(event.eventType as string) &&
    typeof event.status === "string" && ["pending", "in_flight", "succeeded", "failed", "dead"].includes(event.status) &&
    typeof event.attempts === "number" && Number.isInteger(event.attempts) && event.attempts >= 0 && !!event.payload && typeof event.payload === "object" &&
    typeof event.createdAt === "string" && typeof event.updatedAt === "string";
}
export function parsePrayerSnapshot(raw: string | null): PrayerSnapshot {
  if (!raw) return emptySnapshot();
  try {
    const data = JSON.parse(raw) as Record<string, unknown>;
    if (data.version !== STORAGE_SCHEMA_VERSION) return emptySnapshot();
    const prayedIds = Array.isArray(data.prayedIds) ? [...new Set(data.prayedIds.filter((id): id is string => typeof id === "string"))] : [];
    const publishedPrayers = Array.isArray(data.publishedPrayers) ? data.publishedPrayers.filter(isPrayer).slice(0, 100) : [];
    const outboxEvents = Array.isArray(data.outboxEvents) ? data.outboxEvents.filter(isOutboxEvent).slice(0, 200) : [];
    return { prayedIds, publishedPrayers, outboxEvents };
  } catch { return emptySnapshot(); }
}
const uuid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
export const prayerActionIdempotencyKey = (prayerId: string, prayed: boolean) => `prayer-action:${prayerId}:${prayed ? "pray" : "unpray"}`;
export function createOutboxEvent(input: { aggregateType: OutboxAggregateType; aggregateId?: string; eventType: OutboxEventType; payload: Record<string, unknown>; idempotencyKey?: string; now?: string }): OutboxEvent {
  const now = input.now ?? new Date().toISOString();
  return { id: uuid(), aggregateType: input.aggregateType, aggregateId: input.aggregateId, eventType: input.eventType, payload: input.payload, idempotencyKey: input.idempotencyKey ?? uuid(), status: "pending", attempts: 0, createdAt: now, updatedAt: now };
}
export const retryDelaySeconds = (attempts: number) => [1, 5, 30, 300, 1800][Math.max(0, Math.min(attempts - 1, 4))] ?? 1800;
export function markOutboxFailed(event: OutboxEvent, errorCode: string, retryable: boolean, now = new Date()): OutboxEvent {
  const attempts = event.attempts + 1; const terminal = !retryable || attempts >= 8; const updatedAt = now.toISOString();
  return { ...event, attempts, status: terminal ? "dead" : "failed", lastErrorCode: errorCode, nextAttemptAt: terminal ? undefined : new Date(now.getTime() + retryDelaySeconds(attempts) * 1000).toISOString(), updatedAt };
}
export function markOutboxSucceeded(event: OutboxEvent, now = new Date()): OutboxEvent {
  return { ...event, status: "succeeded", nextAttemptAt: undefined, lastErrorCode: undefined, updatedAt: now.toISOString() };
}
export function migrateV2(raw: string): PrayerSnapshot {
  const data = JSON.parse(raw) as { version?: unknown; prayedIds?: unknown; publishedPrayers?: unknown };
  if (data.version !== 2) throw new Error("unsupported legacy schema");
  const prayedIds = Array.isArray(data.prayedIds) ? [...new Set(data.prayedIds.filter((id): id is string => typeof id === "string"))] : [];
  const publishedPrayers = Array.isArray(data.publishedPrayers) ? data.publishedPrayers.filter(isPrayer).slice(0, 100).map((prayer) => ({ ...prayer, status: "pending" as const, moderationState: "queued" as const, version: 1 })) : [];
  const outboxEvents = prayedIds.map((id) => createOutboxEvent({ aggregateType: "prayer_action", aggregateId: id, eventType: "prayer.pray", payload: { prayed: true, prayerId: id }, idempotencyKey: prayerActionIdempotencyKey(id, true) }));
  return { prayedIds, publishedPrayers, outboxEvents };
}
export async function loadPrayerSnapshot(): Promise<PrayerSnapshot> {
  const current = await AsyncStorage.getItem(STORAGE_KEY); if (current) return parsePrayerSnapshot(current);
  const legacy = await AsyncStorage.getItem(LEGACY_STORAGE_KEY); if (!legacy) return emptySnapshot();
  try { const migrated = migrateV2(legacy); await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify({ version: STORAGE_SCHEMA_VERSION, ...migrated })); return migrated; }
  catch { try { await AsyncStorage.setItem(LEGACY_BACKUP_KEY, legacy); } catch { /* ignore */ } return emptySnapshot(); }
}
export async function savePrayerSnapshot(snapshot: PrayerSnapshot): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify({ version: STORAGE_SCHEMA_VERSION, ...snapshot, outboxEvents: snapshot.outboxEvents ?? [] }));
}
export async function enqueueOutboxEvent(event: OutboxEvent): Promise<void> {
  const snapshot = await loadPrayerSnapshot(); if ((snapshot.outboxEvents ?? []).some((item) => item.idempotencyKey === event.idempotencyKey)) return;
  await savePrayerSnapshot({ ...snapshot, outboxEvents: [...(snapshot.outboxEvents ?? []), event] });
}
