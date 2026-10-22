import AsyncStorage from "@react-native-async-storage/async-storage";
import type { AuthProvider, Identity, IdentityRepository, IdentitySession } from "../domain/identity";

export const IDENTITY_STORAGE_KEY = "prayer-earth:identity:v1";
export const IDENTITY_SCHEMA_VERSION = 1;

export interface IdentityStorageAdapter {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

function isIdentity(value: unknown): value is Identity {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<Identity>;
  const providers = item.authProviders;
  return typeof item.id === "string" && item.id.length > 0 &&
    (item.kind === "anonymous" || item.kind === "account") &&
    Array.isArray(providers) && providers.every((provider): provider is AuthProvider =>
      provider === "anonymous" || provider === "email" || provider === "apple" || provider === "google",
    ) &&
    (item.status === "active" || item.status === "suspended" || item.status === "deleted") &&
    typeof item.createdAt === "string" && Number.isFinite(Date.parse(item.createdAt)) &&
    typeof item.updatedAt === "string" && Number.isFinite(Date.parse(item.updatedAt));
}

export function parseIdentitySession(raw: string | null): IdentitySession | null {
  if (!raw) return null;
  try {
    const data = JSON.parse(raw) as { version?: unknown; session?: unknown };
    if (data.version !== IDENTITY_SCHEMA_VERSION) return null;
    const candidate = data.session && typeof data.session === "object" ? data.session : data;
    const session = candidate as Partial<IdentitySession>;
    if (!isIdentity(session.identity) || typeof session.accessToken !== "string" || session.accessToken.length === 0) return null;
    if (session.refreshToken !== undefined && typeof session.refreshToken !== "string") return null;
    if (session.accessTokenExpiresAt !== undefined && (typeof session.accessTokenExpiresAt !== "string" || !Number.isFinite(Date.parse(session.accessTokenExpiresAt)))) return null;
    return {
      identity: session.identity,
      accessToken: session.accessToken,
      ...(session.refreshToken ? { refreshToken: session.refreshToken } : {}),
      ...(session.accessTokenExpiresAt ? { accessTokenExpiresAt: session.accessTokenExpiresAt } : {}),
    };
  } catch {
    return null;
  }
}

export class LocalIdentityRepository implements IdentityRepository {
  constructor(private readonly storage: IdentityStorageAdapter = AsyncStorage) {}

  async getSession(): Promise<IdentitySession | null> {
    return parseIdentitySession(await this.storage.getItem(IDENTITY_STORAGE_KEY));
  }

  async saveSession(session: IdentitySession): Promise<void> {
    await this.storage.setItem(IDENTITY_STORAGE_KEY, JSON.stringify({ version: IDENTITY_SCHEMA_VERSION, session }));
  }

  async clearSession(): Promise<void> {
    await this.storage.removeItem(IDENTITY_STORAGE_KEY);
  }
}

export function createLocalIdentityRepository(storage?: IdentityStorageAdapter): IdentityRepository {
  return new LocalIdentityRepository(storage);
}

export const localIdentityRepository: IdentityRepository = new LocalIdentityRepository();
