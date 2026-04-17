"use client";

import { FormEvent, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n/context";
import type {
  IngestionBusinessType,
  IngestionCatalogSetupSeed,
  IngestionSetupQuestion,
  IngestionTimeGrain,
  IngestionWriteMode,
} from "@/types/ingestion";

type IngestionSetupCardProps = {
  initialSeed: IngestionCatalogSetupSeed;
  setupQuestions?: IngestionSetupQuestion[];
  isSubmitting?: boolean;
  onConfirm: (seed: IngestionCatalogSetupSeed) => void | Promise<void>;
  onCancel?: () => void;
};

const FALLBACK_BUSINESS_TYPES: IngestionBusinessType[] = ["roster", "project_progress", "attendance", "other"];
const FALLBACK_WRITE_MODES: IngestionWriteMode[] = ["update_existing", "time_partitioned_new_table", "new_table"];
const FALLBACK_TIME_GRAINS: IngestionTimeGrain[] = ["none", "month", "quarter", "year"];
const BUSINESS_TYPE_LABEL_KEYS: Record<IngestionBusinessType, string> = {
  roster: "ingestion.setup.option.businessType.roster",
  project_progress: "ingestion.setup.option.businessType.projectProgress",
  attendance: "ingestion.setup.option.businessType.attendance",
  other: "ingestion.setup.option.businessType.other",
};
const WRITE_MODE_LABEL_KEYS: Record<IngestionWriteMode, string> = {
  update_existing: "ingestion.setup.option.writeMode.updateExisting",
  time_partitioned_new_table: "ingestion.setup.option.writeMode.timePartitionedNewTable",
  new_table: "ingestion.setup.option.writeMode.newTable",
};
const TIME_GRAIN_LABEL_KEYS: Record<IngestionTimeGrain, string> = {
  none: "ingestion.setup.option.timeGrain.none",
  month: "ingestion.setup.option.timeGrain.month",
  quarter: "ingestion.setup.option.timeGrain.quarter",
  year: "ingestion.setup.option.timeGrain.year",
};

export function IngestionSetupCard({
  initialSeed,
  setupQuestions,
  isSubmitting = false,
  onConfirm,
  onCancel,
}: IngestionSetupCardProps) {
  const { t } = useI18n();
  const [seed, setSeed] = useState<IngestionCatalogSetupSeed>(initialSeed);
  const [validationError, setValidationError] = useState<string | null>(null);

  const businessTypeOptions = useMemo(() => {
    const configured = setupQuestions?.find((item) => item.questionId === "business_type")?.options ?? [];
    const resolved = configured.filter(Boolean) as IngestionBusinessType[];
    return resolved.length > 0 ? resolved : FALLBACK_BUSINESS_TYPES;
  }, [setupQuestions]);

  const writeModeOptions = useMemo(() => {
    const configured = setupQuestions?.find((item) => item.questionId === "write_mode")?.options ?? [];
    const resolved = configured.filter(Boolean) as IngestionWriteMode[];
    return resolved.length > 0 ? resolved : FALLBACK_WRITE_MODES;
  }, [setupQuestions]);

  function resolveOptionLabel(
    option: string,
    labelKeyMap: Partial<Record<string, string>>
  ): string {
    const key = labelKeyMap[option];
    return key ? t(key) : option;
  }

  function parseColumns(raw: string): string[] {
    return Array.from(
      new Set(
        raw
          .split(",")
          .map((item) => item.trim().toLowerCase())
          .filter(Boolean)
      )
    );
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const tableName = seed.tableName.trim().toLowerCase();
    const humanLabel = seed.humanLabel.trim();
    const primaryKeys = parseColumns(seed.primaryKeys.join(","));
    const matchColumns = parseColumns(seed.matchColumns.join(","));

    if (!tableName) {
      setValidationError(t("ingestion.setup.validation.tableNameRequired"));
      return;
    }
    if (!humanLabel) {
      setValidationError(t("ingestion.setup.validation.humanLabelRequired"));
      return;
    }
    if (primaryKeys.length === 0 && matchColumns.length === 0) {
      setValidationError(t("ingestion.setup.validation.keyRequired"));
      return;
    }

    setValidationError(null);
    onConfirm({
      ...seed,
      tableName,
      humanLabel,
      primaryKeys: primaryKeys.length > 0 ? primaryKeys : matchColumns,
      matchColumns: matchColumns.length > 0 ? matchColumns : primaryKeys,
      description: seed.description.trim(),
    });
  }

  return (
    <Card data-testid="ingestion-setup-card">
      <CardHeader>
        <CardTitle>{t("ingestion.setup.title")}</CardTitle>
        <CardDescription>
          {t("ingestion.setup.description")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-3" onSubmit={handleSubmit}>
          <label className="block space-y-1 text-label text-stone-gray">
            <span>{t("ingestion.setup.businessType")}</span>
            <select
              className="h-9 w-full rounded-comfortable border border-border-cream bg-ivory px-2 text-body-sm text-near-black"
              value={seed.businessType}
              onChange={(event) =>
                setSeed((previous) => ({
                  ...previous,
                  businessType: event.target.value as IngestionBusinessType,
                }))
              }
            >
              {businessTypeOptions.map((option) => (
                <option key={option} value={option}>
                  {resolveOptionLabel(option, BUSINESS_TYPE_LABEL_KEYS)}
                </option>
              ))}
            </select>
          </label>

          <label className="block space-y-1 text-label text-stone-gray">
            <span>{t("ingestion.setup.tableName")}</span>
            <Input
              value={seed.tableName}
              onChange={(event) => setSeed((previous) => ({ ...previous, tableName: event.target.value }))}
              placeholder="employee_roster"
            />
          </label>

          <label className="block space-y-1 text-label text-stone-gray">
            <span>{t("ingestion.setup.humanLabel")}</span>
            <Input
              value={seed.humanLabel}
              onChange={(event) => setSeed((previous) => ({ ...previous, humanLabel: event.target.value }))}
              placeholder="Employee Roster"
            />
          </label>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <label className="block space-y-1 text-label text-stone-gray">
              <span>{t("ingestion.setup.writeMode")}</span>
              <select
                className="h-9 w-full rounded-comfortable border border-border-cream bg-ivory px-2 text-body-sm text-near-black"
                value={seed.writeMode}
                onChange={(event) =>
                  setSeed((previous) => ({
                    ...previous,
                    writeMode: event.target.value as IngestionWriteMode,
                  }))
                }
              >
                {writeModeOptions.map((option) => (
                  <option key={option} value={option}>
                    {resolveOptionLabel(option, WRITE_MODE_LABEL_KEYS)}
                  </option>
                ))}
              </select>
            </label>

            <label className="block space-y-1 text-label text-stone-gray">
              <span>{t("ingestion.setup.timeGrain")}</span>
              <select
                className="h-9 w-full rounded-comfortable border border-border-cream bg-ivory px-2 text-body-sm text-near-black"
                value={seed.timeGrain}
                onChange={(event) =>
                  setSeed((previous) => ({
                    ...previous,
                    timeGrain: event.target.value as IngestionTimeGrain,
                  }))
                }
              >
                {FALLBACK_TIME_GRAINS.map((option) => (
                  <option key={option} value={option}>
                    {resolveOptionLabel(option, TIME_GRAIN_LABEL_KEYS)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="block space-y-1 text-label text-stone-gray">
            <span>{t("ingestion.setup.primaryKeys")}</span>
            <Input
              value={seed.primaryKeys.join(", ")}
              onChange={(event) =>
                setSeed((previous) => ({
                  ...previous,
                  primaryKeys: parseColumns(event.target.value),
                }))
              }
              placeholder="employee_id"
            />
          </label>

          <label className="block space-y-1 text-label text-stone-gray">
            <span>{t("ingestion.setup.matchColumns")}</span>
            <Input
              value={seed.matchColumns.join(", ")}
              onChange={(event) =>
                setSeed((previous) => ({
                  ...previous,
                  matchColumns: parseColumns(event.target.value),
                }))
              }
              placeholder="employee_id"
            />
          </label>

          <label className="block space-y-1 text-label text-stone-gray">
            <span>{t("ingestion.setup.descriptionField")}</span>
            <Textarea
              value={seed.description}
              onChange={(event) => setSeed((previous) => ({ ...previous, description: event.target.value }))}
              rows={3}
              placeholder={t("ingestion.setup.optionalNote")}
            />
          </label>

          {validationError ? (
            <p className="text-caption text-red-600" role="alert">
              {validationError}
            </p>
          ) : null}

          <div className="flex items-center gap-2">
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
