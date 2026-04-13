"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useChatStore } from "@/stores/chat-store";
import { useAssetStore } from "@/stores/asset-store";
import { useUIStore } from "@/stores/ui-store";
import * as api from "@/lib/mock/mock-api";

export function useChatSessions() {
  const setSessions = useChatStore((s) => s.setSessions);

  return useQuery({
    queryKey: ["chat-sessions"],
    queryFn: async () => {
      const sessions = await api.fetchSessions();
      setSessions(sessions);
      return sessions;
    },
  });
}

export function useChatMessages(sessionId: string | null) {
  const setMessages = useChatStore((s) => s.setMessages);

  return useQuery({
    queryKey: ["chat-messages", sessionId],
    queryFn: async () => {
      if (!sessionId) return [];
      const msgs = await api.fetchMessages(sessionId);
      setMessages(sessionId, msgs);
      return msgs;
    },
    enabled: !!sessionId,
  });
}

export function useCreateSession() {
  const queryClient = useQueryClient();
  const addSession = useChatStore((s) => s.addSession);
  const setActiveSession = useChatStore((s) => s.setActiveSession);

  return useMutation({
    mutationFn: (title?: string) => api.createSession(title),
    onSuccess: (session) => {
      addSession(session);
      setActiveSession(session.id);
      queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
    },
  });
}

export function useDeleteSession() {
  const queryClient = useQueryClient();
  const removeSession = useChatStore((s) => s.removeSession);

  return useMutation({
    mutationFn: (sessionId: string) => api.deleteSession(sessionId),
    onSuccess: (_, sessionId) => {
      removeSession(sessionId);
      queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
    },
  });
}

export function useSendMessage() {
  const queryClient = useQueryClient();
  const appendMessage = useChatStore((s) => s.appendMessage);
  const addAsset = useAssetStore((s) => s.addAsset);
  const setIsSending = useUIStore((s) => s.setIsSending);

  return useMutation({
    mutationFn: async ({ sessionId, content }: { sessionId: string; content: string }) => {
      setIsSending(true);
      return api.sendMessage(sessionId, content);
    },
    onSuccess: ({ userMessage, assistantMessage, chartAsset }, { sessionId }) => {
      appendMessage(sessionId, userMessage);
      appendMessage(sessionId, assistantMessage);
      if (chartAsset) {
        addAsset(chartAsset);
      }
      queryClient.invalidateQueries({ queryKey: ["chat-messages", sessionId] });
      queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
      queryClient.invalidateQueries({ queryKey: ["chart-assets"] });
    },
    onSettled: () => {
      setIsSending(false);
    },
  });
}
