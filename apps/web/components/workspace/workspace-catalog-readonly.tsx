"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspaceCatalog } from "@/hooks/use-workspace";

export function WorkspaceCatalogReadonly({ workspaceId }: { workspaceId: string }) {
  const catalogQuery = useWorkspaceCatalog(workspaceId);

  if (catalogQuery.isLoading) {
    return (
      <div className="px-3 pt-3 pb-2" data-testid="workspace-catalog-loading">
        <Card>
          <CardHeader>
            <CardTitle>Workspace Table Catalog</CardTitle>
            <CardDescription>Loading table targets for this workspace...</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </CardContent>
        </Card>
      </div>
    );
  }

  const entries = catalogQuery.data ?? [];

  return (
    <div className="px-3 pt-3 pb-2" data-testid="workspace-catalog-readonly">
      <Card>
        <CardHeader>
          <CardTitle>Workspace Table Catalog</CardTitle>
          <CardDescription>
            Current writable targets used by ingestion planning ({entries.length})
          </CardDescription>
        </CardHeader>
        <CardContent>
          {entries.length === 0 ? (
            <p className="text-caption text-stone-gray">No catalog entries yet. Complete setup to add one.</p>
          ) : (
            <div className="space-y-2">
              {entries.map((entry) => (
                <div
                  key={entry.id}
                  className="rounded-comfortable border border-border-cream bg-parchment/70 px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-body-sm font-medium text-near-black">{entry.humanLabel}</p>
                    {entry.isActiveTarget ? <Badge variant="default">Active</Badge> : null}
                  </div>
                  <p className="text-label text-stone-gray">
                    {entry.tableName} · {entry.businessType} · {entry.writeMode}
                  </p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
