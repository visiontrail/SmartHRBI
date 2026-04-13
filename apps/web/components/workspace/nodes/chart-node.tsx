"use client";

import { memo, useState, useCallback } from "react";
import { type NodeProps, NodeResizeControl } from "@xyflow/react";
import { GripVertical, Trash2, Pencil, Check, X, Copy } from "lucide-react";
import { ChartPreview } from "@/components/charts/chart-preview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { generateId } from "@/lib/utils";
import type { ChartNodeData } from "@/types/workspace";

function ChartNodeComponent({ id, data, selected }: NodeProps) {
  const nodeData = data as unknown as ChartNodeData;
  const updateNode = useWorkspaceStore((s) => s.updateNode);
  const removeNode = useWorkspaceStore((s) => s.removeNode);
  const addNode = useWorkspaceStore((s) => s.addNode);
  const nodes = useWorkspaceStore((s) => s.nodes);

  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(nodeData.title);

  const handleSaveTitle = useCallback(() => {
    updateNode(id, { data: { ...nodeData, title: editTitle } as any });
    setIsEditing(false);
  }, [id, nodeData, editTitle, updateNode]);

  const handleDuplicate = useCallback(() => {
    const currentNode = nodes.find((n) => n.id === id);
    if (!currentNode) return;

    addNode({
      id: `node-${generateId()}`,
      type: "chartNode",
      position: { x: currentNode.position.x + 30, y: currentNode.position.y + 30 },
      data: { ...nodeData },
    });
  }, [id, nodeData, nodes, addNode]);

  return (
    <div
      className={`bg-ivory rounded-comfortable border overflow-hidden shadow-whisper transition-shadow ${
        selected ? "border-terracotta shadow-[0px_0px_0px_2px_#c96442]" : "border-border-cream"
      }`}
      style={{
        width: nodeData.width || 520,
        minHeight: nodeData.height || 380,
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border-cream bg-ivory cursor-grab">
        <GripVertical className="w-4 h-4 text-stone-gray shrink-0" />

        {isEditing ? (
          <div className="flex items-center gap-1 flex-1 min-w-0">
            <Input
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              className="h-6 text-xs"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSaveTitle();
                if (e.key === "Escape") {
                  setEditTitle(nodeData.title);
                  setIsEditing(false);
                }
              }}
            />
            <Button variant="ghost" size="icon-sm" onClick={handleSaveTitle}>
              <Check className="w-3 h-3 text-terracotta" />
            </Button>
            <Button variant="ghost" size="icon-sm" onClick={() => {
              setEditTitle(nodeData.title);
              setIsEditing(false);
            }}>
              <X className="w-3 h-3" />
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <span className="text-caption font-medium text-near-black truncate">
              {nodeData.title}
            </span>
            <Badge variant="outline" className="shrink-0 text-[10px]">
              {nodeData.chartType}
            </Badge>
          </div>
        )}

        <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <Button variant="ghost" size="icon-sm" onClick={() => setIsEditing(true)}>
            <Pencil className="w-3 h-3" />
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={handleDuplicate}>
            <Copy className="w-3 h-3" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => removeNode(id)}
            className="hover:text-error-crimson"
          >
            <Trash2 className="w-3 h-3" />
          </Button>
        </div>
      </div>

      {/* Chart */}
      <div className="p-1">
        <ChartPreview
          spec={nodeData.spec}
          height={(nodeData.height || 380) - 48}
        />
      </div>
    </div>
  );
}

export const ChartNode = memo(ChartNodeComponent);
