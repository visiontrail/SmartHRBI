"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import type { GenUISpec } from "../../lib/genui/spec";
import { EmptyPanel, ErrorPanel } from "./state-panels";

const PIE_COLORS = ["#155dfc", "#00a63e", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"];

type ChartRendererProps = {
  spec: GenUISpec;
};

export function ChartRenderer({ spec }: ChartRendererProps) {
  if (spec.engine === "echarts") {
    return <EChartsRenderer spec={spec} />;
  }

  if (spec.chart_type === "empty") {
    return <EmptyPanel title={spec.title} />;
  }

  if (spec.chart_type === "note") {
    const content = spec.data[0];
    return (
      <section className="genui-panel" data-testid="recharts-note-chart">
        <h3>{spec.title}</h3>
        <pre>{JSON.stringify(content, null, 2)}</pre>
      </section>
    );
  }

  if (spec.chart_type === "table") {
    const columns =
      spec.config.columns ??
      (spec.data[0] ? Object.keys(spec.data[0]).map((column) => String(column)) : []);

    if (!columns.length) {
      return <EmptyPanel title={spec.title} />;
    }

    return (
      <section className="genui-panel" data-testid="recharts-table-chart">
        <h3>{spec.title}</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {spec.data.map((row, rowIndex) => (
                <tr key={`${rowIndex}-${String(row[columns[0]] ?? "row")}`}>
                  {columns.map((column) => (
                    <td key={`${rowIndex}-${column}`}>{String(row[column] ?? "-")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    );
  }

  const xKey = spec.config.xKey ?? inferXKey(spec.data);
  const yKey = spec.config.yKey ?? "metric_value";

  if (!spec.data.length && spec.chart_type !== "single_value") {
    return <EmptyPanel title={spec.title} />;
  }

  if (spec.chart_type === "single_value") {
    const value = spec.data[0]?.[yKey] ?? spec.data[0]?.metric_value ?? 0;
    return (
      <section className="genui-panel genui-panel--single-value" data-testid="recharts-single_value-chart">
        <h3>{spec.title}</h3>
        <strong>{String(value)}</strong>
      </section>
    );
  }

  if (spec.chart_type === "bar") {
    return (
      <section className="genui-panel" data-testid="recharts-bar-chart">
        <h3>{spec.title}</h3>
        <BarChart width={680} height={320} data={spec.data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={xKey} />
          <YAxis />
          <Tooltip />
          <Legend />
          <Bar dataKey={yKey} fill="#155dfc" radius={[6, 6, 0, 0]} />
        </BarChart>
      </section>
    );
  }

  if (spec.chart_type === "line") {
    return (
      <section className="genui-panel" data-testid="recharts-line-chart">
        <h3>{spec.title}</h3>
        <LineChart width={680} height={320} data={spec.data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={xKey} />
          <YAxis />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey={yKey} stroke="#155dfc" strokeWidth={2} dot={false} />
        </LineChart>
      </section>
    );
  }

  if (spec.chart_type === "pie") {
    return (
      <section className="genui-panel" data-testid="recharts-pie-chart">
        <h3>{spec.title}</h3>
        <PieChart width={680} height={320}>
          <Tooltip />
          <Legend />
          <Pie data={spec.data} dataKey={yKey} nameKey={xKey} cx="50%" cy="50%" outerRadius={112}>
            {spec.data.map((_, index) => (
              <Cell key={`slice-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
            ))}
          </Pie>
        </PieChart>
      </section>
    );
  }

  return <ErrorPanel description={`Unsupported recharts chart type: ${spec.chart_type}`} />;
}

function EChartsRenderer({ spec }: { spec: Extract<GenUISpec, { engine: "echarts" }> }) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const option = useMemo(() => spec.config.option, [spec.config.option]);

  useEffect(() => {
    if (!chartRef.current) {
      return;
    }

    let instance: ReturnType<typeof echarts.init> | undefined;
    try {
      instance = echarts.init(chartRef.current);
      instance.setOption(option);
      const handleResize = () => instance?.resize();
      window.addEventListener("resize", handleResize);
      return () => {
        window.removeEventListener("resize", handleResize);
        instance?.dispose();
      };
    } catch (error) {
      setRenderError(error instanceof Error ? error.message : "Unknown ECharts error");
      instance?.dispose();
      return;
    }
  }, [option]);

  if (renderError) {
    return <ErrorPanel description={`ECharts render failed: ${renderError}`} />;
  }

  return (
    <section className="genui-panel" data-testid="echarts-chart">
      <h3>{spec.title}</h3>
      <div ref={chartRef} className="echarts-canvas" />
    </section>
  );
}

function inferXKey(data: Array<Record<string, unknown>>): string {
  if (!data.length) {
    return "label";
  }

  const fallback = Object.keys(data[0]).find((key) => key !== "metric_value");
  return fallback ?? "label";
}
