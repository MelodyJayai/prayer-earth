import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchMissions, parseMissions } from "./missionsFeed";

const item = {
  id: "mission-20261120-0123456789ab",
  title: "洛桑运动区域会议",
  summary: "短摘要",
  sourceName: "洛桑运动",
  sourceUrl: "https://example.com/missions/conference",
  date: "2026-11-20",
  eventDate: "2026-12-01",
  region: "非洲",
  kind: "会议",
  verified: true,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("mission board feed", () => {
  it("maps a valid payload", () => {
    const [parsed] = parseMissions({ version: 3, items: [item] });
    expect(parsed).toMatchObject({ id: item.id, kind: "会议", eventDate: "2026-12-01", verified: true });
  });

  it("accepts an empty feed and items without an event date", () => {
    expect(parseMissions({ version: 1, items: [] })).toEqual([]);
    const { eventDate: _eventDate, ...noEvent } = item;
    expect(parseMissions({ items: [noEvent] })[0].eventDate).toBeUndefined();
  });

  it("rejects unsafe links, unknown kinds, bad ids and duplicates", () => {
    expect(() => parseMissions({ items: [{ ...item, sourceUrl: "javascript:alert(1)" }] })).toThrow();
    expect(() => parseMissions({ items: [{ ...item, kind: "新闻" }] })).toThrow();
    expect(() => parseMissions({ items: [{ ...item, id: "news-20261120-0123456789ab" }] })).toThrow();
    expect(() => parseMissions({ items: [{ ...item, eventDate: "soon" }] })).toThrow();
    expect(() => parseMissions({ items: [{ ...item, verified: "true" }] })).toThrow();
    expect(() => parseMissions({ items: [item, item] })).toThrow();
    expect(() => parseMissions({})).toThrow();
  });

  it("reads /api/missions without caching and reports HTTP errors", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ version: 1, items: [item] }) });
    vi.stubGlobal("fetch", fetchMock);
    await expect(fetchMissions()).resolves.toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/missions", expect.objectContaining({ cache: "no-store" }));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
    await expect(fetchMissions()).rejects.toThrow("暂时无法读取宣教动态");
  });
});
