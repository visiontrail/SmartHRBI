"use client";

import { useEffect } from "react";
import { GlobalSidebar } from "./global-sidebar";
import { WorkspaceOnboardingGate } from "./workspace-onboarding-gate";
import { ChatPanel } from "@/components/chat/chat-panel";
import { WorkspacePanel } from "@/components/workspace/workspace-panel";
import { useUIStore } from "@/stores/ui-store";
import { useChatSessions } from "@/hooks/use-chat";
import { useCreateWorkspace, useWorkspaceList } from "@/hooks/use-workspace";
import { useChartAssets } from "@/hooks/use-chart-assets";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n/context";

export function AppShell() {
  const { t } = useI18n();
  const activePanel = useUIStore((s) => s.activePanel);
  const chatSidebarOpen = useUIStore((s) => s.chatSidebarOpen);
  const workspaces = useWorkspaceStore((s) => s.workspaces);
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId);
  const setActiveWorkspace = useWorkspaceStore((s) => s.setActiveWorkspace);

  useChatSessions();
  const workspaceListQuery = useWorkspaceList();
  const createWorkspace = useCreateWorkspace();
  useChartAssets();

  useEffect(() => {
    if (activeWorkspaceId || workspaces.length === 0) {
      return;
    }
    setActiveWorkspace(workspaces[0].id);
  }, [activeWorkspaceId, setActiveWorkspace, workspaces]);

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

  if (workspaceListQuery.isLoading && workspaces.length === 0) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-parchment">
        <p className="text-body text-stone-gray">{t("app.loadingWorkspaces")}</p>
      </div>
    );
  }

  if (workspaceListQuery.isSuccess && workspaces.length === 0) {
    return (
      <WorkspaceOnboardingGate
        isSubmitting={createWorkspace.isPending}
        onCreate={(name) => createWorkspace.mutate({ title: name })}
      />
    );
  }

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
