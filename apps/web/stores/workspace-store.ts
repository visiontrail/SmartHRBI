import { create } from "zustand";
import {
  DEFAULT_CANVAS_FORMAT,
  normalizeCanvasFormat,
} from "@/lib/workspace/canvas-formats";
import type {
  Workspace,
  WorkspaceNode,
  WorkspaceEdge,
  WorkspaceSnapshot,
  WorkspaceCanvasFormat,
  WebDesignLayout,
  WebDesignSidebarItem,
} from "@/types/workspace";

const DEFAULT_WEB_DESIGN_LAYOUT: WebDesignLayout = {
  grid: {
    columns: 3,
    rows: [
      { id: "row-1", height: 400 },
      { id: "row-2", height: 400 },
    ],
  },
  zones: [],
  sidebar: [{ id: "section-1", label: "Section 1", anchorRowId: "row-1", children: [] }],
  preview: false,
};

type WorkspaceState = {
  workspaces: Workspace[];
  activeWorkspaceId: string | null;
  nodes: WorkspaceNode[];
  edges: WorkspaceEdge[];
  viewport: { x: number; y: number; zoom: number };
  canvasFormat: WorkspaceCanvasFormat;
  webDesign: WebDesignLayout;
  hasUnsavedChanges: boolean;

  setWorkspaces: (workspaces: Workspace[]) => void;
  addWorkspace: (workspace: Workspace) => void;
  updateWorkspaceTitle: (workspaceId: string, title: string) => void;
  removeWorkspace: (workspaceId: string) => void;
  setActiveWorkspace: (workspaceId: string | null) => void;
  setNodes: (nodes: WorkspaceNode[]) => void;
  setEdges: (edges: WorkspaceEdge[]) => void;
  addNode: (node: WorkspaceNode) => void;
  addNodeToWebDesign: (node: WorkspaceNode) => void;
  updateNode: (nodeId: string, data: Partial<WorkspaceNode>) => void;
  removeNode: (nodeId: string) => void;
  setViewport: (viewport: { x: number; y: number; zoom: number }) => void;
  setCanvasFormat: (canvasFormat: WorkspaceCanvasFormat) => void;
  setWebDesignColumns: (columns: number) => void;
  addWebDesignRow: () => void;
  removeWebDesignRow: (rowId: string) => void;
  setWebDesignRowHeight: (rowId: string, height: number) => void;
  placeWebDesignZone: (nodeId: string, column: number, row: number) => void;
  moveWebDesignZone: (zoneId: string, column: number, row: number) => void;
  resizeWebDesignZone: (zoneId: string, colSpan: number, rowSpan: number) => void;
  removeWebDesignZone: (zoneId: string) => void;
  setWebDesignPreview: (preview: boolean) => void;
  addWebDesignSidebarItem: (parentId?: string) => void;
  updateWebDesignSidebarItem: (itemId: string, updates: Partial<Omit<WebDesignSidebarItem, "id" | "children">>) => void;
  removeWebDesignSidebarItem: (itemId: string) => void;
  loadSnapshot: (snapshot: WorkspaceSnapshot) => void;
  getSnapshot: () => WorkspaceSnapshot | null;
  setHasUnsavedChanges: (value: boolean) => void;
};

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  workspaces: [],
  activeWorkspaceId: null,
  nodes: [],
  edges: [],
  viewport: { x: 0, y: 0, zoom: 1 },
  canvasFormat: DEFAULT_CANVAS_FORMAT,
  webDesign: DEFAULT_WEB_DESIGN_LAYOUT,
  hasUnsavedChanges: false,

  setWorkspaces: (workspaces) => set({ workspaces }),

  addWorkspace: (workspace) =>
    set((state) => ({
      workspaces: [workspace, ...state.workspaces],
    })),

  updateWorkspaceTitle: (workspaceId, title) =>
    set((state) => ({
      workspaces: state.workspaces.map((workspace) =>
        workspace.id === workspaceId
          ? { ...workspace, title, updatedAt: new Date().toISOString() }
          : workspace
      ),
    })),

  removeWorkspace: (workspaceId) =>
    set((state) => ({
      workspaces: state.workspaces.filter((w) => w.id !== workspaceId),
      activeWorkspaceId: state.activeWorkspaceId === workspaceId ? null : state.activeWorkspaceId,
    })),

  setActiveWorkspace: (workspaceId) =>
    set({
      activeWorkspaceId: workspaceId,
      nodes: [],
      edges: [],
      viewport: { x: 0, y: 0, zoom: 1 },
      canvasFormat: DEFAULT_CANVAS_FORMAT,
      webDesign: DEFAULT_WEB_DESIGN_LAYOUT,
      hasUnsavedChanges: false,
    }),

  setNodes: (nodes) => set({ nodes, hasUnsavedChanges: true }),

  setEdges: (edges) => set({ edges, hasUnsavedChanges: true }),

  addNode: (node) =>
    set((state) => ({
      nodes: [...state.nodes, node],
      hasUnsavedChanges: true,
    })),

  addNodeToWebDesign: (node) =>
    set((state) => {
      if (node.data.type !== "chart") return {};

      const placement = findNextWebDesignCell(state.webDesign);
      const rows =
        placement.row < state.webDesign.grid.rows.length
          ? state.webDesign.grid.rows
          : [...state.webDesign.grid.rows, { id: `row-${state.webDesign.grid.rows.length + 1}`, height: 400 }];

      return {
        nodes: [...state.nodes, node],
        canvasFormat: { id: "web-design" },
        webDesign: {
          ...state.webDesign,
          preview: false,
          grid: { ...state.webDesign.grid, rows },
          zones: [
            ...state.webDesign.zones,
            {
              id: `zone-${node.id}`,
              nodeId: node.id,
              chartId: node.data.assetId,
              column: placement.column,
              row: placement.row,
              colSpan: 1,
              rowSpan: 1,
            },
          ],
        },
        hasUnsavedChanges: true,
      };
    }),

  updateNode: (nodeId, data) =>
    set((state) => ({
      nodes: state.nodes.map((n) =>
        n.id === nodeId ? { ...n, ...data, data: { ...n.data, ...(data.data ?? {}) } } : n
      ),
      hasUnsavedChanges: true,
    })),

  removeNode: (nodeId) =>
    set((state) => ({
      nodes: state.nodes.filter((n) => n.id !== nodeId),
      edges: state.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      hasUnsavedChanges: true,
    })),

  setViewport: (viewport) => set({ viewport }),

  setCanvasFormat: (canvasFormat) =>
    set((state) => {
      const nextCanvasFormat = normalizeCanvasFormat(canvasFormat);
      if (state.canvasFormat.id === nextCanvasFormat.id) {
        return {};
      }
      return {
        canvasFormat: nextCanvasFormat,
        hasUnsavedChanges: true,
      };
    }),

  setWebDesignColumns: (columns) =>
    set((state) => ({
      webDesign: clampLayoutToColumns(
        {
          ...state.webDesign,
          grid: {
            ...state.webDesign.grid,
            columns: clamp(columns, 2, 10),
          },
        },
        clamp(columns, 2, 10)
      ),
      hasUnsavedChanges: true,
    })),

  addWebDesignRow: () =>
    set((state) => {
      const nextIndex = state.webDesign.grid.rows.length + 1;
      return {
        webDesign: {
          ...state.webDesign,
          grid: {
            ...state.webDesign.grid,
            rows: [...state.webDesign.grid.rows, { id: `row-${nextIndex}`, height: 400 }],
          },
        },
        hasUnsavedChanges: true,
      };
    }),

  removeWebDesignRow: (rowId) =>
    set((state) => {
      if (state.webDesign.grid.rows.length <= 1) return {};
      const rows = state.webDesign.grid.rows.filter((row) => row.id !== rowId);
      return {
        webDesign: {
          ...state.webDesign,
          grid: { ...state.webDesign.grid, rows },
          zones: state.webDesign.zones.filter((zone) => rows[zone.row]),
          sidebar: retargetSidebar(state.webDesign.sidebar, rows[0]?.id ?? "row-1"),
        },
        hasUnsavedChanges: true,
      };
    }),

  setWebDesignRowHeight: (rowId, height) =>
    set((state) => ({
      webDesign: {
        ...state.webDesign,
        grid: {
          ...state.webDesign.grid,
          rows: state.webDesign.grid.rows.map((row) =>
            row.id === rowId ? { ...row, height: clamp(height, 120, 800) } : row
          ),
        },
      },
      hasUnsavedChanges: true,
    })),

  placeWebDesignZone: (nodeId, column, row) =>
    set((state) => {
      const chartNode = state.nodes.find((node) => node.id === nodeId && node.data.type === "chart");
      if (!chartNode || state.webDesign.zones.some((zone) => zone.nodeId === nodeId)) return {};
      if (chartNode.data.type !== "chart") return {};
      const safeColumn = clamp(column, 0, state.webDesign.grid.columns - 1);
      const safeRow = clamp(row, 0, state.webDesign.grid.rows.length - 1);
      if (state.webDesign.zones.some((zone) => zone.column === safeColumn && zone.row === safeRow)) {
        return {};
      }
      return {
        webDesign: {
          ...state.webDesign,
          zones: [
            ...state.webDesign.zones,
            {
              id: `zone-${Date.now().toString(36)}`,
              nodeId,
              chartId: chartNode.data.assetId,
              column: safeColumn,
              row: safeRow,
              colSpan: 1,
              rowSpan: 1,
            },
          ],
        },
        hasUnsavedChanges: true,
      };
    }),

  moveWebDesignZone: (zoneId, column, row) =>
    set((state) => {
      const zone = state.webDesign.zones.find((item) => item.id === zoneId);
      if (!zone) return {};

      const safeColumn = clamp(column, 0, state.webDesign.grid.columns - zone.colSpan);
      const safeRow = clamp(row, 0, state.webDesign.grid.rows.length - zone.rowSpan);
      if (zone.column === safeColumn && zone.row === safeRow) return {};
      if (zoneOverlaps(state.webDesign.zones, zoneId, safeColumn, safeRow, zone.colSpan, zone.rowSpan)) {
        return {};
      }

      return {
        webDesign: {
          ...state.webDesign,
          zones: state.webDesign.zones.map((item) =>
            item.id === zoneId ? { ...item, column: safeColumn, row: safeRow } : item
          ),
        },
        hasUnsavedChanges: true,
      };
    }),

  resizeWebDesignZone: (zoneId, colSpan, rowSpan) =>
    set((state) => ({
      webDesign: {
        ...state.webDesign,
        zones: state.webDesign.zones.map((zone) =>
          zone.id === zoneId
            ? {
                ...zone,
                colSpan: clamp(colSpan, 1, state.webDesign.grid.columns - zone.column),
                rowSpan: clamp(rowSpan, 1, state.webDesign.grid.rows.length - zone.row),
              }
            : zone
        ),
      },
      hasUnsavedChanges: true,
    })),

  removeWebDesignZone: (zoneId) =>
    set((state) => ({
      webDesign: {
        ...state.webDesign,
        zones: state.webDesign.zones.filter((zone) => zone.id !== zoneId),
      },
      hasUnsavedChanges: true,
    })),

  setWebDesignPreview: (preview) =>
    set((state) => ({
      webDesign: { ...state.webDesign, preview },
      hasUnsavedChanges: true,
    })),

  addWebDesignSidebarItem: (parentId) =>
    set((state) => ({
      webDesign: {
        ...state.webDesign,
        sidebar: addSidebarItem(state.webDesign.sidebar, parentId, state.webDesign.grid.rows[0]?.id ?? "row-1"),
      },
      hasUnsavedChanges: true,
    })),

  updateWebDesignSidebarItem: (itemId, updates) =>
    set((state) => ({
      webDesign: {
        ...state.webDesign,
        sidebar: mapSidebarItems(state.webDesign.sidebar, (item) =>
          item.id === itemId ? { ...item, ...updates } : item
        ),
      },
      hasUnsavedChanges: true,
    })),

  removeWebDesignSidebarItem: (itemId) =>
    set((state) => ({
      webDesign: {
        ...state.webDesign,
        sidebar: removeSidebarItem(state.webDesign.sidebar, itemId),
      },
      hasUnsavedChanges: true,
    })),

  loadSnapshot: (snapshot) =>
    set({
      nodes: snapshot.nodes,
      edges: snapshot.edges,
      viewport: snapshot.viewport,
      canvasFormat: normalizeCanvasFormat(snapshot.canvasFormat),
      webDesign: normalizeWebDesignLayout(snapshot.webDesign),
      hasUnsavedChanges: false,
    }),

  getSnapshot: () => {
    const { activeWorkspaceId, nodes, edges, viewport, canvasFormat, webDesign } = get();
    if (!activeWorkspaceId) return null;
    return { workspaceId: activeWorkspaceId, nodes, edges, viewport, canvasFormat, webDesign };
  },

  setHasUnsavedChanges: (value) => set({ hasUnsavedChanges: value }),
}));

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.trunc(value)));
}

