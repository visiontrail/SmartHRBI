"use client";

import { useState } from "react";
import { Save, Plus, Type, Undo, Redo, ZoomIn, ZoomOut, Maximize, Loader2, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { Separator } from "@/components/ui/separator";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { useUIStore } from "@/stores/ui-store";
import { useSaveWorkspace } from "@/hooks/use-workspace";
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

  const workspace = workspaces.find((w) => w.id === activeWorkspaceId);

  const handleSave = () => {
    saveWorkspace.mutate(undefined, {
      onSuccess: () => toast.success("Workspace saved"),
      onError: () => toast.error("Failed to save workspace"),
    });
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
          <h2 className="font-serif text-feature text-near-black">
            {workspace?.title ?? "Workspace"}
          </h2>
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
