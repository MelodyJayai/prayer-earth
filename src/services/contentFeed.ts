import type { ImportedContentItem, ImportedContentSegment } from "../contentData";

type JsonRecord = Record<string, unknown>;

const NEWS_CATEGORIES = new Set(["基督教", "宗教宣教", "教会", "教会相关"]);

export type TextNewsItem = {
  kind: "news";
  id: string;
  date: string;
  channel: "宗教动态";
  label: "宗教动态";
  title: string;
  excerpt: string;
  summary: string;
  sourceName: string;
  sourceUrl: string;
  region: string;
  verified: boolean;
  category: string;
  searchText: string;
  publishedAt: string;
};

export type FeedItem = ImportedContentItem | TextNewsItem;

export function isTextNewsItem(item: FeedItem): item is TextNewsItem {
  return (item as TextNewsItem).kind === "news";
}

export function newsVerificationLabel(verified: boolean): string | null {
  return verified ? null : "待核实";
}

export function isSafeHttpUrl(value: string): boolean {
  if (!value || value.length > 500 || /[\s\\]/.test(value) || /[\u0000-\u001F\u007F]/.test(value)) return false;
  try {
    const url = new URL(value);
    return (url.protocol === "http:" || url.protocol === "https:") && !url.username && !url.password && Boolean(url.hostname);
  } catch {
    return false;
  }
}

function record(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function dimension(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function imageUri(value: unknown): value is string {
  return typeof value === "string" && (/^\/(?!\/)/.test(value) || /^https?:\/\//.test(value));
}

function boundedText(value: unknown, max: number): string {
  if (typeof value !== "string" || /[\u0000-\u001F\u007F]/.test(value)) throw new Error("内容条目格式有误");
  const text = value.trim();
  if (!text || text.length > max) throw new Error("内容条目格式有误");
  return text;
}

function parseNewsItem(raw: JsonRecord): TextNewsItem {
  if (raw.kind !== "news" || raw.channel !== "宗教动态" || typeof raw.id !== "string" || !/^news-\d{8}-[a-f0-9]{12}$/.test(raw.id)
    || typeof raw.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(raw.date)
    || typeof raw.verified !== "boolean" || typeof raw.category !== "string" || !NEWS_CATEGORIES.has(raw.category)
    || "segments" in raw || "image" in raw) {
    throw new Error("内容条目格式有误");
  }
  const title = boundedText(raw.title, 120);
  const summary = boundedText(raw.summary ?? raw.excerpt, 400);
  const sourceName = boundedText(raw.sourceName, 60);
  const region = boundedText(raw.region, 40);
  if (typeof raw.sourceUrl !== "string" || !isSafeHttpUrl(raw.sourceUrl)) throw new Error("内容条目格式有误");
  const publishedAt = typeof raw.publishedAt === "string" && raw.publishedAt.length <= 40 ? raw.publishedAt : raw.date;
  return {
    kind: "news",
    id: raw.id,
    date: raw.date,
    channel: "宗教动态",
    label: "宗教动态",
    title,
    excerpt: summary,
    summary,
    sourceName,
    sourceUrl: raw.sourceUrl,
    region,
    verified: raw.verified,
    category: raw.category,
    publishedAt,
    searchText: `${title} ${summary} 宗教动态 ${raw.date} ${sourceName} ${region} ${raw.category}`,
  };
}

/** The server returns the complete published feed, including the imported archive. */
export function parseContentFeed(payload: unknown): FeedItem[] {
  if (!record(payload) || !Array.isArray(payload.items)) {
    throw new Error("内容列表格式有误");
  }
  const ids = new Set<string>();
  return payload.items.map((raw): FeedItem => {
    if (!record(raw) || typeof raw.id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(raw.id) || ids.has(raw.id)) {
      throw new Error("内容条目格式有误");
    }
    if (raw.kind === "news" || raw.channel === "宗教动态") {
      const item = parseNewsItem(raw);
      ids.add(item.id);
      return item;
    }
    if (typeof raw.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(raw.date)
      || (raw.channel !== "晨修" && raw.channel !== "宣教动态与见证")
      || !Array.isArray(raw.segments) || raw.segments.length === 0) {
      throw new Error("内容条目格式有误");
    }
    const segments: ImportedContentSegment[] = raw.segments.map((segment: unknown) => {
      if (!record(segment) || !imageUri(segment.uri) || !dimension(segment.width) || !dimension(segment.height)) {
        throw new Error("内容图片格式有误");
      }
      return { image: { uri: segment.uri }, width: segment.width, height: segment.height };
    });
    ids.add(raw.id);
    const sourceFile = typeof raw.sourceFile === "string" ? raw.sourceFile : "";
    const title = typeof raw.title === "string" && raw.title.trim() ? raw.title : `${raw.channel} · ${raw.date}`;
    const excerpt = typeof raw.excerpt === "string" && raw.excerpt.trim() ? raw.excerpt : "点击查看完整图片内容。";
    return {
      id: raw.id,
      date: raw.date,
      channel: raw.channel,
      label: raw.channel,
      title,
      excerpt,
      sourceFile,
      searchText: `${title} ${excerpt} ${raw.channel} ${raw.date} ${sourceFile}`,
      image: segments[0].image,
      width: dimension(raw.width) ? raw.width : segments[0].width,
      height: dimension(raw.height) ? raw.height : segments.reduce((total, segment) => total + segment.height, 0),
      segments,
    };
  });
}

/** A failed or slow update must never prevent opening the bundled content. */
export async function fetchContentFeed(timeoutMs = 7500): Promise<FeedItem[]> {
  const controller = typeof AbortController !== "undefined" ? new AbortController() : undefined;
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    const request = async () => {
      const response = await fetch("/api/content", { cache: "no-store", signal: controller?.signal });
      if (!response.ok) throw new Error("暂时无法更新内容");
      return parseContentFeed(await response.json());
    };
    return await Promise.race([
      request(),
      new Promise<never>((_, reject) => {
        timeout = setTimeout(() => {
          reject(new Error("内容更新超时"));
          controller?.abort();
        }, timeoutMs);
      }),
    ]);
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}
