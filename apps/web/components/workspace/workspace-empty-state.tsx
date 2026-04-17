"use client";

import { LayoutDashboard, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCreateWorkspace } from "@/hooks/use-workspace";
import { useI18n } from "@/lib/i18n/context";

export function WorkspaceEmptyState() {
  const { t } = useI18n();
  const createWorkspace = useCreateWorkspace();

  return (
    <div className="flex flex-col items-center justify-center h-full px-8 py-12">
      <div className="w-14 h-14 rounded-maximum bg-warm-sand flex items-center justify-center mb-6">
        <LayoutDashboard className="w-7 h-7 text-terracotta" />
      </div>

      <h2 className="font-serif text-heading text-near-black mb-2 text-center">
        {t("workspace.emptyTitle")}
      </h2>
      <p className="text-body text-olive-gray text-center max-w-md mb-8 leading-relaxed">
        {t("workspace.emptyDescription")}
      </p>

      <Button
        variant="default"
        onClick={() => createWorkspace.mutate({ title: t("workspace.defaultUntitled") })}
        disabled={createWorkspace.isPending}
      >
        <Plus className="w-4 h-4" />
        {t("workspace.create")}
      </Button>
    </div>
  );
}
