import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TextNode } from "../../components/workspace/nodes/text-node";
import { useWorkspaceStore } from "../../stores/workspace-store";
import type { TextNodeData, WorkspaceNode } from "../../types/workspace";

vi.mock("../../components/workspace/nodes/resizable-node", () => ({
  ResizableNode: () => <div data-testid="resize-controls" />,
}));

const textNodeData: TextNodeData = {
  type: "text",
  content: "Revenue grew steadily.",
  fontSize: 18,
  fontWeight: "normal",
  color: "#3f3d39",
  width: 480,
  height: 220,
};

function renderTextNode(selected = true) {
  return render(
    <TextNode
      {...({
        id: "node-text",
        data: textNodeData,
        selected,
        type: "textNode",
        width: 480,
        height: 220,
        xPos: 0,
        yPos: 0,
        zIndex: 0,
        isConnectable: false,
        dragging: false,
      } as any)}
    />
  );
}

describe("TextNode", () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      activeWorkspaceId: "ws-test",
      nodes: [
        {
          id: "node-text",
          type: "textNode",
          position: { x: 0, y: 0 },
          width: 480,
          height: 220,
          data: textNodeData,
        },
      ] as WorkspaceNode[],
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

  it("keeps editing open when the text area blurs for resize handles", async () => {
    renderTextNode();

    await userEvent.click(screen.getByRole("button", { name: "Edit text block" }));
    const editor = screen.getByRole("textbox");

    fireEvent.blur(editor);

    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByTestId("resize-controls")).toBeInTheDocument();
  });
});
