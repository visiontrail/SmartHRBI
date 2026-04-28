import { afterEach, describe, expect, it } from "vitest";

import {
  clearInMemoryToken,
  getActiveAuthContext,
  setInMemoryToken,
  type AuthContext,
} from "../../lib/auth/session";

const FALLBACK_CONTEXT: AuthContext = {
  userId: "demo-user",
  projectId: "demo-project",
  role: "hr",
  department: "HR",
  clearance: 1,
};

describe("auth session context", () => {
  afterEach(() => {
    clearInMemoryToken();
    window.localStorage.clear();
  });

  it("uses the signed-in token scope for request bodies", () => {
    setInMemoryToken(
      makeUnsignedJwt({
        sub: "user-123",
        project_id: "default",
        role: "admin",
        department: null,
        clearance: 0,
      }),
      4102444800
    );

    expect(getActiveAuthContext(FALLBACK_CONTEXT)).toEqual({
      userId: "user-123",
      projectId: "default",
      role: "admin",
      department: null,
      clearance: 0,
    });
  });

  it("falls back to legacy context when no user token exists", () => {
    expect(getActiveAuthContext(FALLBACK_CONTEXT)).toEqual(FALLBACK_CONTEXT);
  });
});

function makeUnsignedJwt(payload: Record<string, unknown>): string {
  return [
    encodeBase64Url({ alg: "HS256", typ: "JWT" }),
    encodeBase64Url(payload),
    "signature",
  ].join(".");
}

function encodeBase64Url(payload: Record<string, unknown>): string {
  return window
    .btoa(JSON.stringify(payload))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}
