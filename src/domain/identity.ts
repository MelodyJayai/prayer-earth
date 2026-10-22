export type IdentityKind = "anonymous" | "account";
export type IdentityStatus = "active" | "suspended" | "deleted";
export type AuthProvider = "anonymous" | "email" | "apple" | "google";

export type Identity = {
  id: string;
  kind: IdentityKind;
  authProviders: AuthProvider[];
  displayName?: string;
  locale?: string;
  countryCode?: string;
  status: IdentityStatus;
  consentVersion?: string;
  createdAt: string;
  updatedAt: string;
  lastSeenAt?: string;
};

export type IdentitySession = {
  identity: Identity;
  accessToken: string;
  refreshToken?: string;
  accessTokenExpiresAt?: string;
};

export interface IdentityRepository {
  getSession(): Promise<IdentitySession | null>;
  saveSession(session: IdentitySession): Promise<void>;
  clearSession(): Promise<void>;
}
