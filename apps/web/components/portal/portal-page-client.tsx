"use client";

import { useEffect, useState } from "react";
import { PortalChatWindow } from "@/components/portal/portal-chat-window";
import { PortalWorkspaceSidebar } from "@/components/portal/portal-workspace-sidebar";
import { PublishedPageGrid } from "@/components/portal/published-page-grid";
import { PublishedPageSidebar } from "@/components/portal/published-page-sidebar";
import {
  fetchPortalManifest,
  fetchPortalWorkspaces,
  type PortalManifestResponse,
  type PortalWorkspace,
} from "@/lib/portal/api";

export function PortalPageClient({ initialPageId }: { initialPageId?: string }) {
  const [workspaces, setWorkspaces] = useState<PortalWorkspace[]>([]);
  const [pageId, setPageId] = useState<string | null>(initialPageId || null);
  const [page, setPage] = useState<PortalManifestResponse | null>(null);
  const [activeChartId, setActiveChartId] = useState<string | null>(null);
  const [activeChartTitle, setActiveChartTitle] = useState<string | undefined>();

  useEffect(() => {
    fetchPortalWorkspaces().then((items) => {
      setWorkspaces(items);
      if (!pageId && items[0]) setPageId(items[0].latest_page_id);
    });
  }, [pageId]);

  useEffect(() => {
    if (!pageId) return;
    fetchPortalManifest(pageId).then((payload) => {
      setPage(payload);
      setActiveChartId(null);
      setActiveChartTitle(undefined);
    });
  }, [pageId]);

  return (
    <div className="flex h-screen overflow-hidden bg-[#f7f4eb] text-[#2f332f]">
      <PortalWorkspaceSidebar workspaces={workspaces} activePageId={pageId} onSelect={setPageId} />
      <main className="relative flex min-w-0 flex-1">
        {!page ? (
          <div className="flex flex-1 items-center justify-center text-sm text-[#777166]">
            Select a published workspace.
          </div>
        ) : (
          <>
            <PublishedPageSidebar items={page.manifest.sidebar || []} />
            <PublishedPageGrid
              pageId={page.page_id}
              manifest={page.manifest}
              activeChartId={activeChartId}
              onSelectChart={(chartId, title) => {
                setActiveChartId(chartId);
                setActiveChartTitle(title);
              }}
            />
            <PortalChatWindow
              pageId={page.page_id}
              activeChartId={activeChartId}
              activeChartTitle={activeChartTitle}
              onClearChart={() => {
                setActiveChartId(null);
                setActiveChartTitle(undefined);
              }}
            />
          </>
        )}
      </main>
    </div>
  );
}
