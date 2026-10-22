import type { ImportedContentItem, ImportedContentSegment } from "../contentData";

type JsonRecord = Record<string, unknown>;

function record(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function dimension(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function imageUri(value: unknown): value is string {
  return typeof value === "string" && (/^\/(?!\/)/.test(value) || /^https?:\/\//.test(value));
}

/** The server returns the complete published feed, including the imported archive. */
export function parseContentFeed(payload: unknown): ImportedContentItem[] {
  if (!record(payload) || !Array.isArray(payload.items)) {
    throw new Error("内容列表格式有误");
  }
  const ids = new Set<string>();
  return payload.items.map((raw): ImportedContentItem => {
    if (!record(raw) || typeof raw.id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(raw.id) || ids.has(raw.id)
      || typeof raw.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(raw.date)
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
export async function fetchContentFeed(timeoutMs = 7500): Promise<ImportedContentItem[]> {
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
