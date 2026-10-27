import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchContentFeed, isTextNewsItem, newsVerificationLabel, parseContentFeed } from "./contentFeed";

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
    if (isTextNewsItem(item)) throw new Error("expected an image item");
    expect(item.image).toEqual({ uri: "/uploads/content/image.jpg" });
    expect(item.segments[0]).toEqual({ image: item.image, width: 900, height: 2400 });
    expect(item.sourceFile).toBe("");
    expect(item.searchText).toContain("约翰福音第一章 今日晨修 晨修 2026-10-19");
    expect(item.height).toBe(2400);
  });

  it("uses an empty published feed as authoritative so withdrawn archive items stay hidden", () => {
    expect(parseContentFeed({ version: 2, items: [] })).toEqual([]);
  });

  it("keeps image items intact when a religious text item is added", () => {
    const news = {
      id: "news-20261027-0123456789ab",
      kind: "news",
      date: "2026-10-27",
      channel: "宗教动态",
      title: "教会周报",
      summary: "短摘要",
      sourceName: "教会通讯",
      sourceUrl: "https://example.com/church",
      region: "全球",
      verified: false,
      category: "基督教",
      publishedAt: "2026-10-27T08:00:00Z",
    };
    const [image, text] = parseContentFeed({ version: 3, items: [publishedItem, news] });
    if (isTextNewsItem(image)) throw new Error("expected an image item");
    expect(image.id).toBe("morning-live-1");
    expect(image.segments).toHaveLength(1);
    expect(isTextNewsItem(text)).toBe(true);
    if (!isTextNewsItem(text)) return;
    expect(text.summary).toBe("短摘要");
    expect(text.sourceUrl).toBe("https://example.com/church");
    expect(text.verified).toBe(false);
    expect(newsVerificationLabel(text.verified)).toBe("待核实");
    expect(text.searchText).toContain("短摘要");
    expect(newsVerificationLabel(true)).toBeNull();
  });

  it("rejects unsafe news links and non-religious categories without dropping valid images silently", () => {
    const news = {
      id: "news-20261027-0123456789ab",
      kind: "news",
      date: "2026-10-27",
      channel: "宗教动态",
      title: "教会周报",
      summary: "短摘要",
      sourceName: "教会通讯",
      sourceUrl: "https://example.com/church",
      region: "全球",
      verified: false,
      category: "基督教",
    };
    expect(() => parseContentFeed({ items: [{ ...news, sourceUrl: "javascript:alert(1)" }] })).toThrow();
    expect(() => parseContentFeed({ items: [{ ...news, category: "财经" }] })).toThrow();
    expect(() => parseContentFeed({ items: [{ ...news, verified: "false" }] })).toThrow();
    expect(() => parseContentFeed({ items: [publishedItem, { ...news, id: "news-20261027-0123456789ab", segments: [] }] })).toThrow();
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
