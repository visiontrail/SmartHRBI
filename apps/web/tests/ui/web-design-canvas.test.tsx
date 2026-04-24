import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { TooltipProvider } from "../../components/ui/tooltip";
import { WorkspaceToolbar } from "../../components/workspace/workspace-toolbar";
import { DEFAULT_CANVAS_FORMAT } from "../../lib/workspace/canvas-formats";
import { useWorkspaceStore } from "../../stores/workspace-store";
import type { WorkspaceNode } from "../../types/workspace";

const chartNode: WorkspaceNode = {
  id: "node-chart",
  type: "chartNode",
  position: { x: 0, y: 0 },
  data: {
    type: "chart",
    assetId: "chart-1",
    title: "Headcount",
    chartType: "bar",
    width: 400,
    height: 280,
    spec: {
      chartType: "bar",
      title: "Headcount",
      echartsOption: { __rows__: [{ department: "HR", headcount: 4 }] },
    },
  },
};

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

describe("WebDesignCanvas state", () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      activeWorkspaceId: "ws-test",
      nodes: [chartNode],
      edges: [],
      viewport: { x: 0, y: 0, zoom: 1 },
      canvasFormat: DEFAULT_CANVAS_FORMAT,
      webDesign: {
        grid: {
          columns: 2,
          rows: [
            { id: "row-1", height: 400 },
            { id: "row-2", height: 400 },
          ],
        },
        zones: [],
        sidebar: [{ id: "section-1", label: "Section 1", anchorRowId: "row-1", children: [] }],
        preview: false,
      },
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
      canvasFormat: DEFAULT_CANVAS_FORMAT,
      hasUnsavedChanges: false,
    });
  });

  it("clamps grid zone resize to available columns and minimum span", () => {
    const store = useWorkspaceStore.getState();
    store.placeWebDesignZone("node-chart", 1, 0);
    const zoneId = useWorkspaceStore.getState().webDesign.zones[0].id;

    useWorkspaceStore.getState().resizeWebDesignZone(zoneId, 4, 0);

    const zone = useWorkspaceStore.getState().webDesign.zones[0];
    expect(zone.colSpan).toBe(1);
    expect(zone.rowSpan).toBe(1);
  });

  it("keeps sidebar nesting at two levels", () => {
    const store = useWorkspaceStore.getState();
    store.addWebDesignSidebarItem("section-1");
    const childId = useWorkspaceStore.getState().webDesign.sidebar[0].children[0].id;

    useWorkspaceStore.getState().addWebDesignSidebarItem(childId);

    const firstSection = useWorkspaceStore.getState().webDesign.sidebar[0];
    expect(firstSection.children).toHaveLength(1);
    expect(firstSection.children[0].children).toHaveLength(0);
  });

  it("switches to Web Page Design from the mode picker", async () => {
    useWorkspaceStore.setState({
      workspaces: [
        {
          id: "ws-test",
          title: "Original Canvas",
          createdAt: "2026-04-14T00:00:00.000Z",
          updatedAt: "2026-04-14T00:00:00.000Z",
          nodeCount: 1,
        },
      ],
    });

    renderWithProviders(<WorkspaceToolbar />);

    await userEvent.click(screen.getByRole("button", { name: "Canvas size" }));
    await userEvent.click(screen.getByText("Web Page Design"));

    await waitFor(() => {
      expect(useWorkspaceStore.getState().canvasFormat.id).toBe("web-design");
      expect(useWorkspaceStore.getState().hasUnsavedChanges).toBe(true);
    });
  });
});
