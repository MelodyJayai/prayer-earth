const relativeFormatter = new Intl.RelativeTimeFormat("zh-CN", {
  numeric: "auto",
});
const todayFormatter = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "long",
});

export function formatPrayerCount(value: number): string {
  if (value >= 10_000) return `${(value / 10_000).toFixed(1)}万`;
  return value.toLocaleString("zh-CN");
}

export function formatRelativeTime(isoDate: string, now = Date.now()): string {
  const timestamp = Date.parse(isoDate);
  if (!Number.isFinite(timestamp)) return "刚刚";
  const seconds = Math.round((timestamp - now) / 1_000);
  if (Math.abs(seconds) < 60) return "刚刚";
  const minutes = Math.round(seconds / 60);
  if (Math.abs(minutes) < 60)
    return relativeFormatter.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return relativeFormatter.format(hours, "hour");
  return relativeFormatter.format(Math.round(hours / 24), "day");
}

export function formatToday(date = new Date()): string {
  return todayFormatter.format(date);
}
