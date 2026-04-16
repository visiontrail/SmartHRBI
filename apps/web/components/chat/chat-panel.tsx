"use client";

import { useChatStore } from "@/stores/chat-store";
import { useChatMessages, useCreateSession } from "@/hooks/use-chat";
import { MessageList } from "./message-list";
import { ChatInput } from "./chat-input";
import { ChatEmptyState } from "./chat-empty-state";
import { PanelLeftOpen, MessageSquarePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/stores/ui-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { Skeleton } from "@/components/ui/skeleton";

export function ChatPanel() {
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const chatSidebarOpen = useUIStore((s) => s.chatSidebarOpen);
  const setChatSidebarOpen = useUIStore((s) => s.setChatSidebarOpen);
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId);
  const activeWorkspaceTitle = useWorkspaceStore((s) => {
    const workspace = s.workspaces.find((item) => item.id === s.activeWorkspaceId);
    return workspace?.title ?? null;
  });
  const createSession = useCreateSession();

  const { isLoading } = useChatMessages(activeSessionId);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-border-cream bg-ivory shrink-0">
        <div className="flex items-center gap-2">
          {!chatSidebarOpen && (
            <Button variant="ghost" size="icon-sm" onClick={() => setChatSidebarOpen(true)}>
              <PanelLeftOpen className="w-4 h-4" />
            </Button>
          )}
          <div>
            <h2 className="font-serif text-feature text-near-black">
              {activeSessionId ? <SessionTitle sessionId={activeSessionId} /> : "Chat"}
            </h2>
            <p className="text-label text-stone-gray">
              Ask questions about your HR & project data
            </p>
            <p className="text-label text-stone-gray/90">
              Workspace: {activeWorkspaceTitle ?? (activeWorkspaceId ? activeWorkspaceId : "Unselected")}
            </p>
          </div>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => createSession.mutate(undefined)}
          disabled={createSession.isPending}
        >
          <MessageSquarePlus className="w-4 h-4" />
          New Chat
        </Button>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-hidden">
        {!activeSessionId ? (
          <ChatEmptyState />
        ) : isLoading ? (
          <div className="p-6 space-y-4">
            <Skeleton className="h-16 w-3/4" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-16 w-2/3" />
          </div>
        ) : (
          <MessageList sessionId={activeSessionId} />
        )}
      </div>

      {/* Input */}
      {activeSessionId && <ChatInput sessionId={activeSessionId} />}
    </div>
  );
}

function SessionTitle({ sessionId }: { sessionId: string }) {
  const session = useChatStore((s) => s.sessions.find((s) => s.id === sessionId));
  return <>{session?.title ?? "Conversation"}</>;
}
