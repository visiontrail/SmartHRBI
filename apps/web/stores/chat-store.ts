import { create } from "zustand";
import type { ChatSession, ChatMessage } from "@/types/chat";
import {
  CHAT_STORAGE_KEY,
  safeLoadFromStorage,
  safeSaveToStorage,
} from "@/lib/chat/session-storage";

type ChatState = {
  sessions: ChatSession[];
  activeSessionId: string | null;
  messagesBySession: Record<string, ChatMessage[]>;
  isComposing: boolean;
  composerText: string;

  setSessions: (sessions: ChatSession[]) => void;
  addSession: (session: ChatSession) => void;
  removeSession: (sessionId: string) => void;
  setActiveSession: (sessionId: string | null) => void;
  setMessages: (sessionId: string, messages: ChatMessage[]) => void;
  appendMessage: (sessionId: string, message: ChatMessage) => void;
  touchSession: (
    sessionId: string,
    updates: { lastMessage?: string; messageDelta?: number; title?: string }
  ) => void;
  setComposerText: (text: string) => void;
  setIsComposing: (value: boolean) => void;

  getActiveMessages: () => ChatMessage[];
};

type PersistedChatState = {
  version: 1;
  sessions: ChatSession[];
  activeSessionId: string | null;
  messagesBySession: Record<string, ChatMessage[]>;
};

function loadPersistedChatState(): PersistedChatState | null {
  const state = safeLoadFromStorage<Partial<PersistedChatState>>(CHAT_STORAGE_KEY);
  if (!state || !Array.isArray(state.sessions)) {
    return null;
  }

  const messagesBySession = isMessageMap(state.messagesBySession) ? state.messagesBySession : {};
  const sessionIds = new Set(state.sessions.map((session) => session.id));
  const activeSessionId =
    typeof state.activeSessionId === "string" && sessionIds.has(state.activeSessionId)
      ? state.activeSessionId
      : state.sessions[0]?.id ?? null;

  return {
    version: 1,
    sessions: state.sessions,
    activeSessionId,
    messagesBySession: Object.fromEntries(
      Object.entries(messagesBySession).filter(([sessionId]) => sessionIds.has(sessionId))
    ),
  };
}

function persistChatState(state: Pick<ChatState, "sessions" | "activeSessionId" | "messagesBySession">): void {
  safeSaveToStorage<PersistedChatState>(CHAT_STORAGE_KEY, {
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

const persistedChatState = loadPersistedChatState();

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: persistedChatState?.sessions ?? [],
  activeSessionId: persistedChatState?.activeSessionId ?? null,
  messagesBySession: persistedChatState?.messagesBySession ?? {},
  isComposing: false,
  composerText: "",

  setSessions: (sessions) =>
    set((state) => {
      const sessionIds = new Set(sessions.map((session) => session.id));
      const activeSessionId =
        state.activeSessionId && sessionIds.has(state.activeSessionId)
          ? state.activeSessionId
          : sessions[0]?.id ?? null;
      const messagesBySession = Object.fromEntries(
        Object.entries(state.messagesBySession).filter(([sessionId]) => sessionIds.has(sessionId))
      );
      const nextState = { sessions, activeSessionId, messagesBySession };
      persistChatState(nextState);
      return nextState;
    }),

  addSession: (session) =>
    set((state) => {
      const sessions = [session, ...state.sessions.filter((item) => item.id !== session.id)];
      const nextState = {
        sessions,
        activeSessionId: state.activeSessionId,
        messagesBySession: {
          ...state.messagesBySession,
          [session.id]: state.messagesBySession[session.id] ?? [],
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
      const nextState = { sessions, activeSessionId, messagesBySession };
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
          ...(updates.title ? { title: updates.title } : {}),
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
}));
