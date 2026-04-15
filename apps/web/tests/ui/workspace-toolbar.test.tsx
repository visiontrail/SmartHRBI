import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { TooltipProvider } from "../../components/ui/tooltip";
import { WorkspaceToolbar } from "../../components/workspace/workspace-toolbar";
import { useWorkspaceStore } from "../../stores/workspace-store";

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>{ui}</TooltipProvider>
    </QueryClientProvider>
  );
}

describe("WorkspaceToolbar", () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      workspaces: [
        {
          id: "ws-test",
          title: "Original Canvas",
          createdAt: "2026-04-14T00:00:00.000Z",
          updatedAt: "2026-04-14T00:00:00.000Z",
          nodeCount: 0,
        },
      ],
      activeWorkspaceId: "ws-test",
      nodes: [],
      edges: [],
      viewport: { x: 0, y: 0, zoom: 1 },
      hasUnsavedChanges: false,
    });
  });

  afterEach(() => {
    useWorkspaceStore.setState({
      workspaces: [],
      activeWorkspaceId: null,
      nodes: [],
      edges: [],
      viewport: { x: 0, y: 0, zoom: 1 },
      hasUnsavedChanges: false,
    });
  });

  it("renames the active workspace from the canvas toolbar", async () => {
    renderWithProviders(<WorkspaceToolbar />);

    await userEvent.click(screen.getByRole("button", { name: "Rename workspace" }));
    const nameInput = screen.getByLabelText("Workspace name");

    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Renamed Canvas");
    await userEvent.click(screen.getByRole("button", { name: "Save workspace name" }));

    await waitFor(() => {
      expect(screen.getByText("Renamed Canvas")).toBeInTheDocument();
      expect(useWorkspaceStore.getState().workspaces[0].title).toBe("Renamed Canvas");
    });
  });
});
