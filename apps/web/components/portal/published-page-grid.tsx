"use client";

import { useEffect, useMemo, useState } from "react";
import { ChartPreview } from "@/components/charts/chart-preview";
import { fetchPublishedChartData, type PublishedManifest, type PublishedTextZone, type PublishedZone } from "@/lib/portal/api";
import type { ChartSpec } from "@/types/chart";
import { useI18n } from "@/lib/i18n/context";

export function PublishedPageGrid({
  pageId,
  manifest,
  activePageId,
  activeChartId,
  onSelectChart,
}: {
  pageId: string;
  manifest: PublishedManifest;
  activePageId?: string;
  activeChartId: string | null;
  onSelectChart: (chartId: string | null, title?: string) => void;
}) {
  const pageLayout =
    manifest.layout.pages?.find((page) => page.id === activePageId) ??
    manifest.layout.pages?.[0] ?? {
      id: manifest.layout.activePageId ?? "section-1",
      title: "Section 1",
      grid: manifest.layout.grid,
      zones: manifest.layout.zones,
    };
  const grid = pageLayout.grid;
  return (
    <div className="min-w-0 flex-1 overflow-auto p-5">
      <div
        className="grid bg-white"
        style={{
          gridTemplateColumns: `repeat(${grid.columns}, minmax(180px, 1fr))`,
          gridTemplateRows: grid.rows.map((row) => `${row.height}px`).join(" "),
        }}
      >
        {grid.rows.map((row, rowIndex) => (
          <div key={row.id} id={row.id} style={{ gridColumn: "1 / -1", gridRow: rowIndex + 1 }} />
        ))}
        {pageLayout.zones.map((zone) => (
          <PublishedChartZone
            key={zone.id}
            pageId={pageId}
            zone={zone}
            title={manifest.charts.find((chart) => chart.chart_id === chartIdFromZone(zone))?.title}
            selected={activeChartId === chartIdFromZone(zone)}
            onSelect={onSelectChart}
          />
        ))}
        {(pageLayout.textZones ?? []).map((zone) => (
          <PublishedTextZoneBlock key={zone.id} zone={zone} />
        ))}
      </div>
    </div>
  );
}

export function PublishedChartZone({
  pageId,
  zone,
  title,
  selected,
  onSelect,
}: {
  pageId: string;
  zone: PublishedZone;
  title?: string;
  selected: boolean;
  onSelect: (chartId: string | null, title?: string) => void;
}) {
  const { t } = useI18n();
  const chartId = chartIdFromZone(zone);
  const [spec, setSpec] = useState<ChartSpec | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!chartId) return;
    fetchPublishedChartData(pageId, chartId).then((payload) => {
      if (cancelled) return;
      setSpec(normalizeSpec(payload));
    });
    return () => {
      cancelled = true;
    };
  }, [chartId, pageId]);

  const height = useMemo(() => Math.max(180, zone.rowSpan * 260), [zone.rowSpan]);

  return (
    <button
      type="button"
      onClick={() => onSelect(chartId, title)}
      className={`relative overflow-hidden rounded-md border bg-white text-left ${
        selected ? "border-[#ad7d3d] ring-2 ring-[#e8d5b3]" : "border-[#d8d1c1]"
      }`}
      style={{
        gridColumn: `${zone.column + 1} / span ${zone.colSpan}`,
        gridRow: `${zone.row + 1} / span ${zone.rowSpan}`,
      }}
    >
      <div className="border-b border-[#eee8dc] px-3 py-2 text-sm font-semibold">
        {title || chartId}
      </div>
      {spec ? (
        <ChartPreview spec={spec} height={height} />
      ) : (
        <div className="flex h-full items-center justify-center text-sm text-[#777166]">{t("portal.loadingChart")}</div>
      )}
    </button>
  );
}

const PUBLISHED_TEXT_STYLE_MAP: Record<
  "title" | "subtitle" | "body",
  string
> = {
  title: "text-2xl font-bold leading-tight text-[#2f332f]",
  subtitle: "text-lg font-semibold leading-snug text-[#4a4842]",
  body: "text-sm leading-relaxed text-[#555250]",
};

function PublishedTextZoneBlock({ zone }: { zone: PublishedTextZone }) {
  const className = PUBLISHED_TEXT_STYLE_MAP[zone.style] ?? PUBLISHED_TEXT_STYLE_MAP.body;
  return (
    <div
      className="overflow-hidden rounded-md border border-[#c8d8f0] bg-[#f5f9ff] p-4"
      style={{
        gridColumn: `${zone.column + 1} / span ${zone.colSpan}`,
        gridRow: `${zone.row + 1} / span ${zone.rowSpan}`,
      }}
    >
      <p className={`whitespace-pre-wrap ${className}`}>{zone.content}</p>
    </div>
  );
}

function chartIdFromZone(zone: PublishedZone): string {
  return zone.chartId || zone.chart_id || "";
}

function normalizeSpec(payload: Awaited<ReturnType<typeof fetchPublishedChartData>>): ChartSpec {
  return {
    chartType: (payload.spec.chartType || payload.spec.chart_type || "bar") as ChartSpec["chartType"],
    title: payload.spec.title || payload.chart_id,
    echartsOption: {
      ...(payload.spec.echartsOption || {}),
      __rows__: payload.rows,
    },
  };
}
