"use client";

import { useRef, useEffect, useMemo } from "react";
import * as echarts from "echarts";
import type { ChartSpec } from "@/types/chart";
import { validateChartSpec } from "@/types/chart";

type ChartPreviewProps = {
  spec: ChartSpec;
  height?: number;
  className?: string;
};

const WARM_THEME = {
  backgroundColor: "transparent",
  textStyle: { fontFamily: "Inter, system-ui, sans-serif", color: "#4d4c48" },
};

export function ChartPreview({ spec, height = 320, className }: ChartPreviewProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<echarts.ECharts | null>(null);

  const validation = useMemo(() => validateChartSpec(spec), [spec]);

  const option = useMemo(() => {
    if (!validation.valid) return null;
    return {
      ...WARM_THEME,
      ...spec.echartsOption,
      animation: true,
      animationDuration: 600,
      animationEasing: "cubicInOut" as const,
    };
  }, [spec.echartsOption, validation.valid]);

  useEffect(() => {
    if (!chartRef.current || !option) return;

    const instance = echarts.init(chartRef.current, undefined, { renderer: "canvas" });
    instanceRef.current = instance;

    try {
      instance.setOption(option);
    } catch {
      instance.dispose();
      instanceRef.current = null;
      return;
    }

    const observer = new ResizeObserver(() => {
      instance.resize();
    });
    observer.observe(chartRef.current);

    return () => {
      observer.disconnect();
      instance.dispose();
      instanceRef.current = null;
    };
  }, [option]);

  if (!validation.valid) {
    return (
      <div
        className="flex items-center justify-center bg-warm-sand rounded-comfortable"
        style={{ height }}
      >
        <div className="text-center px-4">
          <p className="text-body-sm text-error-crimson font-medium">Chart rendering failed</p>
          <p className="text-caption text-stone-gray mt-1">
            {validation.errors[0] ?? "Invalid chart configuration"}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={chartRef}
      className={className}
      style={{ width: "100%", height }}
    />
  );
}
