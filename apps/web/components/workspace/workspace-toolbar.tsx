"use client";

import { useEffect, useState } from "react";
import { Check, Loader2, Pencil, Save, Type, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { Separator } from "@/components/ui/separator";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { useUIStore } from "@/stores/ui-store";
import { useRenameWorkspace, useSaveWorkspace } from "@/hooks/use-workspace";
import { generateId } from "@/lib/utils";
import { toast } from "sonner";
import type { TextNodeData } from "@/types/workspace";

export function WorkspaceToolbar() {
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId);
  const workspaces = useWorkspaceStore((s) => s.workspaces);
  const addNode = useWorkspaceStore((s) => s.addNode);
  const hasUnsavedChanges = useWorkspaceStore((s) => s.hasUnsavedChanges);
  const nodes = useWorkspaceStore((s) => s.nodes);
  const isSaving = useUIStore((s) => s.isSaving);
  const saveWorkspace = useSaveWorkspace();
  const renameWorkspace = useRenameWorkspace();
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");

  const workspace = workspaces.find((w) => w.id === activeWorkspaceId);

  useEffect(() => {
    setTitleDraft(workspace?.title ?? "");
    setIsEditingTitle(false);
  }, [workspace?.id, workspace?.title]);

  const handleSave = () => {
    saveWorkspace.mutate(undefined, {
      onSuccess: () => toast.success("Workspace saved"),
      onError: () => toast.error("Failed to save workspace"),
    });
  };

  const handleRename = () => {
    if (!activeWorkspaceId) return;

    const trimmedTitle = titleDraft.trim();
    if (!trimmedTitle) {
      toast.error("Workspace name cannot be empty");
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
          toast.success("Workspace renamed");
        },
        onError: () => toast.error("Failed to rename workspace"),
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
      content: "Add your annotation here…",
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
                aria-label="Workspace name"
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
                aria-label="Save workspace name"
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
                aria-label="Cancel workspace rename"
                onClick={handleCancelRename}
                disabled={renameWorkspace.isPending}
              >
                <X className="w-4 h-4" />
              </Button>
            </form>
          ) : (
            <div className="flex items-center gap-1">
              <h2 className="font-serif text-feature text-near-black">
                {workspace?.title ?? "Workspace"}
              </h2>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => setIsEditingTitle(true)}
                    aria-label="Rename workspace"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Rename workspace</TooltipContent>
              </Tooltip>
            </div>
          )}
          <p className="text-label text-stone-gray">
            {nodes.length} items
            {hasUnsavedChanges && (
              <span className="text-terracotta ml-1">• Unsaved changes</span>
            )}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={handleAddTextNode}>
              <Type className="w-4 h-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Add text block</TooltipContent>
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
              Save
            </Button>
          </TooltipTrigger>
          <TooltipContent>Save workspace (⌘S)</TooltipContent>
        </Tooltip>
      </div>
    </header>
  );
}
