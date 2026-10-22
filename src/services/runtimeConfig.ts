export type RuntimeConfig = {
  apiBaseUrl: string;
  apiTimeoutMs: number;
  enableRemoteContent: boolean;
};

const env: Record<string, string | undefined> = typeof process !== "undefined" ? process.env : {};
const parseBoolean = (value: string | undefined) => value?.toLowerCase() === "true";
const parseTimeout = (value: string | undefined) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 10000;
};

export const runtimeConfig: RuntimeConfig = {
  apiBaseUrl: (env.EXPO_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, ""),
  apiTimeoutMs: parseTimeout(env.EXPO_PUBLIC_API_TIMEOUT_MS),
  enableRemoteContent: parseBoolean(env.EXPO_PUBLIC_ENABLE_REMOTE_CONTENT),
};
