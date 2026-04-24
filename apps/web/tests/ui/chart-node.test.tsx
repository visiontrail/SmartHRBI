import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { TooltipProvider } from "../../components/ui/tooltip";
import { ChartNode } from "../../components/workspace/nodes/chart-node";
import { useWorkspaceStore } from "../../stores/workspace-store";
import type { ChartNodeData, WorkspaceNode } from "../../types/workspace";

const tableNodeData: ChartNodeData = {
  type: "chart",
  assetId: "asset-table",
  title: "Employee Table",
  chartType: "table",
  width: 520,
  height: 380,
  spec: {
    chartType: "table",
    title: "Employee Table",
    echartsOption: {
      __table__: true,
      __columns__: ["name", "department"],
      __rows__: [{ name: "Alice", department: "HR" }],
    },
  },
};

function renderChartNode(data: ChartNodeData) {
  return render(
    <TooltipProvider>
      <ChartNode
        {...({
          id: "node-table",
          data,
          selected: false,
          type: "chartNode",
          xPos: 0,
          yPos: 0,
          zIndex: 0,
          isConnectable: false,
          dragging: false,
        } as any)}
      />
    </TooltipProvider>
  );
}

describe("ChartNode", () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      activeWorkspaceId: "ws-test",
      nodes: [
        {
          id: "node-table",
          type: "chartNode",
          position: { x: 0, y: 0 },
          data: tableNodeData,
        },
      ] as WorkspaceNode[],
      edges: [
        {
          id: "edge-table",
          source: "node-table",
          target: "node-other",
        },
      ],
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

  it("deletes the corresponding table node from the canvas", async () => {
    renderChartNode(tableNodeData);

    await userEvent.click(screen.getByRole("button", { name: "Delete table: Employee Table" }));

    await waitFor(() => {
      const state = useWorkspaceStore.getState();
      expect(state.nodes).toHaveLength(0);
      expect(state.edges).toHaveLength(0);
      expect(state.hasUnsavedChanges).toBe(true);
    });
  });
});
