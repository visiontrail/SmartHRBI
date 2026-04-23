"use client";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useCreateWorkspaceCatalogFromSetup, useWorkspaceCatalog } from "@/hooks/use-workspace";
import { useI18n } from "@/lib/i18n/context";
import { cn } from "@/lib/utils";
import { WorkspaceCatalogSetupCard } from "./workspace-catalog-setup-card";

export function WorkspaceCatalogReadonly({
  workspaceId,
  className,
  showHeader = true,
}: {
  workspaceId: string;
  className?: string;
  showHeader?: boolean;
}) {
  const { t } = useI18n();
  const catalogQuery = useWorkspaceCatalog(workspaceId);
  const createSetupMutation = useCreateWorkspaceCatalogFromSetup();

  if (catalogQuery.isLoading) {
    return (
      <section className={cn("space-y-4", className)} data-testid="workspace-catalog-loading">
        {showHeader ? (
          <div>
            <h2 className="font-serif text-heading-sm text-near-black">
              {t("workspace.catalog.title")}
            </h2>
            <p className="text-caption text-olive-gray">{t("workspace.catalog.loadingDescription")}</p>
          </div>
        ) : null}
        <div className="space-y-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      </section>
    );
  }

  const entries = catalogQuery.data ?? [];

  return (
    <section className={cn("space-y-5", className)} data-testid="workspace-catalog-readonly">
      {showHeader ? (
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
          <div>
            <h2 className="font-serif text-heading-sm text-near-black">
              {t("workspace.catalog.title")}
            </h2>
            <p className="text-caption text-olive-gray">
              {t("workspace.catalog.description", { count: entries.length })}
            </p>
          </div>
          <Badge variant="outline">{t("workspace.catalog.entryCount", { count: entries.length })}</Badge>
        </div>
      ) : null}

      {entries.length === 0 ? (
        <div className="rounded-comfortable border border-border-cream bg-ivory px-4 py-4">
          <p className="text-caption text-stone-gray">{t("workspace.catalog.empty")}</p>
        </div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {entries.map((entry) => (
            <div
              key={entry.id}
              className="rounded-comfortable border border-border-cream bg-ivory px-4 py-3 shadow-whisper"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <p className="text-body-sm font-medium text-near-black">{entry.humanLabel}</p>
                  <p className="text-caption text-stone-gray">
                    {entry.description || t("workspace.catalog.purposeFallback")}
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap justify-end gap-2">
                  {entry.primaryKeys.length === 0 && entry.matchColumns.length === 0 ? (
                    <Badge variant="secondary">{t("workspace.catalog.planned")}</Badge>
                  ) : (
                    <Badge variant="outline">{t("workspace.catalog.aiManaged")}</Badge>
                  )}
                  {entry.isActiveTarget ? <Badge variant="default">{t("workspace.catalog.active")}</Badge> : null}
                </div>
              </div>
              <p className="pt-2 text-label text-stone-gray">{entry.tableName}</p>
            </div>
          ))}
        </div>
      )}

      <WorkspaceCatalogSetupCard
        entries={entries}
        isSubmitting={createSetupMutation.isPending}
        onAdd={(seed) => createSetupMutation.mutateAsync({ workspaceId, seed })}
      />
    </section>
  );
}
