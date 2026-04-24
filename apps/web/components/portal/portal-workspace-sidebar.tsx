"use client";

import { LayoutDashboard } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PortalWorkspace } from "@/lib/portal/api";

export function PortalWorkspaceSidebar({
  workspaces,
  activePageId,
  onSelect,
}: {
  workspaces: PortalWorkspace[];
  activePageId: string | null;
  onSelect: (pageId: string) => void;
}) {
  return (
    <aside className="h-full w-72 shrink-0 overflow-auto border-r border-[#d8d1c1] bg-[#fbfaf5] p-3">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#2f332f]">
        <LayoutDashboard className="h-4 w-4 text-[#996b35]" />
        Published workspaces
      </div>
      {workspaces.length === 0 ? (
        <p className="rounded-md border border-[#d8d1c1] bg-white p-3 text-sm text-[#777166]">
          No published workspaces yet. Publish a workspace from the designer.
        </p>
      ) : (
        <div className="space-y-2">
          {workspaces.map((workspace) => (
            <button
              key={workspace.latest_page_id}
              onClick={() => onSelect(workspace.latest_page_id)}
              className={cn(
                "w-full rounded-md border bg-white p-3 text-left shadow-sm transition hover:border-[#ad7d3d]",
                activePageId === workspace.latest_page_id
                  ? "border-[#ad7d3d] ring-2 ring-[#e8d5b3]"
                  : "border-[#d8d1c1]"
              )}
            >
              <span className="block truncate text-sm font-semibold">{workspace.name}</span>
              <span className="mt-1 block text-xs text-[#777166]">
                v{workspace.latest_version} · {new Date(workspace.published_at).toLocaleString()}
              </span>
            </button>
          ))}
        </div>
      )}
    </aside>
  );
}
