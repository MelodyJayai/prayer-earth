import { describe, expect, it } from "vitest";
import { createOutboxEvent } from "./prayerStorage";
import { drainOutbox } from "./outbox";

describe("drainOutbox", () => {
  it("sends due events in order and marks success", async () => {
    const first = createOutboxEvent({ aggregateType: "prayer", eventType: "prayer.create", payload: {}, now: "2026-09-05T00:00:00.000Z" });
    const second = createOutboxEvent({ aggregateType: "prayer", eventType: "prayer.create", payload: {}, now: "2026-09-05T00:00:01.000Z" });
    const sent: string[] = [];
    const result = await drainOutbox(
      { prayedIds: [], publishedPrayers: [], outboxEvents: [first, second] },
      async (event) => { sent.push(event.id); return { ok: true }; },
      new Date("2026-09-05T00:01:00.000Z"),
    );
    expect(sent).toEqual([first.id, second.id]);
    expect(result.outboxEvents.every(({ status }) => status === "succeeded")).toBe(true);
  });

  it("backs off retryable errors and dead-letters permanent errors", async () => {
    const event = createOutboxEvent({ aggregateType: "report", eventType: "report.create", payload: {}, now: "2026-09-05T00:00:00.000Z" });
    const result = await drainOutbox(
      { prayedIds: [], publishedPrayers: [], outboxEvents: [event] },
      async () => ({ ok: false, errorCode: "VALIDATION_ERROR", retryable: false }),
      new Date("2026-09-05T00:01:00.000Z"),
    );
    expect(result.outboxEvents[0].status).toBe("dead");
    expect(result.outboxEvents[0].lastErrorCode).toBe("VALIDATION_ERROR");
  });
});
