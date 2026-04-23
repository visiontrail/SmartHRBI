"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { useUIStore } from "@/stores/ui-store";
import type { IngestionCatalogSetupSeed } from "@/types/ingestion";
import * as api from "@/lib/workspace/api";

export function useWorkspaceList() {
  const setWorkspaces = useWorkspaceStore((s) => s.setWorkspaces);

  return useQuery({
    queryKey: ["workspaces"],
    queryFn: async () => {
      const workspaces = await api.fetchWorkspaces();
      setWorkspaces(workspaces);
      return workspaces;
    },
  });
}

export function useWorkspaceSnapshot(workspaceId: string | null) {
  const loadSnapshot = useWorkspaceStore((s) => s.loadSnapshot);

  return useQuery({
    queryKey: ["workspace-snapshot", workspaceId],
    queryFn: async () => {
      if (!workspaceId) return null;
      const snapshot = await api.fetchWorkspaceSnapshot(workspaceId);
      if (snapshot) loadSnapshot(snapshot);
      return snapshot;
    },
    enabled: !!workspaceId,
  });
}

export function useWorkspaceCatalog(workspaceId: string | null) {
  return useQuery({
    queryKey: ["workspace-catalog", workspaceId],
    queryFn: async () => {
      if (!workspaceId) return [];
      return api.fetchWorkspaceCatalog(workspaceId);
    },
    enabled: !!workspaceId,
  });
}

export function useWorkspaceCatalogDataPreview(
  workspaceId: string | null,
  catalogId: string | null,
  options: { limit?: number; offset?: number } = {}
) {
  const limit = options.limit ?? 100;
  const offset = options.offset ?? 0;
  return useQuery({
    queryKey: ["workspace-catalog-data", workspaceId, catalogId, limit, offset],
    queryFn: async () => {
      if (!workspaceId || !catalogId) return null;
      return api.fetchWorkspaceCatalogDataPreview(workspaceId, catalogId, { limit, offset });
    },
    enabled: Boolean(workspaceId && catalogId),
  });
}

export function useCreateWorkspaceCatalogFromSetup() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ workspaceId, seed }: { workspaceId: string; seed: IngestionCatalogSetupSeed }) =>
      api.createWorkspaceCatalogFromSetup(workspaceId, seed),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["workspace-catalog", variables.workspaceId] });
    },
  });
}

export function useDeleteWorkspaceCatalogEntry() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ workspaceId, catalogId }: { workspaceId: string; catalogId: string }) =>
      api.deleteWorkspaceCatalogEntry(workspaceId, catalogId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["workspace-catalog", variables.workspaceId] });
    },
  });
}

export function useCreateWorkspace() {
  const queryClient = useQueryClient();
  const addWorkspace = useWorkspaceStore((s) => s.addWorkspace);
  const setActiveWorkspace = useWorkspaceStore((s) => s.setActiveWorkspace);

  return useMutation({
    mutationFn: ({ title, description }: { title?: string; description?: string }) =>
      api.createWorkspace(title, description),
    onSuccess: (workspace) => {
      addWorkspace(workspace);
      setActiveWorkspace(workspace.id);
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}

export function useDeleteWorkspace() {
  const queryClient = useQueryClient();
  const removeWorkspace = useWorkspaceStore((s) => s.removeWorkspace);

  return useMutation({
    mutationFn: (workspaceId: string) => api.deleteWorkspace(workspaceId),
    onSuccess: (_, workspaceId) => {
      removeWorkspace(workspaceId);
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}

export function useRenameWorkspace() {
  const queryClient = useQueryClient();
  const updateWorkspaceTitle = useWorkspaceStore((s) => s.updateWorkspaceTitle);

  return useMutation({
    mutationFn: async ({ workspaceId, title }: { workspaceId: string; title: string }) => {
      const trimmedTitle = title.trim();
      if (!trimmedTitle) throw new Error("Workspace name cannot be empty");

      await api.updateWorkspaceTitle(workspaceId, trimmedTitle);
      return { workspaceId, title: trimmedTitle };
    },
    onSuccess: ({ workspaceId, title }) => {
      updateWorkspaceTitle(workspaceId, title);
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}

export function useSaveWorkspace() {
  const queryClient = useQueryClient();
  const setIsSaving = useUIStore((s) => s.setIsSaving);
  const setHasUnsavedChanges = useWorkspaceStore((s) => s.setHasUnsavedChanges);

  return useMutation({
    mutationFn: async () => {
      const snapshot = useWorkspaceStore.getState().getSnapshot();
      if (!snapshot) throw new Error("No active workspace to save");
      setIsSaving(true);
      return api.saveWorkspaceSnapshot(snapshot);
    },
    onSuccess: () => {
      setHasUnsavedChanges(false);
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
    },
    onSettled: () => {
      setIsSaving(false);
    },
  });
}
