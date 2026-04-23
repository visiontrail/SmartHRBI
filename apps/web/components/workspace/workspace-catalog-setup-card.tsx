"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n/context";
import type { IngestionCatalogSetupSeed } from "@/types/ingestion";
import type { TableCatalogEntry } from "@/types/workspace";

type WorkspaceCatalogSetupCardProps = {
  entries: TableCatalogEntry[];
  isSubmitting?: boolean;
  onAdd: (seed: IngestionCatalogSetupSeed) => void | Promise<unknown>;
};

export function WorkspaceCatalogSetupCard({
  entries: _entries,
  isSubmitting = false,
  onAdd,
}: WorkspaceCatalogSetupCardProps) {
  const { t } = useI18n();
  const [humanLabel, setHumanLabel] = useState("");
  const [description, setDescription] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const normalizedLabel = humanLabel.trim();
    const normalizedDescription = description.trim();

    if (!normalizedLabel) {
      setValidationError(t("ingestion.setup.validation.humanLabelRequired"));
      return;
    }
    if (!normalizedDescription) {
      setValidationError(t("workspace.catalog.validation.purposeRequired"));
      return;
    }

    setValidationError(null);
    await onAdd({
      businessType: "other",
      tableName: "",
      humanLabel: normalizedLabel,
      writeMode: "new_table",
      timeGrain: "none",
      primaryKeys: [],
      matchColumns: [],
      isActiveTarget: false,
      description: normalizedDescription,
    });
    setHumanLabel("");
    setDescription("");
  }

  return (
    <Card className="border-dashed bg-ivory/70" data-testid="workspace-catalog-setup-card">
      <CardHeader>
        <CardTitle>{t("workspace.catalog.setupTitle")}</CardTitle>
        <CardDescription>{t("workspace.catalog.setupDescription")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-3" onSubmit={handleSubmit}>
          <label className="block space-y-1 text-label text-stone-gray">
            <span>{t("ingestion.setup.humanLabel")}</span>
            <Input
              value={humanLabel}
              onChange={(event) => setHumanLabel(event.target.value)}
              placeholder={t("workspace.catalog.setupLabelPlaceholder")}
            />
          </label>

          <label className="block space-y-1 text-label text-stone-gray">
            <span>{t("ingestion.setup.purpose")}</span>
            <Textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
              placeholder={t("workspace.catalog.setupPurposePlaceholder")}
            />
          </label>

          <div className="rounded-comfortable border border-border-cream bg-parchment/80 px-3 py-2 text-caption text-stone-gray">
            {t("workspace.catalog.setupNote")}
          </div>

          {validationError ? <p className="text-caption text-red-600">{validationError}</p> : null}

          <Button type="submit" size="sm" disabled={isSubmitting}>
            {isSubmitting ? t("workspace.catalog.addingTable") : t("workspace.catalog.addTable")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
