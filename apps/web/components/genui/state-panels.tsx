"use client";

import type { ReactNode } from "react";
import { useI18n } from "@/lib/i18n/context";

type PanelProps = {
  title: string;
  description: string;
  children?: ReactNode;
  testId?: string;
};

function BasePanel({ title, description, children, testId }: PanelProps) {
  return (
    <section
      className="rounded-comfortable border border-border-cream bg-ivory p-4"
      data-testid={testId}
    >
      <h3 className="text-body font-medium text-near-black mb-1">{title}</h3>
      <p className="text-caption text-olive-gray">{description}</p>
      {children}
    </section>
  );
}

export function SkeletonPanel() {
  return (
    <section
      className="rounded-comfortable border border-border-cream bg-ivory p-4 space-y-3"
      data-testid="stream-skeleton"
    >
      <div className="h-4 w-3/4 bg-warm-sand rounded animate-pulse" />
      <div className="h-4 w-full bg-warm-sand rounded animate-pulse" />
      <div className="h-4 w-1/2 bg-warm-sand rounded animate-pulse" />
    </section>
  );
}

export function EmptyPanel({ title }: { title?: string }) {
  const { t } = useI18n();
  const resolvedTitle = title ?? t("panel.noData");
  return (
    <BasePanel
      title={resolvedTitle}
      description={t("panel.noVisualization")}
      testId="chart-empty"
    />
  );
}

export function ErrorPanel({
  title,
  description,
}: {
  title?: string;
  description?: string;
}) {
  const { t } = useI18n();
  const resolvedTitle = title ?? t("panel.renderFailed");
  const resolvedDescription = description ?? t("panel.renderFailedDescription");
  return <BasePanel title={resolvedTitle} description={resolvedDescription} testId="chart-error" />;
}
