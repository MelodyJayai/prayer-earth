import type { Prayer } from "../domain/types";
import { isSafeHttpUrl } from "./contentFeed";

export type PrayerRequest = {
  id: string;
  title: string;
  summary: string;
  sourceName: string;
  sourceUrl: string;
  date: string;
  region: string;
  verified: boolean;
};

type JsonRecord = Record<string, unknown>;

function record(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function boundedText(value: unknown, max: number): string {
  if (typeof value !== "string" || /[\u0000-\u001F\u007F]/.test(value)) throw new Error("代祷列表格式有误");
  const text = value.trim();
  if (!text || text.length > max) throw new Error("代祷列表格式有误");
  return text;
}

export function parsePrayerRequests(payload: unknown): PrayerRequest[] {
  if (!record(payload) || !Array.isArray(payload.items)) throw new Error("代祷列表格式有误");
  const ids = new Set<string>();
  return payload.items.map((raw) => {
    if (!record(raw) || typeof raw.id !== "string" || !/^news-\d{8}-[a-f0-9]{12}$/.test(raw.id) || ids.has(raw.id)) {
      throw new Error("代祷列表格式有误");
    }
    if (typeof raw.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(raw.date) || typeof raw.verified !== "boolean") {
      throw new Error("代祷列表格式有误");
    }
    if (typeof raw.sourceUrl !== "string" || !isSafeHttpUrl(raw.sourceUrl)) throw new Error("代祷列表格式有误");
    ids.add(raw.id);
    return {
      id: raw.id,
      title: boundedText(raw.title, 120),
      summary: boundedText(raw.summary, 400),
      sourceName: boundedText(raw.sourceName, 60),
      sourceUrl: raw.sourceUrl,
      date: raw.date,
      region: boundedText(raw.region, 40),
      verified: raw.verified,
    };
  });
}

export function prayerFromRequest(item: PrayerRequest): Prayer {
  return {
    id: item.id,
    title: item.title,
    excerpt: item.summary,
    location: item.region,
    flag: "",
    category: "代祷",
    prayerCount: 0,
    createdAt: `${item.date}T00:00:00.000Z`,
    urgent: false,
    prayedByMe: false,
    source: "news",
    sourceUrl: item.sourceUrl,
    sourceName: item.sourceName,
    verified: item.verified,
  };
}

/** Same-origin read. Remote content flags stay off; connect-src remains 'self'. */
export async function fetchPrayerRequests(timeoutMs = 7500): Promise<PrayerRequest[]> {
  const controller = typeof AbortController !== "undefined" ? new AbortController() : undefined;
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    const request = async () => {
      const response = await fetch("/api/prayer-requests", { cache: "no-store", signal: controller?.signal });
      if (!response.ok) throw new Error("暂时无法读取需要代祷的动态");
      return parsePrayerRequests(await response.json());
    };
    return await Promise.race([
      request(),
      new Promise<never>((_, reject) => {
        timeout = setTimeout(() => {
          reject(new Error("代祷列表超时"));
          controller?.abort();
        }, timeoutMs);
      }),
    ]);
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}
