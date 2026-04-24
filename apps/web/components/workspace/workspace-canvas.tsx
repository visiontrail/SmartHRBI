"use client";

import { useCallback, useEffect, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  ViewportPortal,
  useNodesState,
  useEdgesState,
  applyNodeChanges,
  applyEdgeChanges,
  type NodeChange,
  type EdgeChange,
  type NodeTypes,
  type Node,
  type Edge,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { useSaveWorkspace } from "@/hooks/use-workspace";
import { getCanvasFormatPreset } from "@/lib/workspace/canvas-formats";
import { ChartNode } from "./nodes/chart-node";
import { TextNode } from "./nodes/text-node";
import { WebDesignCanvas } from "./web-design-canvas";
import type { WorkspaceNode } from "@/types/workspace";

const nodeTypes: NodeTypes = {
  chartNode: ChartNode,
  textNode: TextNode,
};

function normalizeWorkspaceNodes(nodes: WorkspaceNode[]): Node[] {
  return nodes.map((node) =>
    node.type === "textNode" ? { ...node, dragHandle: ".text-node-drag-handle" } : node
  ) as Node[];
}

export function WorkspaceCanvas() {
  const storeNodes = useWorkspaceStore((s) => s.nodes);
  const storeEdges = useWorkspaceStore((s) => s.edges);
  const storeViewport = useWorkspaceStore((s) => s.viewport);
  const canvasFormat = useWorkspaceStore((s) => s.canvasFormat);
  const setStoreNodes = useWorkspaceStore((s) => s.setNodes);
  const setViewport = useWorkspaceStore((s) => s.setViewport);

  const [nodes, setNodes] = useNodesState(normalizeWorkspaceNodes(storeNodes));
  const [edges, setEdges] = useEdgesState(storeEdges as Edge[]);
  const nodesRef = useRef<Node[]>(storeNodes as Node[]);

  const saveWorkspace = useSaveWorkspace();
  const canvasPreset = getCanvasFormatPreset(canvasFormat.id);

  useEffect(() => {
    const nextNodes = normalizeWorkspaceNodes(storeNodes);
    nodesRef.current = nextNodes;
    setNodes(nextNodes);
  }, [storeNodes, setNodes]);

  useEffect(() => {
    setEdges(storeEdges as Edge[]);
  }, [storeEdges, setEdges]);

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const nextNodes = applyNodeChanges(changes, nodesRef.current);
      nodesRef.current = nextNodes;
      setNodes(nextNodes);

      const hasMeaningfulChange = changes.some(
        (c) => c.type === "position" || c.type === "remove" || c.type === "dimensions"
      );
      if (hasMeaningfulChange) {
        setStoreNodes(nextNodes as WorkspaceNode[]);
      }
    },
    [setNodes, setStoreNodes]
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      setEdges((eds) => applyEdgeChanges(changes, eds));
    },
    [setEdges]
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        saveWorkspace.mutate();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [saveWorkspace]);

  if (canvasFormat.id === "web-design") {
    return <WebDesignCanvas />;
  }

  return (
    <div className="h-full w-full">
      {/* suppress ReactFlow selection outline for text nodes — editing panel provides its own indicator */}
      <style>{`.react-flow__node-textNode { outline: none !important; box-shadow: none !important; }`}</style>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        nodeTypes={nodeTypes}
        defaultViewport={storeViewport}
        onViewportChange={setViewport}
        deleteKeyCode={["Backspace", "Delete"]}
        multiSelectionKeyCode="Shift"
        selectionOnDrag
        panOnDrag={[1, 2]}
        minZoom={0.3}
        maxZoom={2}
        snapToGrid
        snapGrid={[10, 10]}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="#d1cfc5"
        />
        {canvasPreset.width && canvasPreset.height && (
          <ViewportPortal>
            <div
              aria-hidden="true"
              className="workspace-page-frame"
              style={{
                left: 0,
                top: 0,
                width: canvasPreset.width,
                height: canvasPreset.height,
              }}
            />
          </ViewportPortal>
        )}
        <Controls
          showInteractive={false}
        />
        <MiniMap
          nodeColor={() => "#c96442"}
          maskColor="rgba(245, 244, 237, 0.8)"
        />
      </ReactFlow>
    </div>
  );
}
