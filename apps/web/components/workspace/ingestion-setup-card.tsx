"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n/context";
import type { IngestionCatalogSetupSeed, IngestionSetupQuestion } from "@/types/ingestion";

type IngestionSetupCardProps = {
  initialSeed: IngestionCatalogSetupSeed;
  setupQuestions?: IngestionSetupQuestion[];
  isSubmitting?: boolean;
  onConfirm: (seed: IngestionCatalogSetupSeed) => void | Promise<void>;
  onCancel?: () => void;
};

export function IngestionSetupCard({
  initialSeed,
  setupQuestions: _setupQuestions,
  isSubmitting = false,
  onConfirm,
  onCancel,
}: IngestionSetupCardProps) {
  const { t } = useI18n();
  const [seed, setSeed] = useState<IngestionCatalogSetupSeed>(initialSeed);
  const [validationError, setValidationError] = useState<string | null>(null);

  function normalizeTableName(raw: string, humanLabel: string): string {
    const source = raw.trim() || humanLabel.trim();
    const normalized = source
      .toLowerCase()
      .replace(/[^a-z0-9_]+/g, "_")
      .replace(/^_+|_+$/g, "");

    if (!normalized) {
      return "workspace_table";
    }
    if (/^[0-9]/.test(normalized)) {
      return `t_${normalized}`;
    }
    return normalized;
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const humanLabel = seed.humanLabel.trim();
    if (!humanLabel) {
      setValidationError(t("ingestion.setup.validation.humanLabelRequired"));
      return;
    }

    setValidationError(null);
    onConfirm({
      ...seed,
      tableName: normalizeTableName(seed.tableName, humanLabel),
      humanLabel,
      description: seed.description.trim(),
    });
  }

  return (
    <Card
      className="flex max-h-[calc(100dvh-14rem)] flex-col overflow-hidden"
      data-testid="ingestion-setup-card"
    >
      <CardHeader>
        <CardTitle>{t("ingestion.setup.title")}</CardTitle>
        <CardDescription>{t("ingestion.setup.description")}</CardDescription>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-y-auto pr-2 scrollbar-thin">
        <form className="space-y-3 pb-1" onSubmit={handleSubmit}>
          <label className="block space-y-1 text-label text-stone-gray">
            <span>{t("ingestion.setup.humanLabel")}</span>
            <Textarea
              value={seed.humanLabel}
              onChange={(event) => setSeed((previous) => ({ ...previous, humanLabel: event.target.value }))}
              rows={2}
              placeholder={t("ingestion.setup.humanLabelPlaceholder")}
            />
          </label>

          <label className="block space-y-1 text-label text-stone-gray">
            <span>{t("ingestion.setup.purpose")}</span>
            <Textarea
              value={seed.description}
              onChange={(event) => setSeed((previous) => ({ ...previous, description: event.target.value }))}
              rows={4}
              placeholder={t("ingestion.setup.purposePlaceholder")}
            />
          </label>

          <div className="rounded-comfortable border border-border-cream bg-parchment/80 px-3 py-2 text-caption text-stone-gray">
            {t("ingestion.setup.autoSchemaNote")}
          </div>

          {validationError ? (
            <p className="text-caption text-red-600" role="alert">
              {validationError}
            </p>
          ) : null}

          <div className="flex items-center gap-2 pt-1">
            <Button type="submit" size="sm" disabled={isSubmitting}>
              {isSubmitting ? t("ingestion.setup.applying") : t("ingestion.setup.apply")}
            </Button>
            {onCancel ? (
              <Button type="button" variant="ghost" size="sm" onClick={onCancel} disabled={isSubmitting}>
                {t("ingestion.setup.cancel")}
              </Button>
            ) : null}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
