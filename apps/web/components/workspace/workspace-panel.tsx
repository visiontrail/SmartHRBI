"use client";

import { useWorkspaceStore } from "@/stores/workspace-store";
import { useWorkspaceSnapshot, useSaveWorkspace } from "@/hooks/use-workspace";
import { WorkspaceCanvas } from "./workspace-canvas";
import { WorkspaceCatalogReadonly } from "./workspace-catalog-readonly";
import { WorkspaceEmptyState } from "./workspace-empty-state";
import { WorkspaceToolbar } from "./workspace-toolbar";
import { Skeleton } from "@/components/ui/skeleton";

export function WorkspacePanel() {
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId);
  const { isLoading } = useWorkspaceSnapshot(activeWorkspaceId);

  if (!activeWorkspaceId) {
    return <WorkspaceEmptyState />;
  }

  if (isLoading) {
    return (
      <div className="flex flex-col h-full">
        <div className="border-b border-border-cream p-3">
          <Skeleton className="h-8 w-48" />
        </div>
        <div className="flex-1 p-6">
          <Skeleton className="h-full w-full rounded-very" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <WorkspaceToolbar />
      <WorkspaceCatalogReadonly workspaceId={activeWorkspaceId} />
      <div className="flex-1 overflow-hidden">
        <WorkspaceCanvas />
      </div>
    </div>
  );
}
