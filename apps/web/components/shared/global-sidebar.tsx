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
import { useUIStore } from "@/stores/ui-store";
import { useCreateSession, useDeleteSession } from "@/hooks/use-chat";
import { useCreateWorkspace, useDeleteWorkspace } from "@/hooks/use-workspace";
import { useI18n } from "@/lib/i18n/context";
import type { Locale } from "@/lib/i18n/dictionary";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/utils";

export function GlobalSidebar() {
  const { t, locale, setLocale } = useI18n();
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
    createWorkspace.mutate({ title: t("workspace.defaultUntitled") });
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
          <TooltipContent>{t("sidebar.hideSidebar")}</TooltipContent>
        </Tooltip>
      </div>

      <ScrollArea className="flex-1">
        <div className="pl-3 pr-5 py-3">
          {/* Chat Sessions */}
          <div className="mb-4">
            <div className="sticky top-0 z-10 bg-ivory flex items-center justify-between mb-2 px-1 py-0.5">
              <span className="text-label text-stone-gray uppercase tracking-wider font-medium">
                {t("sidebar.section.conversations")}
              </span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("sidebar.action.newConversation")}
                    onClick={handleNewChat}
                    disabled={createSession.isPending}
                    className="h-6 w-6 rounded-subtle border border-ring-warm bg-ivory text-near-black shadow-ring-warm hover:bg-warm-sand hover:text-near-black"
                  >
                    <Plus className="w-3.5 h-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{t("sidebar.action.newConversation")}</TooltipContent>
              </Tooltip>
            </div>

            <div className="space-y-0.5">
              {sessions.length === 0 ? (
                <p className="text-caption text-stone-gray px-2 py-3">
                  {t("sidebar.emptyConversations")}
                </p>
              ) : (
                sessions.map((session) => (
                  <SidebarItem
                    key={session.id}
                    active={session.id === activeSessionId}
                    icon={<MessageSquare className="w-4 h-4" />}
                    title={session.title}
                    subtitle={formatRelativeTime(new Date(session.updatedAt), locale)}
                    onClick={() => handleSelectSession(session.id)}
                    onDelete={() => deleteSession.mutate(session.id)}
                    deleteAriaLabel={t("sidebar.deleteConversation", { title: session.title })}
                  />
                ))
              )}
            </div>
          </div>

          <Separator className="my-3" />

          {/* Workspaces */}
          <div>
            <div className="sticky top-0 z-10 bg-ivory flex items-center justify-between mb-2 px-1 py-0.5">
              <span className="text-label text-stone-gray uppercase tracking-wider font-medium">
                {t("sidebar.section.workspaces")}
              </span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("sidebar.action.newWorkspace")}
                    onClick={handleNewWorkspace}
                    disabled={createWorkspace.isPending}
                    className="h-6 w-6 rounded-subtle border border-ring-warm bg-ivory text-near-black shadow-ring-warm hover:bg-warm-sand hover:text-near-black"
                  >
                    <Plus className="w-3.5 h-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{t("sidebar.action.newWorkspace")}</TooltipContent>
              </Tooltip>
            </div>

            <div className="space-y-0.5">
              {workspaces.length === 0 ? (
                <p className="text-caption text-stone-gray px-2 py-3">
                  {t("sidebar.emptyWorkspaces")}
                </p>
              ) : (
                workspaces.map((ws) => (
                  <SidebarItem
                    key={ws.id}
                    active={ws.id === activeWorkspaceId}
                    icon={<LayoutDashboard className="w-4 h-4" />}
                    title={ws.title}
                    subtitle={t("sidebar.itemCount", { count: ws.nodeCount })}
                    onClick={() => handleSelectWorkspace(ws.id)}
                    onDelete={() => deleteWorkspace.mutate(ws.id)}
                    deleteAriaLabel={t("sidebar.deleteWorkspace", { title: ws.title })}
                  />
                ))
              )}
            </div>
          </div>
        </div>
      </ScrollArea>

      {/* Footer */}
      <div className="border-t border-border-cream px-4 py-3">
        <p className="text-label text-stone-gray">{t("sidebar.footerTagline")}</p>
        <div className="mt-2 flex items-center justify-between gap-2">
          <span className="text-label text-stone-gray">{t("language.label")}</span>
          <div className="inline-flex items-center gap-1 rounded-subtle border border-border-cream bg-parchment p-1">
            <LanguageButton
              locale="en-US"
              active={locale === "en-US"}
              onClick={setLocale}
              label={t("language.en")}
            />
            <LanguageButton
              locale="zh-CN"
              active={locale === "zh-CN"}
              onClick={setLocale}
              label={t("language.zh")}
            />
          </div>
        </div>
      </div>
    </aside>
  );
}

function LanguageButton({
  locale,
  active,
  onClick,
  label,
}: {
  locale: Locale;
  active: boolean;
  onClick: (locale: Locale) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={() => onClick(locale)}
      className={cn(
        "rounded-subtle px-2 py-1 text-label font-medium transition-colors",
        active ? "bg-warm-sand text-near-black" : "text-stone-gray hover:bg-border-cream"
      )}
    >
      {label}
    </button>
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
        "group grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2.5 px-2 py-2 rounded-comfortable cursor-pointer transition-colors overflow-hidden",
        active
          ? "bg-warm-sand text-near-black shadow-ring-warm"
          : "text-olive-gray hover:bg-border-cream hover:text-near-black"
      )}
    >
      <span className={cn("shrink-0", active ? "text-terracotta" : "text-stone-gray")}>
        {icon}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-body-sm font-medium truncate" title={title}>
          {title}
        </p>
        <p className="text-label text-stone-gray truncate" title={subtitle}>
          {subtitle}
        </p>
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
