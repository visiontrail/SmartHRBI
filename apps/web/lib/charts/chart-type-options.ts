import type { KnownChartType } from "@/types/chart";

export type QueryChartType = Extract<
  KnownChartType,
  | "bar"
  | "stacked_bar"
  | "line"
  | "area"
  | "scatter"
  | "pie"
  | "funnel"
  | "radar"
  | "treemap"
  | "sunburst"
  | "sankey"
  | "graph"
  | "boxplot"
  | "candlestick"
  | "map"
  | "heatmap"
  | "parallel"
  | "gauge"
  | "single_value"
  | "wordCloud"
  | "table"
>;

export type ChartTypeOption = {
  type: QueryChartType;
  label: string;
  description: string;
  group: string;
};

export const QUERY_CHART_TYPE_OPTIONS: ChartTypeOption[] = [
  { type: "bar", label: "Bar", description: "Compare categorical values.", group: "Comparison" },
  { type: "stacked_bar", label: "Stacked bar", description: "Compare totals by stacked groups.", group: "Comparison" },
  { type: "line", label: "Line", description: "Show trends over time or order.", group: "Trend" },
  { type: "area", label: "Area", description: "Trend with filled volume.", group: "Trend" },
  { type: "scatter", label: "Scatter", description: "Show correlation between numeric fields.", group: "Distribution" },
  { type: "pie", label: "Pie", description: "Show share of a whole.", group: "Share" },
  { type: "funnel", label: "Funnel", description: "Show pipeline or conversion stages.", group: "Process" },
  { type: "radar", label: "Radar", description: "Compare multiple dimensions.", group: "Comparison" },
  { type: "treemap", label: "Treemap", description: "Show hierarchical part-to-whole blocks.", group: "Hierarchy" },
  { type: "sunburst", label: "Sunburst", description: "Show nested hierarchy as rings.", group: "Hierarchy" },
  { type: "sankey", label: "Sankey", description: "Show weighted flow between stages.", group: "Flow" },
  { type: "graph", label: "Graph", description: "Show relationships or networks.", group: "Relationship" },
  { type: "boxplot", label: "Boxplot", description: "Show statistical distribution.", group: "Statistics" },
  { type: "candlestick", label: "Candlestick", description: "Show OHLC financial values.", group: "Finance" },
  { type: "map", label: "China map", description: "Show province-level choropleth values.", group: "Geography" },
  { type: "heatmap", label: "Heatmap", description: "Show intensity across a 2D grid.", group: "Intensity" },
  { type: "parallel", label: "Parallel", description: "Compare many numeric dimensions.", group: "Multivariate" },
  { type: "gauge", label: "Gauge", description: "Show one KPI on a dial.", group: "KPI" },
  { type: "single_value", label: "Single value", description: "Show one headline metric.", group: "KPI" },
  { type: "wordCloud", label: "Word cloud", description: "Show weighted words or tags.", group: "Text" },
  { type: "table", label: "Table", description: "Show structured multi-column data.", group: "Tabular" },
];

const QUERY_CHART_TYPE_SET = new Set<string>(QUERY_CHART_TYPE_OPTIONS.map((item) => item.type));

export function isQueryChartType(value: string): value is QueryChartType {
  return QUERY_CHART_TYPE_SET.has(value);
}

export function findQueryChartType(value: string): QueryChartType | null {
  return isQueryChartType(value) ? value : null;
}
