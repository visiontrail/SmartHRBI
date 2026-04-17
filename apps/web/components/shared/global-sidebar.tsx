"use client";

import {
  MessageSquare,
  LayoutDashboard,
  Plus,
  PanelLeftClose,
  Trash2,
  BarChart3,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { useChatStore } from "@/stores/chat-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { useUIStore, type ActivePanel } from "@/stores/ui-store";
import { useCreateSession, useDeleteSession } from "@/hooks/use-chat";
import { useCreateWorkspace, useDeleteWorkspace } from "@/hooks/use-workspace";
import { cn } from "@/lib/utils";
import { truncate, formatRelativeTime } from "@/lib/utils";

export function GlobalSidebar() {
  const sessions = useChatStore((s) => s.sessions);
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const setActiveSession = useChatStore((s) => s.setActiveSession);

  const workspaces = useWorkspaceStore((s) => s.workspaces);
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId);
  const setActiveWorkspace = useWorkspaceStore((s) => s.setActiveWorkspace);

  const activePanel = useUIStore((s) => s.activePanel);
  const setActivePanel = useUIStore((s) => s.setActivePanel);
  const toggleChatSidebar = useUIStore((s) => s.toggleChatSidebar);

  const createSession = useCreateSession();
  const deleteSession = useDeleteSession();
  const createWorkspace = useCreateWorkspace();
  const deleteWorkspace = useDeleteWorkspace();

  const handleNewChat = () => {
    createSession.mutate(undefined);
    if (activePanel === "workspace") setActivePanel("both");
  };

  const handleNewWorkspace = () => {
    createWorkspace.mutate({});
    if (activePanel === "chat") setActivePanel("both");
  };

  const handleSelectSession = (sessionId: string) => {
    setActiveSession(sessionId);
    if (activePanel === "workspace") setActivePanel("both");
  };

  const handleSelectWorkspace = (workspaceId: string) => {
    setActiveWorkspace(workspaceId);
    if (activePanel === "chat") setActivePanel("both");
  };

  return (
    <aside className="flex flex-col w-sidebar min-w-sidebar border-r border-border-cream bg-ivory h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-cream">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-terracotta" />
          <h1 className="font-serif text-feature text-near-black">SmartHRBI</h1>
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={toggleChatSidebar}>
              <PanelLeftClose className="w-4 h-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Hide sidebar (⌘B)</TooltipContent>
        </Tooltip>
      </div>

      {/* Panel Switcher */}
      <div className="flex items-center gap-1 px-3 py-2 border-b border-border-cream">
        <PanelButton
          active={activePanel === "chat" || activePanel === "both"}
          onClick={() => setActivePanel(activePanel === "chat" ? "both" : "chat")}
          label="Chat"
          shortcut="⌘1"
        />
        <PanelButton
          active={activePanel === "workspace" || activePanel === "both"}
          onClick={() => setActivePanel(activePanel === "workspace" ? "both" : "workspace")}
          label="Canvas"
          shortcut="⌘2"
        />
        <PanelButton
          active={activePanel === "both"}
          onClick={() => setActivePanel("both")}
          label="Split"
          shortcut="⌘3"
        />
      </div>

      <ScrollArea className="flex-1">
        <div className="px-3 py-3">
          {/* Chat Sessions */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2 px-1">
              <span className="text-label text-stone-gray uppercase tracking-wider font-medium">
                Conversations
              </span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="New conversation"
                    onClick={handleNewChat}
                    disabled={createSession.isPending}
                    className="h-6 w-6 rounded-subtle border border-ring-warm bg-ivory text-near-black shadow-ring-warm hover:bg-warm-sand hover:text-near-black"
                  >
                    <Plus className="w-3.5 h-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>New conversation</TooltipContent>
              </Tooltip>
            </div>

            <div className="space-y-0.5">
              {sessions.length === 0 ? (
                <p className="text-caption text-stone-gray px-2 py-3">
                  No conversations yet. Start a new one.
                </p>
              ) : (
                sessions.map((session) => (
                  <SidebarItem
                    key={session.id}
                    active={session.id === activeSessionId}
                    icon={<MessageSquare className="w-4 h-4" />}
                    title={truncate(session.title, 28)}
                    subtitle={formatRelativeTime(new Date(session.updatedAt))}
                    onClick={() => handleSelectSession(session.id)}
                    onDelete={() => deleteSession.mutate(session.id)}
                    deleteAriaLabel={`Delete conversation: ${session.title}`}
                  />
                ))
              )}
            </div>
          </div>

          <Separator className="my-3" />

          {/* Workspaces */}
          <div>
            <div className="flex items-center justify-between mb-2 px-1">
              <span className="text-label text-stone-gray uppercase tracking-wider font-medium">
                Workspaces
              </span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="New workspace"
                    onClick={handleNewWorkspace}
                    disabled={createWorkspace.isPending}
                    className="h-6 w-6 rounded-subtle border border-ring-warm bg-ivory text-near-black shadow-ring-warm hover:bg-warm-sand hover:text-near-black"
                  >
                    <Plus className="w-3.5 h-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>New workspace</TooltipContent>
              </Tooltip>
            </div>

            <div className="space-y-0.5">
              {workspaces.length === 0 ? (
                <p className="text-caption text-stone-gray px-2 py-3">
                  No workspaces yet. Create one to compose reports.
                </p>
              ) : (
                workspaces.map((ws) => (
                  <SidebarItem
                    key={ws.id}
                    active={ws.id === activeWorkspaceId}
                    icon={<LayoutDashboard className="w-4 h-4" />}
                    title={truncate(ws.title, 28)}
                    subtitle={`${ws.nodeCount} items`}
                    onClick={() => handleSelectWorkspace(ws.id)}
                    onDelete={() => deleteWorkspace.mutate(ws.id)}
                    deleteAriaLabel={`Delete workspace: ${ws.title}`}
                  />
                ))
              )}
            </div>
          </div>
        </div>
      </ScrollArea>

      {/* Footer */}
      <div className="border-t border-border-cream px-4 py-3">
        <p className="text-label text-stone-gray">
          AI Native HR BI Platform
        </p>
      </div>
    </aside>
  );
}

function PanelButton({
  active,
  onClick,
  label,
  shortcut,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  shortcut: string;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          onClick={onClick}
          className={cn(
            "flex-1 text-center text-caption font-medium py-1 rounded-subtle transition-colors",
            active
              ? "bg-warm-sand text-near-black shadow-ring-warm"
              : "text-stone-gray hover:text-olive-gray hover:bg-border-cream"
          )}
        >
          {label}
        </button>
      </TooltipTrigger>
      <TooltipContent>{shortcut}</TooltipContent>
    </Tooltip>
  );
}

function SidebarItem({
  active,
  icon,
  title,
  subtitle,
  onClick,
  onDelete,
  deleteAriaLabel,
}: {
  active: boolean;
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  onClick: () => void;
  onDelete: () => void;
  deleteAriaLabel: string;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onClick();
      }}
      className={cn(
        "group flex items-center gap-2.5 px-2 py-2 rounded-comfortable cursor-pointer transition-colors",
        active
          ? "bg-warm-sand text-near-black shadow-ring-warm"
          : "text-olive-gray hover:bg-border-cream hover:text-near-black"
      )}
    >
      <span className={cn("shrink-0", active ? "text-terracotta" : "text-stone-gray")}>
        {icon}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-body-sm font-medium truncate">{title}</p>
        <p className="text-label text-stone-gray truncate">{subtitle}</p>
      </div>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="shrink-0 opacity-100 p-1 rounded-subtle text-stone-gray hover:bg-error-crimson/10 hover:text-error-crimson focus-visible:text-error-crimson transition-colors"
        aria-label={deleteAriaLabel}
      >
        <Trash2 className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
