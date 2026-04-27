import { afterEach, describe, expect, it, vi } from "vitest";

import { WORKSPACE_SELECTION_STORAGE_KEY } from "../../lib/chat/session-storage";
import type { Workspace } from "../../types/workspace";

const workspaces: Workspace[] = [
  {
    id: "workspace-1",
    title: "Top Workspace",
    createdAt: "2026-04-24T00:00:00.000Z",
    updatedAt: "2026-04-24T00:00:00.000Z",
    nodeCount: 0,
  },
  {
    id: "workspace-2",
    title: "Selected Workspace",
    createdAt: "2026-04-25T00:00:00.000Z",
    updatedAt: "2026-04-25T00:00:00.000Z",
    nodeCount: 0,
  },
];

describe("workspace store selection persistence", () => {
  afterEach(() => {
    window.localStorage.clear();
    vi.resetModules();
  });

  it("restores the persisted active workspace instead of falling back to the first workspace", async () => {
    window.localStorage.setItem(
      WORKSPACE_SELECTION_STORAGE_KEY,
      JSON.stringify({ version: 1, activeWorkspaceId: "workspace-2" })
    );
    vi.resetModules();

    const { useWorkspaceStore } = await import("../../stores/workspace-store");

    expect(useWorkspaceStore.getState().activeWorkspaceId).toBe("workspace-2");

    useWorkspaceStore.getState().setWorkspaces(workspaces);

    expect(useWorkspaceStore.getState().activeWorkspaceId).toBe("workspace-2");
  });

  it("clears a persisted active workspace when it no longer exists", async () => {
    window.localStorage.setItem(
      WORKSPACE_SELECTION_STORAGE_KEY,
      JSON.stringify({ version: 1, activeWorkspaceId: "missing-workspace" })
    );
    vi.resetModules();

    const { useWorkspaceStore } = await import("../../stores/workspace-store");

    useWorkspaceStore.getState().setWorkspaces(workspaces);

    expect(useWorkspaceStore.getState().activeWorkspaceId).toBeNull();
  });

  it("persists changes when users select another workspace", async () => {
    vi.resetModules();

    const { useWorkspaceStore } = await import("../../stores/workspace-store");

    useWorkspaceStore.getState().setActiveWorkspace("workspace-2");

    expect(JSON.parse(window.localStorage.getItem(WORKSPACE_SELECTION_STORAGE_KEY) ?? "{}")).toEqual({
      version: 1,
      activeWorkspaceId: "workspace-2",
    });
  });
});
