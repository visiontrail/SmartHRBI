export type PortalWorkspace = {
  workspace_id: string;
  name: string;
  latest_page_id: string;
  latest_version: number;
  published_at: string;
};

export type PortalManifestResponse = {
  page_id: string;
  workspace_id: string;
  version: number;
  published_at: string;
  manifest: PublishedManifest;
};

export type PublishedManifest = {
  layout: {
    grid: { columns: number; rows: { id: string; height: number }[] };
    zones: PublishedZone[];
    pages?: PublishedPageLayout[];
    activePageId?: string;
  };
  sidebar: PublishedSidebarItem[];
  charts: PublishedChartEntry[];
};

export type PublishedPageLayout = {
  id: string;
  title: string;
  grid: { columns: number; rows: { id: string; height: number }[] };
  zones: PublishedZone[];
};

export type PublishedZone = {
  id: string;
  nodeId: string;
  chartId?: string;
  chart_id?: string;
  column: number;
  row: number;
  colSpan: number;
  rowSpan: number;
};

export type PublishedChartEntry = {
  chart_id: string;
  title: string;
  chart_type?: string;
  data_truncated?: boolean;
};

export type PublishedSidebarItem = {
  id: string;
  label: string;
  pageId?: string;
  anchorRowId: string;
  children: PublishedSidebarItem[];
};

export type PublishedChartData = {
  page_id: string;
  chart_id: string;
  spec: {
    chartType?: string;
    chart_type?: string;
    title?: string;
    echartsOption?: Record<string, unknown>;
  };
  rows: Record<string, unknown>[];
  data_truncated: boolean;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function fetchPortalWorkspaces(): Promise<PortalWorkspace[]> {
  const response = await fetch(`${API_BASE_URL}/portal/workspaces`, { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok) throw new Error("Unable to load portal workspaces");
  return Array.isArray(payload.workspaces) ? payload.workspaces : [];
}

export async function fetchPortalManifest(pageId: string): Promise<PortalManifestResponse> {
  const response = await fetch(`${API_BASE_URL}/portal/pages/${encodeURIComponent(pageId)}/manifest`, {
    cache: "no-store",
  });
  const payload = await response.json();
  if (!response.ok) throw new Error("Unable to load published page");
  return payload;
}

export async function fetchPublishedChartData(pageId: string, chartId: string): Promise<PublishedChartData> {
  const response = await fetch(
    `${API_BASE_URL}/portal/pages/${encodeURIComponent(pageId)}/charts/${encodeURIComponent(chartId)}/data`,
    { cache: "no-store" }
  );
  const payload = await response.json();
  if (!response.ok) throw new Error("Unable to load chart data");
  return payload;
}
