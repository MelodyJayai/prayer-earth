import { isSafeHttpUrl } from "./contentFeed";

export const MISSION_KINDS = ["会议", "进展", "报告"] as const;
export type MissionKind = (typeof MISSION_KINDS)[number];

export type MissionItem = {
  id: string;
  title: string;
  summary: string;
  sourceName: string;
  sourceUrl: string;
  /** Publication or announcement day (UTC, YYYY-MM-DD). */
  date: string;
  /** Optional day the event takes place; may be in the future. */
  eventDate?: string;
  region: string;
  kind: MissionKind;
  verified: boolean;
};

type JsonRecord = Record<string, unknown>;

const FORMAT_ERROR = "宣教动态格式有误";

function record(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function boundedText(value: unknown, max: number): string {
  if (typeof value !== "string" || /[\u0000-\u001F\u007F]/.test(value)) throw new Error(FORMAT_ERROR);
  const text = value.trim();
  if (!text || text.length > max) throw new Error(FORMAT_ERROR);
  return text;
}

function isDay(value: unknown): value is string {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

export function parseMissions(payload: unknown): MissionItem[] {
  if (!record(payload) || !Array.isArray(payload.items)) throw new Error(FORMAT_ERROR);
  const ids = new Set<string>();
  return payload.items.map((raw) => {
    if (!record(raw) || typeof raw.id !== "string" || !/^mission-\d{8}-[a-f0-9]{12}$/.test(raw.id) || ids.has(raw.id)) {
      throw new Error(FORMAT_ERROR);
    }
    if (!isDay(raw.date) || typeof raw.verified !== "boolean") throw new Error(FORMAT_ERROR);
    if (typeof raw.sourceUrl !== "string" || !isSafeHttpUrl(raw.sourceUrl)) throw new Error(FORMAT_ERROR);
    if (typeof raw.kind !== "string" || !(MISSION_KINDS as readonly string[]).includes(raw.kind)) throw new Error(FORMAT_ERROR);
    if (raw.eventDate !== undefined && !isDay(raw.eventDate)) throw new Error(FORMAT_ERROR);
    ids.add(raw.id);
    return {
      id: raw.id,
      title: boundedText(raw.title, 120),
      summary: boundedText(raw.summary, 400),
      sourceName: boundedText(raw.sourceName, 60),
      sourceUrl: raw.sourceUrl,
      date: raw.date,
      eventDate: raw.eventDate as string | undefined,
      region: boundedText(raw.region, 40),
      kind: raw.kind as MissionKind,
      verified: raw.verified,
    };
  });
}

/** Same-origin read, like the prayer feed. connect-src stays 'self'. */
export async function fetchMissions(timeoutMs = 7500): Promise<MissionItem[]> {
  const controller = typeof AbortController !== "undefined" ? new AbortController() : undefined;
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    const request = async () => {
      const response = await fetch("/api/missions", { cache: "no-store", signal: controller?.signal });
      if (!response.ok) throw new Error("暂时无法读取宣教动态");
      return parseMissions(await response.json());
    };
    return await Promise.race([
      request(),
      new Promise<never>((_, reject) => {
        timeout = setTimeout(() => {
          reject(new Error("宣教动态读取超时"));
          controller?.abort();
        }, timeoutMs);
      }),
    ]);
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}
