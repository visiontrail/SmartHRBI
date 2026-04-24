"use client";

import { memo, useState, useCallback } from "react";
import { type NodeProps } from "@xyflow/react";
import { GripVertical, Trash2, Pencil, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { useI18n } from "@/lib/i18n/context";
import type { TextNodeData } from "@/types/workspace";
import { ResizableNode } from "./resizable-node";

const DEFAULT_TEXT_NODE_WIDTH = 400;
const DEFAULT_TEXT_NODE_HEIGHT = 80;
const MIN_TEXT_NODE_WIDTH = 220;
const MIN_TEXT_NODE_HEIGHT = 80;

function TextNodeComponent({ id, data, selected, width, height }: NodeProps) {
  const { t } = useI18n();
  const nodeData = data as unknown as TextNodeData;
  const updateNode = useWorkspaceStore((s) => s.updateNode);
  const removeNode = useWorkspaceStore((s) => s.removeNode);

  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(nodeData.content);

  const handleSave = useCallback(() => {
    updateNode(id, { data: { ...nodeData, content: editContent } as any });
    setIsEditing(false);
  }, [id, nodeData, editContent, updateNode]);

  const nodeWidth = width ?? nodeData.width ?? DEFAULT_TEXT_NODE_WIDTH;
  const nodeHeight = height ?? nodeData.height ?? DEFAULT_TEXT_NODE_HEIGHT;

  return (
    <div
      className={`relative flex flex-col bg-ivory rounded-comfortable border transition-shadow ${
        selected ? "border-terracotta shadow-[0px_0px_0px_2px_#c96442]" : "border-border-cream"
      }`}
      style={{
        width: nodeWidth,
        height: nodeHeight,
      }}
    >
      <ResizableNode
        id={id}
        selected={selected}
        minWidth={MIN_TEXT_NODE_WIDTH}
        minHeight={MIN_TEXT_NODE_HEIGHT}
      />

      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border-cream bg-ivory cursor-grab">
        <GripVertical className="w-3.5 h-3.5 text-stone-gray shrink-0" />
        <span className="text-label text-stone-gray flex-1">{t("workspace.textBlock")}</span>

        <div className="flex items-center gap-0.5 shrink-0">
          {isEditing ? (
            <Button variant="ghost" size="icon-sm" onClick={handleSave}>
              <Check className="w-3 h-3 text-terracotta" />
            </Button>
          ) : (
            <Button variant="ghost" size="icon-sm" onClick={() => setIsEditing(true)}>
              <Pencil className="w-3 h-3" />
            </Button>
          )}
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

      {/* Content */}
      <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
        {isEditing ? (
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            className="w-full h-full min-h-[48px] bg-transparent text-body-sm text-near-black resize-none focus:outline-none border border-border-cream rounded-subtle p-2"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter" && e.metaKey) handleSave();
              if (e.key === "Escape") {
                setEditContent(nodeData.content);
                setIsEditing(false);
              }
            }}
          />
        ) : (
          <p
            className="text-body-sm text-olive-gray leading-relaxed whitespace-pre-wrap cursor-pointer"
            onDoubleClick={() => setIsEditing(true)}
          >
            {nodeData.content}
          </p>
        )}
      </div>
    </div>
  );
}

export const TextNode = memo(TextNodeComponent);
