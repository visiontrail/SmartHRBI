import { beforeEach, describe, expect, it } from "vitest";

import { createSession, deleteSession, fetchMessages, fetchSessions } from "../../lib/mock/mock-api";
import { CHAT_STORAGE_KEY } from "../../lib/chat/session-storage";

describe("mock chat API persistence", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("does not seed fixed mock conversations", async () => {
    await expect(fetchSessions()).resolves.toEqual([]);
  });

  it("persists created and deleted conversations", async () => {
    const session = await createSession("Saved conversation");

    await expect(fetchSessions()).resolves.toEqual([expect.objectContaining({ id: session.id })]);

    await deleteSession(session.id);

    await expect(fetchSessions()).resolves.toEqual([]);
  });

  it("loads stored messages for a persisted conversation", async () => {
    window.localStorage.setItem(
      CHAT_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        activeSessionId: "session-1",
        sessions: [
          {
            id: "session-1",
            title: "Persisted",
            createdAt: "2026-04-16T00:00:00.000Z",
            updatedAt: "2026-04-16T00:00:00.000Z",
            messageCount: 1
          }
        ],
        messagesBySession: {
          "session-1": [
            {
              id: "message-1",
              sessionId: "session-1",
              role: "assistant",
              content: "restored",
              timestamp: "2026-04-16T00:00:00.000Z"
            }
          ]
        }
      })
    );

    await expect(fetchMessages("session-1")).resolves.toEqual([
      expect.objectContaining({ id: "message-1", content: "restored" })
    ]);
  });
});