function normalizeWebDesignLayout(value: unknown): WebDesignLayout {
  if (!value || typeof value !== "object") return DEFAULT_WEB_DESIGN_LAYOUT;
  const layout = value as Partial<WebDesignLayout>;
  return {
    grid: {
      columns: clamp(Number(layout.grid?.columns ?? 3), 2, 10),
      rows: Array.isArray(layout.grid?.rows) && layout.grid.rows.length
        ? layout.grid.rows.map((row, index) => ({
            id: String(row.id || `row-${index + 1}`),
            height: clamp(Number(row.height ?? 400), 120, 800),
          }))
        : DEFAULT_WEB_DESIGN_LAYOUT.grid.rows,
    },
    zones: Array.isArray(layout.zones) ? layout.zones : [],
    sidebar: Array.isArray(layout.sidebar) ? layout.sidebar : DEFAULT_WEB_DESIGN_LAYOUT.sidebar,
    preview: Boolean(layout.preview),
  };
}

function findNextWebDesignCell(layout: WebDesignLayout): { column: number; row: number } {
  const occupied = new Set<string>();
  for (const zone of layout.zones) {
    for (let row = zone.row; row < zone.row + zone.rowSpan; row += 1) {
      for (let column = zone.column; column < zone.column + zone.colSpan; column += 1) {
        occupied.add(`${column}:${row}`);
      }
    }
  }

  for (let row = 0; row < layout.grid.rows.length; row += 1) {
    for (let column = 0; column < layout.grid.columns; column += 1) {
      if (!occupied.has(`${column}:${row}`)) return { column, row };
    }
  }

  return { column: 0, row: layout.grid.rows.length };
}

