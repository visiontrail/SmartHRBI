"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCreateWorkspaceCatalogFromSetup, useWorkspaceCatalog } from "@/hooks/use-workspace";
import { useI18n } from "@/lib/i18n/context";
import { WorkspaceCatalogSetupCard } from "./workspace-catalog-setup-card";

export function WorkspaceCatalogReadonly({ workspaceId }: { workspaceId: string }) {
  const { t } = useI18n();
  const catalogQuery = useWorkspaceCatalog(workspaceId);
  const createSetupMutation = useCreateWorkspaceCatalogFromSetup();

  if (catalogQuery.isLoading) {
    return (
      <div className="px-3 pt-3 pb-2" data-testid="workspace-catalog-loading">
        <Card>
          <CardHeader>
            <CardTitle>{t("workspace.catalog.title")}</CardTitle>
            <CardDescription>{t("workspace.catalog.loadingDescription")}</CardDescription>
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
          <CardTitle>{t("workspace.catalog.title")}</CardTitle>
          <CardDescription>
            {t("workspace.catalog.description", { count: entries.length })}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {entries.length === 0 ? (
            <p className="text-caption text-stone-gray">{t("workspace.catalog.empty")}</p>
          ) : (
            <div className="space-y-2">
              {entries.map((entry) => (
                <div
                  key={entry.id}
                  className="rounded-comfortable border border-border-cream bg-parchment/70 px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="space-y-1">
                      <p className="text-body-sm font-medium text-near-black">{entry.humanLabel}</p>
                      <p className="text-caption text-stone-gray">
                        {entry.description || t("workspace.catalog.purposeFallback")}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {entry.primaryKeys.length === 0 && entry.matchColumns.length === 0 ? (
                        <Badge variant="secondary">{t("workspace.catalog.planned")}</Badge>
                      ) : (
                        <Badge variant="outline">{t("workspace.catalog.aiManaged")}</Badge>
                      )}
                      {entry.isActiveTarget ? <Badge variant="default">{t("workspace.catalog.active")}</Badge> : null}
                    </div>
                  </div>
                  <p className="pt-1 text-label text-stone-gray">{entry.tableName}</p>
                </div>
              ))}
            </div>
          )}

          <WorkspaceCatalogSetupCard
            entries={entries}
            isSubmitting={createSetupMutation.isPending}
            onAdd={(seed) => createSetupMutation.mutateAsync({ workspaceId, seed })}
          />
        </CardContent>
      </Card>
    </div>
  );
}
