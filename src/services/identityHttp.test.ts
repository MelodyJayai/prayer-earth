import { describe, expect, it, vi } from "vitest";
import type { Identity, IdentitySession } from "../domain/identity";
import { createLocalIdentityRepository, parseIdentitySession, type IdentityStorageAdapter } from "./identityStorage";
import { AnonymousIdentityHttpClient, AuthTokenManager, IdentityHttpError, type FetchLike } from "./identityHttp";

const identity: Identity = {
  id: "id-1", kind: "anonymous", authProviders: ["anonymous"], status: "active",
  createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
};
const session: IdentitySession = { identity, accessToken: "access-1", refreshToken: "refresh-1" };

function memoryStorage(): IdentityStorageAdapter & { value: string | null } {
  return {
    value: null,
    async getItem() { return this.value; },
    async setItem(_key, value) { this.value = value; },
    async removeItem() { this.value = null; },
  };
}

describe("identity storage", () => {
  it("persists and restores a session", async () => {
    const storage = memoryStorage();
    const repository = createLocalIdentityRepository(storage);
    await repository.saveSession(session);
    expect(await repository.getSession()).toEqual(session);
    expect(storage.value).toContain('"version":1');
    await repository.clearSession();
    expect(await repository.getSession()).toBeNull();
  });

  it("rejects malformed sessions", () => {
    expect(parseIdentitySession('{"version":1,"session":{"accessToken":"x"}}')).toBeNull();
  });
});

describe("anonymous identity HTTP", () => {
  it("creates and caches an anonymous session", async () => {
    const storage = memoryStorage();
    const repository = createLocalIdentityRepository(storage);
    const fetchImpl: FetchLike = vi.fn(async (_input, init) => {
      expect(init?.method).toBe("POST");
      expect(init?.body).toBe(JSON.stringify({ deviceInstallId: "install-1" }));
      return new Response(JSON.stringify({ data: { identity, accessToken: "access-1", refreshToken: "refresh-1" } }), { status: 201, headers: { "Content-Type": "application/json" } });
    });
    const client = new AnonymousIdentityHttpClient({ baseUrl: "https://api.example.com", repository, fetchImpl });
    await expect(client.createOrRestoreAnonymous("install-1")).resolves.toEqual(session);
    expect(await repository.getSession()).toEqual(session);
  });

  it("maps API errors and adds bearer token", async () => {
    const repository = createLocalIdentityRepository(memoryStorage());
    const manager = new AuthTokenManager(repository);
    await manager.setSession(session);
    const fetchImpl: FetchLike = vi.fn(async () => new Response(JSON.stringify({ error: { code: "RATE_LIMITED", message: "slow", retryable: true } }), { status: 429 }));
    const client = new AnonymousIdentityHttpClient({ baseUrl: "https://api.example.com", repository, fetchImpl, tokenManager: manager });
    await expect(client.createOrRestoreAnonymous()).rejects.toMatchObject({ code: "RATE_LIMITED", status: 429, retryable: true });
    const authorized = await manager.authorizedFetch(fetchImpl, "https://api.example.com/v1/me");
    expect((fetchImpl as ReturnType<typeof vi.fn>).mock.calls.at(-1)?.[1]?.headers).toBeDefined();
    expect((authorized as Response).status).toBe(429);
  });

  it("fails clearly when API is not configured", async () => {
    const client = new AnonymousIdentityHttpClient({ baseUrl: "" });
    await expect(client.createOrRestoreAnonymous()).rejects.toBeInstanceOf(IdentityHttpError);
  });
});
