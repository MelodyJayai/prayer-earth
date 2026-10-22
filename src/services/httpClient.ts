/** Small vendor-neutral JSON HTTP client used by remote repositories. */
export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
    requestId?: string;
    retryable?: boolean;
    fieldErrors?: Record<string, string>;
  };
};

export class HttpError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;
  readonly retryable: boolean;
  readonly fieldErrors?: Record<string, string>;

  constructor(status: number, body?: ApiErrorBody, fallbackMessage?: string) {
    const detail = body?.error;
    super(detail?.message ?? fallbackMessage ?? `HTTP ${status}`);
    this.name = "HttpError";
    this.status = status;
    this.code = detail?.code ?? `HTTP_${status}`;
    this.requestId = detail?.requestId;
    this.retryable = detail?.retryable ?? (status === 408 || status === 429 || status >= 500);
    this.fieldErrors = detail?.fieldErrors;
  }
}

export type HttpClientOptions = {
  baseUrl: string;
  fetch?: FetchLike;
  timeoutMs?: number;
  /** Called for every request so rotated tokens are picked up automatically. */
  accessToken?: string | (() => string | undefined | Promise<string | undefined>);
  defaultHeaders?: Record<string, string>;
};

export type RequestOptions = Omit<RequestInit, "body" | "headers"> & {
  body?: unknown;
  headers?: Record<string, string>;
  idempotencyKey?: string;
  ifMatch?: number | string;
  authenticated?: boolean;
};

export class HttpClient {
  private readonly baseUrl: string;
  private readonly fetcher: FetchLike;
  private readonly token?: HttpClientOptions["accessToken"];
  private readonly defaultHeaders: Record<string, string>;
  private readonly timeoutMs: number;

  constructor(options: HttpClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.fetcher = options.fetch ?? ((input, init) => fetch(input, init));
    this.token = options.accessToken;
    this.defaultHeaders = options.defaultHeaders ?? {};
    this.timeoutMs = options.timeoutMs && options.timeoutMs > 0 ? options.timeoutMs : 10000;
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const url = `${this.baseUrl}/${path.replace(/^\/+/, "")}`;
    const { body: requestBody, headers: requestHeaders, idempotencyKey, ifMatch, authenticated, ...requestInit } = options;
    const headers: Record<string, string> = {
      Accept: "application/json",
      ...this.defaultHeaders,
      ...(requestHeaders ?? {}),
    };
    let body: BodyInit | undefined;
    if (requestBody !== undefined) {
      headers["Content-Type"] ??= "application/json";
      body = JSON.stringify(requestBody);
    }
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
    if (ifMatch !== undefined) headers["If-Match"] = String(ifMatch);
    if (authenticated !== false && this.token) {
      const token = typeof this.token === "function" ? await this.token() : this.token;
      if (token) headers.Authorization = `Bearer ${token}`;
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    let response: Response;
    try {
      response = await this.fetcher(url, {
        ...requestInit,
        body,
        headers,
        signal: requestInit.signal ?? controller.signal,
      });
    } catch (error) {
      const timedOut = error instanceof Error && error.name === "AbortError";
      throw new HttpError(0, {
        error: {
          code: timedOut ? "TIMEOUT" : "NETWORK_ERROR",
          message: timedOut ? "Request timed out" : "Unable to reach API",
          retryable: true,
        },
      });
    } finally {
      clearTimeout(timeout);
    }
    const responseValue = response as Response & { text?: () => Promise<string>; json?: () => Promise<unknown> };
    const raw = typeof responseValue.text === "function"
      ? await responseValue.text()
      : typeof responseValue.json === "function" ? JSON.stringify(await responseValue.json()) : "";
    let parsed: unknown;
    if (raw) {
      try { parsed = JSON.parse(raw); } catch { parsed = raw; }
    }
    const ok = response.ok ?? (response.status >= 200 && response.status < 300);
    if (!ok) {
      const bodyValue = parsed && typeof parsed === "object" ? parsed as ApiErrorBody : undefined;
      throw new HttpError(response.status, bodyValue, typeof parsed === "string" ? parsed : undefined);
    }
    return parsed as T;
  }

  get<T>(path: string, options?: Omit<RequestOptions, "body" | "method">) {
    return this.request<T>(path, { ...options, method: "GET" });
  }

  post<T>(path: string, body?: unknown, options?: Omit<RequestOptions, "body" | "method">) {
    return this.request<T>(path, { ...options, method: "POST", body });
  }

  delete<T = void>(path: string, options?: Omit<RequestOptions, "body" | "method">) {
    return this.request<T>(path, { ...options, method: "DELETE" });
  }
}
