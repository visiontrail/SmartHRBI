export type AuthContext = {
  userId: string;
  projectId: string;
  role: string;
  department: string | null;
  clearance: number;
};

type CachedAccessToken = {
  accessToken: string;
  expiresAt: number;
  scopeKey: string;
};

const AUTH_STORAGE_KEY = "cognitrix:access-token:v1";
const TOKEN_REFRESH_SKEW_SECONDS = 30;

export async function getAuthorizationHeader(
  apiBaseUrl: string,
  context: AuthContext
): Promise<Record<string, string>> {
  const token = await getAccessToken(apiBaseUrl, context);
  return {
    Authorization: `Bearer ${token}`
  };
}

async function getAccessToken(apiBaseUrl: string, context: AuthContext): Promise<string> {
  const normalized = normalizeAuthContext(context);
  const scopeKey = buildScopeKey(normalized);
  const cached = loadCachedAccessToken();
  if (cached && cached.scopeKey === scopeKey && cached.expiresAt > nowInSeconds() + TOKEN_REFRESH_SKEW_SECONDS) {
    return cached.accessToken;
  }

  const response = await fetch(`${apiBaseUrl}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      user_id: normalized.userId,
      project_id: normalized.projectId,
      role: normalized.role,
      department: normalized.department,
      clearance: normalized.clearance
    })
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(readErrorMessage(payload, `auth_login_failed_${response.status}`));
  }

  const accessToken = isRecord(payload) ? String(payload.access_token ?? "") : "";
  const expiresAt = isRecord(payload) ? Number(payload.expires_at ?? 0) : 0;
  if (!accessToken || !Number.isFinite(expiresAt) || expiresAt <= 0) {
    throw new Error("auth_login_invalid_payload");
  }

  saveCachedAccessToken({
    accessToken,
    expiresAt,
    scopeKey
  });
  return accessToken;
}

function normalizeAuthContext(context: AuthContext): AuthContext {
  return {
    userId: context.userId.trim(),
    projectId: context.projectId.trim(),
    role: context.role.trim().toLowerCase() || "viewer",
    department: context.department?.trim() || null,
    clearance: Number.isFinite(context.clearance) ? Math.max(0, Math.trunc(context.clearance)) : 0
  };
}

function buildScopeKey(context: AuthContext): string {
  return JSON.stringify([
    context.userId,
    context.projectId,
    context.role,
    context.department,
    context.clearance
  ]);
}

function loadCachedAccessToken(): CachedAccessToken | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw) as CachedAccessToken;
    if (
      !parsed ||
      typeof parsed.accessToken !== "string" ||
      typeof parsed.scopeKey !== "string" ||
      typeof parsed.expiresAt !== "number"
    ) {
      return null;
    }

    return parsed;
  } catch {
    return null;
  }
}

function saveCachedAccessToken(token: CachedAccessToken): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(token));
  } catch {
    // Ignore storage failures and keep the request path usable in memory.
  }
}

function readErrorMessage(payload: unknown, fallback: string): string {
  if (!isRecord(payload)) {
    return fallback;
  }

  const detail = isRecord(payload.detail) ? payload.detail : null;
  const detailMessage = detail ? String(detail.message ?? "") : "";
  if (detailMessage) {
    return detailMessage;
  }

  const payloadMessage = String(payload.message ?? "");
  return payloadMessage || fallback;
}

function nowInSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
