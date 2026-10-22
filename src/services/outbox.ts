import {
  markOutboxFailed,
  type OutboxEvent,
  type PrayerSnapshot,
} from "./prayerStorage";

export type OutboxSendResult =
  | { ok: true }
  | { ok: false; errorCode: string; retryable: boolean };

export type OutboxSender = (event: OutboxEvent) => Promise<OutboxSendResult>;

/**
 * Sends due events in creation order. The caller persists the returned
 * snapshot, which keeps this worker usable for both local and HTTP adapters.
 */
export async function drainOutbox(
  snapshot: PrayerSnapshot,
  send: OutboxSender,
  now = new Date(),
): Promise<PrayerSnapshot> {
  let events = snapshot.outboxEvents;
  for (const event of events) {
    if (
      (event.status !== "pending" && event.status !== "failed") ||
      (event.nextAttemptAt && Date.parse(event.nextAttemptAt) > now.getTime())
    ) {
      continue;
    }
    const index = events.findIndex(({ id }) => id === event.id);
    if (index < 0) continue;
    const inFlight = { ...event, status: "in_flight" as const, updatedAt: now.toISOString() };
    events = events.map((item, itemIndex) => (itemIndex === index ? inFlight : item));
    try {
      const result = await send(inFlight);
      events = events.map((item, itemIndex) =>
        itemIndex === index
          ? result.ok
            ? { ...item, status: "succeeded" as const, nextAttemptAt: undefined, updatedAt: now.toISOString() }
            : markOutboxFailed(item, result.errorCode, result.retryable, now)
          : item,
      );
    } catch {
      events = events.map((item, itemIndex) =>
        itemIndex === index ? markOutboxFailed(item, "NETWORK_ERROR", true, now) : item,
      );
    }
  }
  return { ...snapshot, outboxEvents: events };
}
