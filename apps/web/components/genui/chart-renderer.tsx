"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Funnel,
  FunnelChart,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  Treemap,
  XAxis,
  YAxis
} from "recharts";

import type { GenUISpec } from "../../lib/genui/spec";
import { EmptyPanel, ErrorPanel } from "./state-panels";

const PIE_COLORS = ["#155dfc", "#00a63e", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"];
const SERIES_COLORS = ["#155dfc", "#00a63e", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#14b8a6"];

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
        <div className="recharts-wrap">
          <ResponsiveContainer width="100%" height="100%" minWidth={320} minHeight={320}>
            <BarChart data={spec.data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey} />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey={yKey} fill="#155dfc" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
    );
  }

  if (spec.chart_type === "line") {
    return (
      <section className="genui-panel" data-testid="recharts-line-chart">
        <h3>{spec.title}</h3>
        <div className="recharts-wrap">
          <ResponsiveContainer width="100%" height="100%" minWidth={320} minHeight={320}>
            <LineChart data={spec.data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey} />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey={yKey} stroke="#155dfc" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>
    );
  }

  if (spec.chart_type === "pie") {
    return (
      <section className="genui-panel" data-testid="recharts-pie-chart">
        <h3>{spec.title}</h3>
        <div className="recharts-wrap">
          <ResponsiveContainer width="100%" height="100%" minWidth={320} minHeight={320}>
            <PieChart>
              <Tooltip />
              <Legend />
              <Pie data={spec.data} dataKey={yKey} nameKey={xKey} cx="50%" cy="50%" outerRadius={112}>
                {spec.data.map((_, index) => (
                  <Cell key={`slice-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </div>
      </section>
    );
  }

  if (spec.chart_type === "area") {
    return (
      <section className="genui-panel" data-testid="recharts-area-chart">
        <h3>{spec.title}</h3>
        <div className="recharts-wrap">
          <ResponsiveContainer width="100%" height="100%" minWidth={320} minHeight={320}>
            <AreaChart data={spec.data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey} />
              <YAxis />
              <Tooltip />
              <Legend />
              <Area type="monotone" dataKey={yKey} stroke="#155dfc" fill="#dbeafe" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>
    );
  }

  if (spec.chart_type === "scatter") {
    return (
      <section className="genui-panel" data-testid="recharts-scatter-chart">
        <h3>{spec.title}</h3>
        <div className="recharts-wrap">
          <ResponsiveContainer width="100%" height="100%" minWidth={320} minHeight={320}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey} type="number" name={xKey} />
              <YAxis dataKey={yKey} type="number" name={yKey} />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} />
              <Legend />
              <Scatter name={spec.title} data={spec.data} fill="#155dfc" />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </section>
    );
  }

  if (spec.chart_type === "radar") {
    const radarData = buildRadarData(spec.data, xKey, yKey);
    return (
      <section className="genui-panel" data-testid="recharts-radar-chart">
        <h3>{spec.title}</h3>
        <div className="recharts-wrap">
          <ResponsiveContainer width="100%" height="100%" minWidth={320} minHeight={320}>
            <RadarChart cx="50%" cy="50%" outerRadius="70%" data={radarData}>
              <PolarGrid />
              <PolarAngleAxis dataKey={xKey} />
              <PolarRadiusAxis />
              <Tooltip />
              <Legend />
              <Radar name={yKey} dataKey={yKey} stroke="#155dfc" fill="#155dfc" fillOpacity={0.3} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </section>
    );
  }

  if (spec.chart_type === "treemap") {
    const treemapData = buildTreemapData(spec.data, xKey, yKey);
    return (
      <section className="genui-panel" data-testid="recharts-treemap-chart">
        <h3>{spec.title}</h3>
        <div className="recharts-wrap">
          <ResponsiveContainer width="100%" height="100%" minWidth={320} minHeight={320}>
            <Treemap
              data={treemapData}
              dataKey="size"
              aspectRatio={4 / 3}
              stroke="#fff"
              content={<TreemapCustomContent colors={PIE_COLORS} />}
            />
          </ResponsiveContainer>
        </div>
      </section>
    );
  }

  if (spec.chart_type === "funnel") {
    return (
      <section className="genui-panel" data-testid="recharts-funnel-chart">
        <h3>{spec.title}</h3>
        <div className="recharts-wrap">
          <ResponsiveContainer width="100%" height="100%" minWidth={320} minHeight={320}>
            <FunnelChart>
              <Tooltip />
              <Funnel dataKey={yKey} nameKey={xKey} data={spec.data} isAnimationActive>
                {spec.data.map((_, index) => (
                  <Cell key={`funnel-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                ))}
              </Funnel>
            </FunnelChart>
          </ResponsiveContainer>
        </div>
      </section>
    );
  }

  if (spec.chart_type === "radialBar") {
    return (
      <section className="genui-panel" data-testid="recharts-radialBar-chart">
        <h3>{spec.title}</h3>
        <div className="recharts-wrap">
          <ResponsiveContainer width="100%" height="100%" minWidth={320} minHeight={320}>
            <RadialBarChart cx="50%" cy="50%" innerRadius="20%" outerRadius="90%" data={spec.data} startAngle={180} endAngle={0}>
              <RadialBar background dataKey={yKey} label={{ position: "insideStart", fill: "#fff", fontSize: 12 }}>
                {spec.data.map((_, index) => (
                  <Cell key={`radial-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                ))}
              </RadialBar>
              <Legend
                iconSize={10}
                layout="vertical"
                verticalAlign="middle"
                align="right"
              />
              <Tooltip />
            </RadialBarChart>
          </ResponsiveContainer>
        </div>
      </section>
    );
  }

  if (spec.chart_type === "composed") {
    const series = spec.config.series ?? [];
    return (
      <section className="genui-panel" data-testid="recharts-composed-chart">
        <h3>{spec.title}</h3>
        <div className="recharts-wrap">
          <ResponsiveContainer width="100%" height="100%" minWidth={320} minHeight={320}>
            <ComposedChart data={spec.data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey} />
              <YAxis />
              <Tooltip />
              <Legend />
              {series.length > 0
                ? series.map((s, index) => {
                    const color = SERIES_COLORS[index % SERIES_COLORS.length];
                    const seriesType = (s as Record<string, unknown>).type;
                    if (seriesType === "line") {
                      return <Line key={s.dataKey} type="monotone" dataKey={s.dataKey} stroke={color} strokeWidth={2} name={s.name} />;
                    }
                    if (seriesType === "area") {
                      return <Area key={s.dataKey} type="monotone" dataKey={s.dataKey} stroke={color} fill={color} fillOpacity={0.2} name={s.name} />;
                    }
                    return <Bar key={s.dataKey} dataKey={s.dataKey} fill={color} radius={[4, 4, 0, 0]} name={s.name} />;
                  })
                : <Bar dataKey={yKey} fill="#155dfc" radius={[6, 6, 0, 0]} />
              }
            </ComposedChart>
          </ResponsiveContainer>
        </div>
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

// ---------------------------------------------------------------------------
// Data transformation helpers
// ---------------------------------------------------------------------------

function inferXKey(data: Array<Record<string, unknown>>): string {
  if (!data.length) {
    return "label";
  }

  const fallback = Object.keys(data[0]).find((key) => key !== "metric_value");
  return fallback ?? "label";
}

function buildRadarData(
  data: Array<Record<string, unknown>>,
  xKey: string,
  yKey: string
): Array<Record<string, unknown>> {
  if (!data.length) return [];
  if (data[0][xKey] !== undefined && data[0][yKey] !== undefined) return data;
  return data;
}

interface TreemapNode {
  name: string;
  size?: number;
  children?: TreemapNode[];
  [key: string]: unknown;
}

function buildTreemapData(
  data: Array<Record<string, unknown>>,
  groupKey: string,
  sizeKey: string
): TreemapNode[] {
  if (!data.length) return [];

  if (Array.isArray((data[0] as Record<string, unknown>).children)) {
    return data as unknown as TreemapNode[];
  }

  const nameKey = findNameKey(data, groupKey, sizeKey);
  const groups = new Map<string, TreemapNode[]>();

  for (const row of data) {
    const group = String(row[groupKey] ?? "other");
    const name = nameKey ? String(row[nameKey] ?? "") : group;
    const size = typeof row[sizeKey] === "number" ? (row[sizeKey] as number) : 1;

    if (!groups.has(group)) {
      groups.set(group, []);
    }
    groups.get(group)!.push({ name, size });
  }

  if (groups.size === 1 && groups.values().next().value) {
    const entries = groups.values().next().value as TreemapNode[];
    if (entries.every((e) => e.name !== entries[0].name)) {
      return entries;
    }
  }

  return Array.from(groups.entries()).map(([groupName, children]) => ({
    name: groupName,
    children
  }));
}

function findNameKey(
  data: Array<Record<string, unknown>>,
  groupKey: string,
  sizeKey: string
): string | null {
  if (!data.length) return null;
  const keys = Object.keys(data[0]);
  return keys.find((k) => k !== groupKey && k !== sizeKey && typeof data[0][k] === "string") ?? null;
}

// ---------------------------------------------------------------------------
// Custom Treemap content renderer
// ---------------------------------------------------------------------------

interface TreemapContentProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  depth?: number;
  index?: number;
  colors: string[];
}

function TreemapCustomContent({ x = 0, y = 0, width = 0, height = 0, name = "", depth = 0, index = 0, colors }: TreemapContentProps) {
  const fill = depth < 2 ? colors[index % colors.length] : adjustBrightness(colors[((index * 7 + 3) % colors.length)], 0.2);
  const showLabel = width > 36 && height > 18;

  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={fill} stroke="#fff" strokeWidth={depth < 2 ? 2 : 1} rx={depth < 2 ? 4 : 2} />
      {showLabel && (
        <text
          x={x + width / 2}
          y={y + height / 2}
          textAnchor="middle"
          dominantBaseline="central"
          fill="#fff"
          fontSize={Math.min(14, Math.max(9, width / (name.length || 1) * 1.2))}
          fontWeight={depth < 2 ? 700 : 400}
        >
          {name.length > Math.floor(width / 8) ? name.slice(0, Math.floor(width / 8)) + "…" : name}
        </text>
      )}
    </g>
  );
}

function adjustBrightness(hex: string, amount: number): string {
  const num = parseInt(hex.replace("#", ""), 16);
  const r = Math.min(255, ((num >> 16) & 0xff) + Math.round(255 * amount));
  const g = Math.min(255, ((num >> 8) & 0xff) + Math.round(255 * amount));
  const b = Math.min(255, (num & 0xff) + Math.round(255 * amount));
  return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`;
}
