import type { Node, Edge } from "@xyflow/react";

export type Workspace = {
  id: string;
  title: string;
  description?: string;
  createdAt: string;
  updatedAt: string;
  nodeCount: number;
  thumbnail?: string;
};

export type WorkspaceNodeType = "chart" | "text" | "section";

export type ChartNodeData = {
  type: "chart";
  assetId: string;
  title: string;
  chartType: string;
  spec: import("./chart").ChartSpec;
  width: number;
  height: number;
};

export type TextNodeData = {
  type: "text";
  content: string;
  fontSize?: number;
  width: number;
  height: number;
};

export type SectionNodeData = {
  type: "section";
  title: string;
  width: number;
  height: number;
};

export type WorkspaceNodeData = ChartNodeData | TextNodeData | SectionNodeData;

export type WorkspaceNode = Node<WorkspaceNodeData>;
export type WorkspaceEdge = Edge;

export type WorkspaceSnapshot = {
  workspaceId: string;
  nodes: WorkspaceNode[];
  edges: WorkspaceEdge[];
  viewport: { x: number; y: number; zoom: number };
};

export type TableCatalogBusinessType = "roster" | "project_progress" | "attendance" | "other";
export type TableCatalogWriteMode =
  | "update_existing"
  | "time_partitioned_new_table"
  | "new_table"
  | "append_only";
export type TableCatalogTimeGrain = "none" | "month" | "quarter" | "year";

export type TableCatalogEntry = {
  id: string;
  workspaceId: string;
  tableName: string;
  humanLabel: string;
  businessType: TableCatalogBusinessType;
  writeMode: TableCatalogWriteMode;
  timeGrain: TableCatalogTimeGrain;
  isActiveTarget: boolean;
  primaryKeys: string[];
  matchColumns: string[];
  description?: string;
  createdAt: string;
  updatedAt: string;
};

export type SavedReportPage = {
  id: string;
  workspaceId: string;
  title: string;
  description?: string;
  snapshot: WorkspaceSnapshot;
  createdAt: string;
  updatedAt: string;
  createdBy: string;
  isPublished: boolean;
  shareUrl?: string;
};
