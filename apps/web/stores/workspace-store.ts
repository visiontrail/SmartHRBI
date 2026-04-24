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
} from "@/types/workspace";

type WorkspaceState = {
  workspaces: Workspace[];
  activeWorkspaceId: string | null;
  nodes: WorkspaceNode[];
  edges: WorkspaceEdge[];
  viewport: { x: number; y: number; zoom: number };
  canvasFormat: WorkspaceCanvasFormat;
  hasUnsavedChanges: boolean;

  setWorkspaces: (workspaces: Workspace[]) => void;
  addWorkspace: (workspace: Workspace) => void;
  updateWorkspaceTitle: (workspaceId: string, title: string) => void;
  removeWorkspace: (workspaceId: string) => void;
  setActiveWorkspace: (workspaceId: string | null) => void;
  setNodes: (nodes: WorkspaceNode[]) => void;
  setEdges: (edges: WorkspaceEdge[]) => void;
  addNode: (node: WorkspaceNode) => void;
  updateNode: (nodeId: string, data: Partial<WorkspaceNode>) => void;
  removeNode: (nodeId: string) => void;
  setViewport: (viewport: { x: number; y: number; zoom: number }) => void;
  setCanvasFormat: (canvasFormat: WorkspaceCanvasFormat) => void;
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
      hasUnsavedChanges: false,
    }),

  setNodes: (nodes) => set({ nodes, hasUnsavedChanges: true }),

  setEdges: (edges) => set({ edges, hasUnsavedChanges: true }),

  addNode: (node) =>
    set((state) => ({
      nodes: [...state.nodes, node],
      hasUnsavedChanges: true,
    })),

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

  loadSnapshot: (snapshot) =>
    set({
      nodes: snapshot.nodes,
      edges: snapshot.edges,
      viewport: snapshot.viewport,
      canvasFormat: normalizeCanvasFormat(snapshot.canvasFormat),
      hasUnsavedChanges: false,
    }),

  getSnapshot: () => {
    const { activeWorkspaceId, nodes, edges, viewport, canvasFormat } = get();
    if (!activeWorkspaceId) return null;
    return { workspaceId: activeWorkspaceId, nodes, edges, viewport, canvasFormat };
  },

  setHasUnsavedChanges: (value) => set({ hasUnsavedChanges: value }),
}));
