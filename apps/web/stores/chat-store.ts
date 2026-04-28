import { create } from "zustand";
import { normalizeSessionTitle } from "@/lib/chat/session-title";
import type { ChatSession, ChatMessage } from "@/types/chat";
import type { IngestionPlanAwaitingApproval, IngestionUploadResult } from "@/types/ingestion";
import {
  chatStorageKeyForUser,
  safeLoadFromStorage,
  safeSaveToStorage,
} from "@/lib/chat/session-storage";

export type PendingIngestionApproval = {
  upload: IngestionUploadResult;
  plan: IngestionPlanAwaitingApproval;
};

type ChatState = {
  sessions: ChatSession[];
  activeSessionId: string | null;
  messagesBySession: Record<string, ChatMessage[]>;
  pendingIngestionBySession: Record<string, PendingIngestionApproval | undefined>;
  isComposing: boolean;
  composerText: string;

  setSessions: (sessions: ChatSession[]) => void;
  addSession: (session: ChatSession) => void;
  removeSession: (sessionId: string) => void;
  setActiveSession: (sessionId: string | null) => void;
  setMessages: (sessionId: string, messages: ChatMessage[]) => void;
  appendMessage: (sessionId: string, message: ChatMessage) => void;
  setPendingIngestionApproval: (
    sessionId: string,
    pending: PendingIngestionApproval | null
  ) => void;
  clearPendingIngestionApproval: (sessionId: string) => void;
  touchSession: (
    sessionId: string,
    updates: { lastMessage?: string; messageDelta?: number; title?: string }
  ) => void;
  setComposerText: (text: string) => void;
  setIsComposing: (value: boolean) => void;

  getActiveMessages: () => ChatMessage[];
  initForUser: (userId: string) => void;
  clearForUser: () => void;
};

type PersistedChatState = {
  version: 1;
  sessions: ChatSession[];
  activeSessionId: string | null;
  messagesBySession: Record<string, ChatMessage[]>;
};

// Tracks the active user ID at module level — not in Zustand state to avoid re-renders.
let _currentUserId: string | null = null;
let _initializedUserId: string | null = null;

function normalizeSession(session: ChatSession): ChatSession {
  return {
    ...session,
    title: normalizeSessionTitle(session.title),
  };
}

function normalizeSessions(sessions: ChatSession[]): ChatSession[] {
  return sessions.map(normalizeSession);
}

function loadPersistedChatState(userId: string): PersistedChatState | null {
  const state = safeLoadFromStorage<Partial<PersistedChatState>>(chatStorageKeyForUser(userId));
  if (!state || !Array.isArray(state.sessions)) {
    return null;
  }

  const sessions = normalizeSessions(state.sessions);
  const messagesBySession = isMessageMap(state.messagesBySession) ? state.messagesBySession : {};
  const sessionIds = new Set(sessions.map((session) => session.id));
  const activeSessionId =
    typeof state.activeSessionId === "string" && sessionIds.has(state.activeSessionId)
      ? state.activeSessionId
      : sessions[0]?.id ?? null;

  return {
    version: 1,
    sessions,
    activeSessionId,
    messagesBySession: Object.fromEntries(
      Object.entries(messagesBySession).filter(([sessionId]) => sessionIds.has(sessionId))
    ),
  };
}

function persistChatState(state: Pick<ChatState, "sessions" | "activeSessionId" | "messagesBySession">): void {
  if (!_currentUserId) return;
  safeSaveToStorage<PersistedChatState>(chatStorageKeyForUser(_currentUserId), {
    version: 1,
    sessions: state.sessions,
    activeSessionId: state.activeSessionId,
    messagesBySession: state.messagesBySession,
  });
}

