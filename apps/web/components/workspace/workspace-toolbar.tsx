"use client";

import { useEffect, useState } from "react";
import { Check, Loader2, MessageSquare, Pencil, Save, Type, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { Separator } from "@/components/ui/separator";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { useUIStore } from "@/stores/ui-store";
import { useRenameWorkspace, useSaveWorkspace } from "@/hooks/use-workspace";
import { generateId } from "@/lib/utils";
import { useI18n } from "@/lib/i18n/context";
import { toast } from "sonner";
import type { TextNodeData } from "@/types/workspace";

export function WorkspaceToolbar() {
  const { t } = useI18n();
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId);
  const workspaces = useWorkspaceStore((s) => s.workspaces);
  const addNode = useWorkspaceStore((s) => s.addNode);
  const hasUnsavedChanges = useWorkspaceStore((s) => s.hasUnsavedChanges);
  const nodes = useWorkspaceStore((s) => s.nodes);
  const activePanel = useUIStore((s) => s.activePanel);
  const isSaving = useUIStore((s) => s.isSaving);
  const setActivePanel = useUIStore((s) => s.setActivePanel);
  const saveWorkspace = useSaveWorkspace();
  const renameWorkspace = useRenameWorkspace();
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const isChatVisible = activePanel === "both";

  const workspace = workspaces.find((w) => w.id === activeWorkspaceId);

  useEffect(() => {
    setTitleDraft(workspace?.title ?? "");
    setIsEditingTitle(false);
  }, [workspace?.id, workspace?.title]);

  const handleSave = () => {
    saveWorkspace.mutate(undefined, {
      onSuccess: () => toast.success(t("workspace.toast.saved")),
      onError: () => toast.error(t("workspace.toast.saveFailed")),
    });
  };

  const handleRename = () => {
    if (!activeWorkspaceId) return;

    const trimmedTitle = titleDraft.trim();
    if (!trimmedTitle) {
      toast.error(t("workspace.toast.nameEmpty"));
      return;
    }

    if (trimmedTitle === workspace?.title) {
      setIsEditingTitle(false);
      return;
    }

    renameWorkspace.mutate(
      { workspaceId: activeWorkspaceId, title: trimmedTitle },
      {
        onSuccess: () => {
          setIsEditingTitle(false);
          toast.success(t("workspace.toast.renamed"));
        },
        onError: () => toast.error(t("workspace.toast.renameFailed")),
      }
    );
  };

  const handleCancelRename = () => {
    setTitleDraft(workspace?.title ?? "");
    setIsEditingTitle(false);
  };

  const handleAddTextNode = () => {
    const nodeData: TextNodeData = {
      type: "text",
      content: t("workspace.defaultTextContent"),
      width: 400,
      height: 80,
    };

    addNode({
      id: `node-${generateId()}`,
      type: "textNode",
      position: { x: 50 + (nodes.length % 4) * 200, y: 50 + Math.floor(nodes.length / 4) * 120 },
      data: nodeData,
    });
  };

  return (
    <header className="flex items-center justify-between px-4 py-2 border-b border-border-cream bg-ivory shrink-0">
      <div className="flex items-center gap-3">
        <div>
          {isEditingTitle ? (
            <form
              className="flex items-center gap-1"
              onSubmit={(event) => {
                event.preventDefault();
                handleRename();
              }}
            >
              <Input
                aria-label={t("workspace.aria.workspaceName")}
                value={titleDraft}
                onChange={(event) => setTitleDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") handleCancelRename();
                }}
                className="h-8 w-64 max-w-[42vw] bg-parchment font-serif text-feature"
                autoFocus
                disabled={renameWorkspace.isPending}
              />
              <Button
                type="submit"
                variant="ghost"
                size="icon-sm"
                aria-label={t("workspace.aria.saveWorkspaceName")}
                disabled={renameWorkspace.isPending}
              >
                {renameWorkspace.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Check className="w-4 h-4" />
                )}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t("workspace.aria.cancelWorkspaceRename")}
                onClick={handleCancelRename}
                disabled={renameWorkspace.isPending}
              >
                <X className="w-4 h-4" />
              </Button>
            </form>
          ) : (
            <div className="flex items-center gap-1">
              <h2 className="font-serif text-feature text-near-black">
                {workspace?.title ?? t("workspace.fallbackTitle")}
              </h2>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => setIsEditingTitle(true)}
                    aria-label={t("workspace.rename")}
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{t("workspace.rename")}</TooltipContent>
              </Tooltip>
            </div>
          )}
          <p className="text-label text-stone-gray">
            {t("sidebar.itemCount", { count: nodes.length })}
            {hasUnsavedChanges && (
              <span className="text-terracotta ml-1">• {t("workspace.unsavedChanges")}</span>
            )}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setActivePanel(isChatVisible ? "workspace" : "both")}
        >
          <MessageSquare className="w-4 h-4" />
          {isChatVisible ? t("workspace.hideChat") : t("workspace.showChat")}
        </Button>

        <Separator orientation="vertical" className="h-6 mx-1" />

        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={handleAddTextNode}>
              <Type className="w-4 h-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t("workspace.addTextBlock")}</TooltipContent>
        </Tooltip>

        <Separator orientation="vertical" className="h-6 mx-1" />

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant={hasUnsavedChanges ? "default" : "secondary"}
              size="sm"
              onClick={handleSave}
              disabled={isSaving || !hasUnsavedChanges}
            >
              {isSaving ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Save className="w-4 h-4" />
              )}
              {t("workspace.save")}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t("workspace.saveShortcut")}</TooltipContent>
        </Tooltip>
      </div>
    </header>
  );
}
