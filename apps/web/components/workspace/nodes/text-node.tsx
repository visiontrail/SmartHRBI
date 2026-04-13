"use client";

import { memo, useState, useCallback } from "react";
import { type NodeProps } from "@xyflow/react";
import { GripVertical, Trash2, Pencil, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { TextNodeData } from "@/types/workspace";

function TextNodeComponent({ id, data, selected }: NodeProps) {
  const nodeData = data as unknown as TextNodeData;
  const updateNode = useWorkspaceStore((s) => s.updateNode);
  const removeNode = useWorkspaceStore((s) => s.removeNode);

  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(nodeData.content);

  const handleSave = useCallback(() => {
    updateNode(id, { data: { ...nodeData, content: editContent } as any });
    setIsEditing(false);
  }, [id, nodeData, editContent, updateNode]);

  return (
    <div
      className={`bg-ivory rounded-comfortable border overflow-hidden transition-shadow ${
        selected ? "border-terracotta shadow-[0px_0px_0px_2px_#c96442]" : "border-border-cream"
      }`}
      style={{
        width: nodeData.width || 400,
        minHeight: nodeData.height || 80,
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border-cream bg-ivory cursor-grab">
        <GripVertical className="w-3.5 h-3.5 text-stone-gray shrink-0" />
        <span className="text-label text-stone-gray flex-1">Text Block</span>

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
      <div className="px-4 py-3">
        {isEditing ? (
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            className="w-full min-h-[48px] bg-transparent text-body-sm text-near-black resize-none focus:outline-none border border-border-cream rounded-subtle p-2"
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
