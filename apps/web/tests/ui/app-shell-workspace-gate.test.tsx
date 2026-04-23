import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "../../components/shared/app-shell";
import { useWorkspaceStore } from "../../stores/workspace-store";

const createWorkspaceMutate = vi.fn();

vi.mock("../../hooks/use-chat", () => ({
  useChatSessions: () => ({}),
  useChatMessages: () => ({ isLoading: false }),
  useCreateSession: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("../../hooks/use-chart-assets", () => ({
  useChartAssets: () => ({}),
}));

vi.mock("../../hooks/use-workspace", () => ({
  useWorkspaceList: () => ({ isLoading: false, isSuccess: true }),
  useCreateWorkspace: () => ({ mutate: createWorkspaceMutate, isPending: false }),
  useWorkspaceSnapshot: () => ({ data: null, isLoading: false }),
  useSaveWorkspace: () => ({ mutate: vi.fn(), isPending: false }),
  useRenameWorkspace: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteWorkspace: () => ({ mutate: vi.fn(), isPending: false }),
  useWorkspaceCatalog: () => ({ isLoading: false, data: [] }),
  useCreateWorkspaceCatalogFromSetup: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteWorkspaceCatalogEntry: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

describe("AppShell workspace gate", () => {
  beforeEach(() => {
    createWorkspaceMutate.mockReset();
    useWorkspaceStore.setState({
      workspaces: [],
      activeWorkspaceId: null,
      nodes: [],
      edges: [],
      viewport: { x: 0, y: 0, zoom: 1 },
      hasUnsavedChanges: false,
    });
  });

  it("forces workspace creation when no workspace exists", async () => {
    render(React.createElement(AppShell));

    expect(screen.getByText("Create Your First Workspace")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Workspace Name"), "North BI");
    await userEvent.click(screen.getByRole("button", { name: "Create Workspace" }));

    expect(createWorkspaceMutate).toHaveBeenCalledWith({ title: "North BI" });
  });
});