function isMessageMap(value: unknown): value is Record<string, ChatMessage[]> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  return Object.values(value).every((messages) => Array.isArray(messages));
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  messagesBySession: {},
  pendingIngestionBySession: {},
  isComposing: false,
  composerText: "",

  setSessions: (sessions) =>
    set((state) => {
      const normalizedSessions = normalizeSessions(sessions);
      const sessionIds = new Set(normalizedSessions.map((session) => session.id));
      const activeSessionId =
        state.activeSessionId && sessionIds.has(state.activeSessionId)
          ? state.activeSessionId
          : normalizedSessions[0]?.id ?? null;
      const messagesBySession = Object.fromEntries(
        Object.entries(state.messagesBySession).filter(([sessionId]) => sessionIds.has(sessionId))
      );
      const pendingIngestionBySession = Object.fromEntries(
        Object.entries(state.pendingIngestionBySession).filter(([sessionId]) => sessionIds.has(sessionId))
      );
      const nextState = {
        sessions: normalizedSessions,
        activeSessionId,
        messagesBySession,
        pendingIngestionBySession,
      };
      persistChatState(nextState);
      return nextState;
    }),

  addSession: (session) =>
    set((state) => {
      const normalizedSession = normalizeSession(session);
      const sessions = [
        normalizedSession,
        ...state.sessions.filter((item) => item.id !== normalizedSession.id),
      ];
      const nextState = {
        sessions,
        activeSessionId: state.activeSessionId,
        messagesBySession: {
          ...state.messagesBySession,
          [normalizedSession.id]: state.messagesBySession[normalizedSession.id] ?? [],
        },
      };
      persistChatState(nextState);
      return nextState;
    }),

  removeSession: (sessionId) =>
    set((state) => {
      const sessions = state.sessions.filter((s) => s.id !== sessionId);
      const activeSessionId =
        state.activeSessionId === sessionId ? sessions[0]?.id ?? null : state.activeSessionId;
      const messagesBySession = (() => {
        const next = { ...state.messagesBySession };
        delete next[sessionId];
        return next;
      })();
      const pendingIngestionBySession = (() => {
        const next = { ...state.pendingIngestionBySession };
        delete next[sessionId];
        return next;
      })();
      const nextState = { sessions, activeSessionId, messagesBySession, pendingIngestionBySession };
      persistChatState(nextState);
      return nextState;
    }),

  setActiveSession: (sessionId) =>
    set((state) => {
      const nextState = { ...state, activeSessionId: sessionId };
      persistChatState(nextState);
      return { activeSessionId: sessionId };
    }),

  setMessages: (sessionId, messages) =>
    set((state) => {
      const nextState = {
        ...state,
        messagesBySession: { ...state.messagesBySession, [sessionId]: messages },
      };
      persistChatState(nextState);
      return { messagesBySession: nextState.messagesBySession };
    }),

  appendMessage: (sessionId, message) =>
    set((state) => {
      const nextState = {
        ...state,
        messagesBySession: {
          ...state.messagesBySession,
          [sessionId]: [...(state.messagesBySession[sessionId] ?? []), message],
        },
      };
      persistChatState(nextState);
      return {
        messagesBySession: nextState.messagesBySession,
      };
    }),

  setPendingIngestionApproval: (sessionId, pending) =>
    set((state) => {
      const next = { ...state.pendingIngestionBySession };
      if (pending) {
        next[sessionId] = pending;
      } else {
        delete next[sessionId];
      }
      return { pendingIngestionBySession: next };
    }),

  clearPendingIngestionApproval: (sessionId) =>
    set((state) => {
      if (!state.pendingIngestionBySession[sessionId]) {
        return state;
      }
      const next = { ...state.pendingIngestionBySession };
      delete next[sessionId];
      return { pendingIngestionBySession: next };
    }),

  touchSession: (sessionId, updates) =>
    set((state) => {
      const sessions = state.sessions.map((session) => {
        if (session.id !== sessionId) {
          return session;
        }

        const nextMessageCount = Math.max(
          0,
          session.messageCount + Math.max(0, Math.trunc(updates.messageDelta ?? 0))
        );
        return {
          ...session,
          ...(updates.title ? { title: normalizeSessionTitle(updates.title) } : {}),
          ...(updates.lastMessage ? { lastMessage: updates.lastMessage } : {}),
          messageCount: nextMessageCount,
          updatedAt: new Date().toISOString(),
        };
      });
      const nextState = {
        ...state,
        sessions,
      };
      persistChatState(nextState);
      return { sessions };
    }),

  setComposerText: (text) => set({ composerText: text }),
  setIsComposing: (value) => set({ isComposing: value }),

  getActiveMessages: () => {
    const { activeSessionId, messagesBySession } = get();
    if (!activeSessionId) return [];
    return messagesBySession[activeSessionId] ?? [];
  },

  initForUser: (userId: string) => {
    if (_initializedUserId === userId) return;
    _currentUserId = userId;
    _initializedUserId = userId;
    const persisted = loadPersistedChatState(userId);
    set({
      sessions: persisted?.sessions ?? [],
      activeSessionId: persisted?.activeSessionId ?? null,
      messagesBySession: persisted?.messagesBySession ?? {},
      pendingIngestionBySession: {},
    });
  },

  clearForUser: () => {
    _currentUserId = null;
    _initializedUserId = null;
    set({
      sessions: [],
      activeSessionId: null,
      messagesBySession: {},
      pendingIngestionBySession: {},
    });
  },
}));
