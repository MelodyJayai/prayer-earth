import type { Identity, IdentityRepository, IdentitySession } from "../domain/identity";
import { localIdentityRepository } from "./identityStorage";
import { runtimeConfig } from "./runtimeConfig";

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export class IdentityHttpError extends Error {
  readonly code: string;
  readonly status: number;
  readonly retryable: boolean;
  readonly requestId?: string;

  constructor(code: string, message: string, status: number, retryable?: boolean, requestId?: string) {
    super(message);
    this.name = "IdentityHttpError";
    this.code = code;
    this.status = status;
    this.retryable = retryable ?? (status >= 500 || status === 429);
    this.requestId = requestId;
  }
}

type ApiError = { error?: { code?: unknown; message?: unknown; retryable?: unknown; requestId?: unknown } };
type AnonymousResponse = {
  identity?: Identity;
  accessToken?: string;
  refreshToken?: string;
  accessTokenExpiresAt?: string;
  tokens?: { accessToken?: string; refreshToken?: string; accessTokenExpiresAt?: string };
};

async function parseJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function unwrapResponse(value: unknown): AnonymousResponse {
  if (!value || typeof value !== "object") return {};
  const root = value as { data?: unknown };
  const data = root.data && typeof root.data === "object" ? root.data : value;
  return data as AnonymousResponse;
}

export class AuthTokenManager {
  constructor(private readonly repository: IdentityRepository = localIdentityRepository) {}

  async getSession(): Promise<IdentitySession | null> {
    return this.repository.getSession();
  }

  async getAccessToken(): Promise<string | null> {
    return (await this.repository.getSession())?.accessToken ?? null;
  }

  /** Callback-friendly variant for HTTP clients whose token provider uses undefined. */
  async getAccessTokenOrUndefined(): Promise<string | undefined> {
    return (await this.repository.getSession())?.accessToken;
  }

  async setSession(session: IdentitySession): Promise<void> {
    await this.repository.saveSession(session);
  }

  async clear(): Promise<void> {
    await this.repository.clearSession();
  }

  async authorizedFetch(fetchImpl: FetchLike, input: string, init: RequestInit = {}): Promise<Response> {
    const token = await this.getAccessToken();
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetchImpl(input, { ...init, headers });
  }

  async fetch(input: string, init: RequestInit = {}): Promise<Response> {
    return this.authorizedFetch((request, options) => fetch(request, options), input, init);
  }
}

export type AnonymousIdentityHttpOptions = {
  baseUrl?: string;
  timeoutMs?: number;
  fetchImpl?: FetchLike;
  repository?: IdentityRepository;
  tokenManager?: AuthTokenManager;
};

export class AnonymousIdentityHttpClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: FetchLike;
  readonly tokenManager: AuthTokenManager;
  private readonly repository: IdentityRepository;

  constructor(options: AnonymousIdentityHttpOptions = {}) {
    this.baseUrl = (options.baseUrl ?? runtimeConfig.apiBaseUrl).replace(/\/$/, "");
    this.timeoutMs = options.timeoutMs ?? runtimeConfig.apiTimeoutMs;
    this.fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
    this.repository = options.repository ?? localIdentityRepository;
    this.tokenManager = options.tokenManager ?? new AuthTokenManager(this.repository);
  }

  async createOrRestoreAnonymous(deviceInstallId?: string): Promise<IdentitySession> {
    if (!this.baseUrl) throw new IdentityHttpError("API_NOT_CONFIGURED", "API base URL is not configured", 0, false);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await this.fetchImpl(`${this.baseUrl}/v1/identities/anonymous`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(deviceInstallId ? { deviceInstallId } : {}),
        signal: controller.signal,
      });
      const payload = await parseJson(response);
      if (!response.ok) {
        const error = payload as ApiError;
        const details = error?.error;
        throw new IdentityHttpError(
          typeof details?.code === "string" ? details.code : `HTTP_${response.status}`,
          typeof details?.message === "string" ? details.message : "Identity request failed",
          response.status,
          typeof details?.retryable === "boolean" ? details.retryable : undefined,
          typeof details?.requestId === "string" ? details.requestId : undefined,
        );
      }
      const data = unwrapResponse(payload);
      const accessToken = data.accessToken ?? data.tokens?.accessToken;
      if (!data.identity || typeof accessToken !== "string" || accessToken.length === 0) {
        throw new IdentityHttpError("INVALID_RESPONSE", "Identity response is missing required fields", response.status, false);
      }
      const session: IdentitySession = {
        identity: data.identity,
        accessToken,
        ...(data.refreshToken ?? data.tokens?.refreshToken ? { refreshToken: data.refreshToken ?? data.tokens?.refreshToken } : {}),
        ...(data.accessTokenExpiresAt ?? data.tokens?.accessTokenExpiresAt ? { accessTokenExpiresAt: data.accessTokenExpiresAt ?? data.tokens?.accessTokenExpiresAt } : {}),
      };
      await this.repository.saveSession(session);
      return session;
    } catch (error) {
      if (error instanceof IdentityHttpError) throw error;
      if (error instanceof Error && error.name === "AbortError") throw new IdentityHttpError("TIMEOUT", "Identity request timed out", 0, true);
      throw new IdentityHttpError("NETWORK_ERROR", "Unable to reach identity service", 0, true);
    } finally {
      clearTimeout(timeout);
    }
  }

  /** Reuses a valid cached session and contacts the service when none exists or it expired. */
  async getOrCreateAnonymous(deviceInstallId?: string): Promise<IdentitySession> {
    const cached = await this.repository.getSession();
    if (
      cached?.identity.status === "active" &&
      (!cached.accessTokenExpiresAt || Date.parse(cached.accessTokenExpiresAt) > Date.now())
    ) return cached;
    return this.createOrRestoreAnonymous(deviceInstallId);
  }
}

export const anonymousIdentityHttpClient = new AnonymousIdentityHttpClient();
