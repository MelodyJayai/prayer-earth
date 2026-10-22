import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchContentFeed, parseContentFeed } from "./contentFeed";

const publishedItem = {
  id: "morning-live-1",
  date: "2026-10-19",
  channel: "晨修",
  title: "约翰福音第一章",
  excerpt: "今日晨修",
  segments: [{ uri: "/uploads/content/image.jpg", width: 900, height: 2400 }],
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("published content feed", () => {
  it("maps newly published images to the existing app model and searchable text", () => {
    const [item] = parseContentFeed({ version: "now", items: [publishedItem] });
    expect(item.image).toEqual({ uri: "/uploads/content/image.jpg" });
    expect(item.segments[0]).toEqual({ image: item.image, width: 900, height: 2400 });
    expect(item.sourceFile).toBe("");
    expect(item.searchText).toContain("约翰福音第一章 今日晨修 晨修 2026-10-19");
    expect(item.height).toBe(2400);
  });

  it("uses an empty published feed as authoritative so withdrawn archive items stay hidden", () => {
    expect(parseContentFeed({ version: 2, items: [] })).toEqual([]);
  });

  it("rejects a broken feed instead of silently replacing the working archive with partial data", () => {
    expect(() => parseContentFeed({ items: [publishedItem, publishedItem] })).toThrow();
    expect(() => parseContentFeed({ items: [{ ...publishedItem, id: "../admin" }] })).toThrow();
    expect(() => parseContentFeed({ items: [{ ...publishedItem, segments: [{ uri: "javascript:alert(1)", width: 10, height: 20 }] }] })).toThrow();
    expect(() => parseContentFeed({ items: [{ ...publishedItem, segments: [] }] })).toThrow();
  });

  it("does not use cached API responses when refreshing daily content", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [publishedItem] }) });
    vi.stubGlobal("fetch", fetch);
    expect((await fetchContentFeed())[0].id).toBe("morning-live-1");
    expect(fetch).toHaveBeenCalledWith("/api/content", expect.objectContaining({ cache: "no-store" }));
  });

  it("bounds the whole update including a stalled response body", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: () => new Promise(() => {}) }));
    const rejected = expect(fetchContentFeed(100)).rejects.toThrow("内容更新超时");
    await vi.advanceTimersByTimeAsync(100);
    await rejected;
  });
});
