import { describe, expect, it } from "vitest";
import { formatPrayerCount, formatRelativeTime } from "./formatters";

describe("formatters", () => {
  it("formats large prayer counts", () => {
    expect(formatPrayerCount(12_847)).toBe("1.3万");
  });

  it("formats relative times from timestamps", () => {
    const now = Date.parse("2026-08-24T12:00:00.000Z");
    expect(formatRelativeTime("2026-08-24T11:48:00.000Z", now)).toContain("12");
    expect(formatRelativeTime("invalid", now)).toBe("刚刚");
  });
});
