import { describe, expect, it, vi } from "vitest";
import { HttpClient, HttpError } from "../services/httpClient";
import { RemotePrayerRepository } from "./httpPrayerRepository";

const response = (body: unknown, status = 200) =>
  new Response(body === undefined ? "" : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

describe("HttpClient", () => {
  it("serializes JSON and auth/idempotency headers", async () => {
    const fetcher = vi.fn(async () => response({ ok: true }));
    const client = new HttpClient({ baseUrl: "https://api.example.test/", accessToken: "token", fetch: fetcher });
    await client.post("/v1/prayers", { title: "hello" }, { idempotencyKey: "idem-1" });
    expect(fetcher).toHaveBeenCalledWith("https://api.example.test/v1/prayers", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ title: "hello" }),
      headers: expect.objectContaining({ Authorization: "Bearer token", "Idempotency-Key": "idem-1" }),
    }));
  });

  it("normalizes contract errors", async () => {
    const client = new HttpClient({ baseUrl: "https://api.example.test", fetch: vi.fn(async () => response({ error: { code: "RATE_LIMITED", message: "slow down", retryable: true, requestId: "req-1" } }, 429)) });
    await expect(client.get("/v1/me")).rejects.toMatchObject({ status: 429, code: "RATE_LIMITED", retryable: true, requestId: "req-1" });
    await expect(client.get("/v1/me")).rejects.toBeInstanceOf(HttpError);
  });
});

describe("RemotePrayerRepository", () => {
  it("builds list query and exposes contract operations", async () => {
    const prayer = { id: "p1", title: "A", excerpt: "B", category: "和平", urgent: false, locale: "zh-CN", source: "seed", status: "published", moderationState: "approved", prayerCount: 0, prayedByMe: false, canEdit: false, canDelete: false, createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z", version: 1 };
    const calls: string[] = [];
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => { calls.push(`${init?.method ?? "GET"} ${url}`); if (url.includes("outbox")) return response({ results: [] }); if (url.includes("prayer-action")) return response({ prayed: true }); if (url.includes("/prayers/p1")) return response(prayer); return response({ data: [prayer], page: { limit: 1, nextCursor: null } }); });
    const repository = new RemotePrayerRepository({ client: new HttpClient({ baseUrl: "https://api.example.test", fetch: fetcher }), cache: { loadSnapshot: async () => ({ prayedIds: [], publishedPrayers: [], outboxEvents: [] }), saveSnapshot: async () => undefined, enqueueOutboxEvent: async () => undefined } });
    await expect(repository.listPrayers({ limit: 1, urgent: false, locale: "zh-CN" })).resolves.toMatchObject({ data: [prayer] });
    await expect(repository.getPrayer("p1")).resolves.toEqual(prayer);
    await repository.createPrayer({ title: "A", excerpt: "B", category: "和平" }, "create-1");
    await repository.togglePrayer("p1", true, "toggle-1");
    await repository.deletePrayer("p1", 1, "delete-1");
    await repository.report({ targetType: "prayer", targetId: "p1", reason: "spam" }, "report-1");
    await repository.sendOutboxBatch([]);
    expect(calls.some((call) => call.includes("GET https://api.example.test/v1/prayers?limit=1&urgent=false&locale=zh-CN"))).toBe(true);
    expect(fetcher.mock.calls.find(([, init]) => init?.method === "DELETE")?.[1]).toEqual(expect.objectContaining({ headers: expect.objectContaining({ "If-Match": "1", "Idempotency-Key": "delete-1" }) }));
  });
});
