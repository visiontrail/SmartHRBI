"use client";

import { ChartPreview } from "@/components/charts/chart-preview";
import type { ChartSpec } from "@/types/chart";

type LegacyGenUISpec = {
  engine?: string;
  chart_type?: string;
  title: string;
  data?: Array<Record<string, unknown>>;
  config?: Record<string, unknown>;
};

export function ChartRenderer({ spec }: { spec: LegacyGenUISpec }) {
  const mapped = mapLegacySpec(spec);
  if (!mapped) {
    return (
      <div className="p-4 text-center text-stone-gray">
        <p>Unsupported chart spec format</p>
      </div>
    );
  }

  return (
    <div className="rounded-comfortable overflow-hidden">
      <ChartPreview spec={mapped} height={320} />
    </div>
  );
}

function mapLegacySpec(spec: LegacyGenUISpec): ChartSpec | null {
  if (spec.engine === "echarts" && spec.config && "option" in spec.config) {
    return {
      chartType: (spec.chart_type as ChartSpec["chartType"]) ?? "bar",
      title: spec.title,
      echartsOption: spec.config.option as Record<string, unknown>,
    };
  }
  return null;
}
