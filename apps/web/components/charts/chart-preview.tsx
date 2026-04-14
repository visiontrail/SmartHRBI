"use client";

import { useRef, useEffect, useMemo, useState } from "react";
import * as echarts from "echarts";
import type { ChartSpec } from "@/types/chart";
import { validateChartSpec } from "@/types/chart";
import { ensureChinaMap, normaliseProvinceName } from "@/lib/genui/geo-loader";
import { isRecord } from "@/lib/utils";

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
  const [geoReady, setGeoReady] = useState(true);
  const [geoError, setGeoError] = useState<string | null>(null);

  const validation = useMemo(() => validateChartSpec(spec), [spec]);
  const requiresChinaMap = useMemo(() => requiresMapRegistration(spec.echartsOption), [spec.echartsOption]);

  const option = useMemo(() => {
    if (!validation.valid) return null;
    const baseOption = requiresChinaMap
      ? normaliseMapOption(spec.echartsOption)
      : spec.echartsOption;
    return {
      ...WARM_THEME,
      ...baseOption,
      animation: true,
      animationDuration: 600,
      animationEasing: "cubicInOut" as const,
    };
  }, [spec.echartsOption, requiresChinaMap, validation.valid]);

  useEffect(() => {
    if (!requiresChinaMap) {
      setGeoReady(true);
      setGeoError(null);
      return;
    }

    let cancelled = false;
    setGeoReady(false);
    setGeoError(null);

    ensureChinaMap().then((ok) => {
      if (cancelled) {
        return;
      }
      if (!ok) {
        setGeoError("无法加载中国地图 GeoJSON 数据，请检查网络连接。");
        return;
      }
      setGeoReady(true);
    });

    return () => {
      cancelled = true;
    };
  }, [requiresChinaMap]);

  useEffect(() => {
    if (!chartRef.current || !option || !geoReady) return;

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
  }, [geoReady, option]);

  if (!validation.valid || geoError) {
    return (
      <div
        className="flex items-center justify-center bg-warm-sand rounded-comfortable"
        style={{ height }}
      >
        <div className="text-center px-4">
          <p className="text-body-sm text-error-crimson font-medium">Chart rendering failed</p>
          <p className="text-caption text-stone-gray mt-1">
            {geoError ?? validation.errors[0] ?? "Invalid chart configuration"}
          </p>
        </div>
      </div>
    );
  }

  if (requiresChinaMap && !geoReady) {
    return (
      <div
        className="flex items-center justify-center bg-warm-sand rounded-comfortable"
        style={{ height }}
      >
        <p className="text-caption text-stone-gray">地图数据加载中...</p>
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

function requiresMapRegistration(option: Record<string, unknown>): boolean {
  const series = option.series;
  if (!Array.isArray(series)) {
    return false;
  }

  return series.some((item) => isRecord(item) && item.type === "map");
}

function normaliseMapOption(option: Record<string, unknown>): Record<string, unknown> {
  const series = option.series;
  if (!Array.isArray(series)) {
    return option;
  }

  const nextSeries = series.map((item) => {
    if (!isRecord(item) || item.type !== "map") {
      return item;
    }

    const data = item.data;
    if (!Array.isArray(data)) {
      return item;
    }

    return {
      ...item,
      data: data.map((datum) => {
        if (!isRecord(datum)) {
          return datum;
        }
        const name = datum.name;
        return {
          ...datum,
          name: typeof name === "string" ? normaliseProvinceName(name) : name,
        };
      }),
    };
  });

  return { ...option, series: nextSeries };
}
