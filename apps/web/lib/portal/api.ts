import { API_BASE_URL } from "@/lib/api-base";

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

const DEFAULT_AUTH_CONTEXT = {
  userId: process.env.NEXT_PUBLIC_DEFAULT_USER_ID ?? "demo-user",
  projectId: process.env.NEXT_PUBLIC_DEFAULT_PROJECT_ID ?? "demo-project",
  role: process.env.NEXT_PUBLIC_DEFAULT_ROLE ?? "hr",
  department: null,
  clearance: 1,
};

async function portalHeaders(): Promise<Record<string, string>> {
  const { getAuthorizationHeader } = await import("@/lib/auth/session");
  return getAuthorizationHeader(API_BASE_URL, DEFAULT_AUTH_CONTEXT);
}

export class PortalError extends Error {
  status: number;
  code?: string;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "PortalError";
    this.code = code;
    this.status = status;
  }
}

export async function fetchPortalWorkspaces(): Promise<PortalWorkspace[]> {
  const headers = await portalHeaders();
  const response = await fetch(`${API_BASE_URL}/portal/workspaces`, { cache: "no-store", headers });
  const payload = await response.json();
  if (response.status === 401) throw new PortalError("authentication_required", "Login required", 401);
  if (!response.ok) throw new Error("Unable to load portal workspaces");
  return Array.isArray(payload.workspaces) ? payload.workspaces : [];
}

export async function fetchPortalManifest(pageId: string): Promise<PortalManifestResponse> {
  const headers = await portalHeaders();
  const response = await fetch(`${API_BASE_URL}/portal/pages/${encodeURIComponent(pageId)}/manifest`, {
    cache: "no-store",
    headers,
  });
  const payload = await response.json();
  if (response.status === 401) throw new PortalError("authentication_required", "Login required", 401);
  if (response.status === 403) throw new PortalError(payload?.detail?.code ?? "page_not_visible", "No access", 403);
  if (response.status === 404) throw new PortalError("page_not_found", "Page not found", 404);
  if (!response.ok) throw new Error("Unable to load published page");
  return payload;
}

export async function fetchPublishedChartData(pageId: string, chartId: string): Promise<PublishedChartData> {
  const headers = await portalHeaders();
  const response = await fetch(
    `${API_BASE_URL}/portal/pages/${encodeURIComponent(pageId)}/charts/${encodeURIComponent(chartId)}/data`,
    { cache: "no-store", headers }
  );
  const payload = await response.json();
  if (response.status === 403) throw new PortalError("page_not_visible", "No access", 403);
  if (!response.ok) throw new Error("Unable to load chart data");
  return payload;
}