function zoneOverlaps(
  zones: WebDesignLayout["zones"],
  zoneId: string,
  column: number,
  row: number,
  colSpan: number,
  rowSpan: number
): boolean {
  return zones.some((zone) => {
    if (zone.id === zoneId) return false;

    return (
      column < zone.column + zone.colSpan &&
      column + colSpan > zone.column &&
      row < zone.row + zone.rowSpan &&
      row + rowSpan > zone.row
    );
  });
}

function clampLayoutToColumns(layout: WebDesignLayout, columns: number): WebDesignLayout {
  return {
    ...layout,
    zones: layout.zones.map((zone) => ({
      ...zone,
      column: clamp(zone.column, 0, columns - 1),
      colSpan: clamp(zone.colSpan, 1, columns - clamp(zone.column, 0, columns - 1)),
    })),
  };
}

function addSidebarItem(
  items: WebDesignSidebarItem[],
  parentId: string | undefined,
  anchorRowId: string
): WebDesignSidebarItem[] {
  const nextItem = {
    id: `section-${Date.now().toString(36)}`,
    label: `Section ${items.length + 1}`,
    anchorRowId,
    children: [],
  };
  if (!parentId) return [...items, nextItem];
  return items.map((item) =>
    item.id === parentId
      ? { ...item, children: [...item.children, { ...nextItem, label: "Sub-section" }] }
      : item
  );
}

function mapSidebarItems(
  items: WebDesignSidebarItem[],
  mapper: (item: WebDesignSidebarItem) => WebDesignSidebarItem
): WebDesignSidebarItem[] {
  return items.map((item) => mapper({ ...item, children: mapSidebarItems(item.children, mapper) }));
}

function removeSidebarItem(items: WebDesignSidebarItem[], itemId: string): WebDesignSidebarItem[] {
  return items
    .filter((item) => item.id !== itemId)
    .map((item) => ({ ...item, children: removeSidebarItem(item.children, itemId) }));
}

function retargetSidebar(items: WebDesignSidebarItem[], fallbackRowId: string): WebDesignSidebarItem[] {
  return items.map((item) => ({
    ...item,
    anchorRowId: item.anchorRowId || fallbackRowId,
    children: retargetSidebar(item.children, fallbackRowId),
  }));
}
