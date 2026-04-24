"use client";

import { useCallback } from "react";
import { NodeResizer, type OnResizeEnd } from "@xyflow/react";
import { useWorkspaceStore } from "@/stores/workspace-store";

type ResizableNodeProps = {
  id: string;
  selected?: boolean;
  minWidth: number;
  minHeight: number;
};

export function ResizableNode({ id, selected, minWidth, minHeight }: ResizableNodeProps) {
  const updateNode = useWorkspaceStore((s) => s.updateNode);

  const handleResizeEnd = useCallback<OnResizeEnd>(
    (_event, params) => {
      updateNode(id, {
        data: {
          width: Math.round(params.width),
          height: Math.round(params.height),
        } as any,
      });
    },
    [id, updateNode]
  );

  if (!selected) {
    return null;
  }

  return (
    <NodeResizer
      minWidth={minWidth}
      minHeight={minHeight}
      color="#c96442"
      handleClassName="nodrag"
      lineClassName="nodrag"
      handleStyle={{
        width: 10,
        height: 10,
        borderRadius: 2,
        border: "2px solid #f8f4e8",
      }}
      lineStyle={{
        borderColor: "#c96442",
        borderWidth: 1,
      }}
      onResizeEnd={handleResizeEnd}
    />
  );
}
