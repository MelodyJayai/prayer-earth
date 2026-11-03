import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchPrayerRequests, parsePrayerRequests, prayerFromRequest } from "./prayerRequests";

const item = {
  id: "news-20261027-0123456789ab",
  title: "信徒遭监禁",
  summary: "短摘要",
  sourceName: "教会通讯",
  sourceUrl: "https://example.com/church",
  date: "2026-10-27",
  region: "全球",
  verified: false,
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("prayer requests", () => {
  it("keeps the public fields and drops anything else", () => {
    const [parsed] = parsePrayerRequests({
      version: 3,
      items: [{ ...item, status: "published", needsPrayer: true, prayerExcluded: false }],
    });
    expect(parsed).toEqual(item);
    expect(prayerFromRequest(parsed)).toMatchObject({
      source: "news",
      category: "代祷",
      prayerCount: 0,
      verified: false,
      sourceUrl: "https://example.com/church",
    });
  });

  it("rejects unsafe links and unverified strings", () => {
    expect(() => parsePrayerRequests({ items: [{ ...item, sourceUrl: "javascript:alert(1)" }] })).toThrow();
    expect(() => parsePrayerRequests({ items: [{ ...item, verified: "true" }] })).toThrow();
    expect(parsePrayerRequests({ items: [] })).toEqual([]);
  });

  it("reads the same-origin prayer feed", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ version: 4, items: [item] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(fetchPrayerRequests()).resolves.toEqual([item]);
    expect(fetchMock).toHaveBeenCalledWith("/api/prayer-requests", expect.objectContaining({ cache: "no-store" }));
  });
});
