import { create } from "zustand";
import type { ChatSession, ChatMessage } from "@/types/chat";

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

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  messagesBySession: {},
  isComposing: false,
  composerText: "",

  setSessions: (sessions) => set({ sessions }),

  addSession: (session) =>
    set((state) => ({
      sessions: [session, ...state.sessions],
    })),

  removeSession: (sessionId) =>
    set((state) => ({
      sessions: state.sessions.filter((s) => s.id !== sessionId),
      activeSessionId: state.activeSessionId === sessionId ? null : state.activeSessionId,
      messagesBySession: (() => {
        const next = { ...state.messagesBySession };
        delete next[sessionId];
        return next;
      })(),
    })),

  setActiveSession: (sessionId) => set({ activeSessionId: sessionId }),

  setMessages: (sessionId, messages) =>
    set((state) => ({
      messagesBySession: { ...state.messagesBySession, [sessionId]: messages },
    })),

  appendMessage: (sessionId, message) =>
    set((state) => ({
      messagesBySession: {
        ...state.messagesBySession,
        [sessionId]: [...(state.messagesBySession[sessionId] ?? []), message],
      },
    })),

  touchSession: (sessionId, updates) =>
    set((state) => ({
      sessions: state.sessions.map((session) => {
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
      }),
    })),

  setComposerText: (text) => set({ composerText: text }),
  setIsComposing: (value) => set({ isComposing: value }),

  getActiveMessages: () => {
    const { activeSessionId, messagesBySession } = get();
    if (!activeSessionId) return [];
    return messagesBySession[activeSessionId] ?? [];
  },
}));
