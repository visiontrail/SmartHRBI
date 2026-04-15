"use client";

import { useCallback, useEffect, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
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
import { ChartNode } from "./nodes/chart-node";
import { TextNode } from "./nodes/text-node";
import type { WorkspaceNode } from "@/types/workspace";

const nodeTypes: NodeTypes = {
  chartNode: ChartNode,
  textNode: TextNode,
};

export function WorkspaceCanvas() {
  const storeNodes = useWorkspaceStore((s) => s.nodes);
  const storeEdges = useWorkspaceStore((s) => s.edges);
  const storeViewport = useWorkspaceStore((s) => s.viewport);
  const setStoreNodes = useWorkspaceStore((s) => s.setNodes);
  const setViewport = useWorkspaceStore((s) => s.setViewport);

  const [nodes, setNodes] = useNodesState(storeNodes as Node[]);
  const [edges, setEdges] = useEdgesState(storeEdges as Edge[]);
  const nodesRef = useRef<Node[]>(storeNodes as Node[]);

  const saveWorkspace = useSaveWorkspace();

  useEffect(() => {
    const nextNodes = storeNodes as Node[];
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

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        nodeTypes={nodeTypes}
        defaultViewport={storeViewport}
        onViewportChange={setViewport}
        fitView
        fitViewOptions={{ padding: 0.2 }}
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
