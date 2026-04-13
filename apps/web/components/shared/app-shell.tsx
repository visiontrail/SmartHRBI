"use client";

import { useEffect } from "react";
import { GlobalSidebar } from "./global-sidebar";
import { ChatPanel } from "@/components/chat/chat-panel";
import { WorkspacePanel } from "@/components/workspace/workspace-panel";
import { useUIStore } from "@/stores/ui-store";
import { useChatSessions } from "@/hooks/use-chat";
import { useWorkspaceList } from "@/hooks/use-workspace";
import { useChartAssets } from "@/hooks/use-chart-assets";
import { cn } from "@/lib/utils";

export function AppShell() {
  const activePanel = useUIStore((s) => s.activePanel);
  const chatSidebarOpen = useUIStore((s) => s.chatSidebarOpen);

  useChatSessions();
  useWorkspaceList();
  useChartAssets();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey) {
        if (e.key === "1") {
          e.preventDefault();
          useUIStore.getState().setActivePanel("chat");
        } else if (e.key === "2") {
          e.preventDefault();
          useUIStore.getState().setActivePanel("workspace");
        } else if (e.key === "3") {
          e.preventDefault();
          useUIStore.getState().setActivePanel("both");
        } else if (e.key === "b") {
          e.preventDefault();
          useUIStore.getState().toggleChatSidebar();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-parchment">
      {chatSidebarOpen && <GlobalSidebar />}

      <div className="flex flex-1 min-w-0 overflow-hidden">
        {(activePanel === "chat" || activePanel === "both") && (
          <div
            className={cn(
              "flex flex-col border-r border-border-cream bg-ivory overflow-hidden transition-all duration-200",
              activePanel === "both" ? "w-1/2 min-w-[400px]" : "flex-1"
            )}
          >
            <ChatPanel />
          </div>
        )}

        {(activePanel === "workspace" || activePanel === "both") && (
          <div
            className={cn(
              "flex flex-col bg-parchment overflow-hidden transition-all duration-200",
              activePanel === "both" ? "flex-1 min-w-[400px]" : "flex-1"
            )}
          >
            <WorkspacePanel />
          </div>
        )}
      </div>
    </div>
  );
}
