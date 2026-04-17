"use client";

import { useMemo, useState } from "react";
import { Building2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/lib/i18n/context";

type WorkspaceOnboardingGateProps = {
  onCreate: (name: string) => void;
  isSubmitting: boolean;
};

export function WorkspaceOnboardingGate({ onCreate, isSubmitting }: WorkspaceOnboardingGateProps) {
  const { t } = useI18n();
  const [workspaceName, setWorkspaceName] = useState("");
  const defaultWorkspaceName = t("workspace.onboarding.defaultName");

  const normalizedName = useMemo(() => workspaceName.trim(), [workspaceName]);

  const handleCreate = () => {
    onCreate(normalizedName || defaultWorkspaceName);
  };

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-parchment px-6">
      <section className="w-full max-w-xl rounded-2xl border border-border-cream bg-ivory p-8 shadow-ring-warm">
        <div className="mb-6 flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-warm-sand text-terracotta">
            <Building2 className="h-5 w-5" />
          </span>
          <div>
            <h1 className="font-serif text-heading text-near-black">{t("workspace.onboarding.title")}</h1>
            <p className="text-body-sm text-olive-gray">
              {t("workspace.onboarding.description")}
            </p>
          </div>
        </div>

        <div className="space-y-3">
          <label htmlFor="workspace-name" className="text-label text-stone-gray">
            {t("workspace.onboarding.nameLabel")}
          </label>
          <Input
            id="workspace-name"
            value={workspaceName}
            onChange={(event) => setWorkspaceName(event.target.value)}
            placeholder={defaultWorkspaceName}
            autoFocus
          />
          <p className="text-caption text-stone-gray">
            {t("workspace.onboarding.renameHint")}
          </p>
        </div>

        <div className="mt-6 flex items-center justify-end">
          <Button onClick={handleCreate} disabled={isSubmitting}>
            {t("workspace.create")}
          </Button>
        </div>
      </section>
    </div>
  );
}
