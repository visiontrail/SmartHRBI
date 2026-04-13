"use client";

import { useState } from "react";
import { GripVertical, Trash2, Pencil, Check, X, Maximize2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ChartPreview } from "./chart-preview";
import type { ChartSpec } from "@/types/chart";
import { cn } from "@/lib/utils";

type ChartCardProps = {
  title: string;
  chartType: string;
  spec: ChartSpec;
  width?: number;
  height?: number;
  onTitleChange?: (title: string) => void;
  onDelete?: () => void;
  onResize?: (width: number, height: number) => void;
  selected?: boolean;
  className?: string;
};

export function ChartCard({
  title,
  chartType,
  spec,
  width,
  height = 280,
  onTitleChange,
  onDelete,
  selected,
  className,
}: ChartCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(title);

  const handleSaveTitle = () => {
    onTitleChange?.(editTitle);
    setIsEditing(false);
  };

  const handleCancelEdit = () => {
    setEditTitle(title);
    setIsEditing(false);
  };

  return (
    <Card
      className={cn(
        "overflow-hidden transition-shadow",
        selected && "ring-2 ring-terracotta",
        className
      )}
      style={{ width }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border-cream bg-ivory">
        <GripVertical className="w-4 h-4 text-stone-gray cursor-grab shrink-0" />

        {isEditing ? (
          <div className="flex items-center gap-1 flex-1 min-w-0">
            <Input
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              className="h-7 text-caption"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSaveTitle();
                if (e.key === "Escape") handleCancelEdit();
              }}
            />
            <Button variant="ghost" size="icon-sm" onClick={handleSaveTitle}>
              <Check className="w-3.5 h-3.5 text-terracotta" />
            </Button>
            <Button variant="ghost" size="icon-sm" onClick={handleCancelEdit}>
              <X className="w-3.5 h-3.5" />
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <span className="text-body-sm font-medium text-near-black truncate">{title}</span>
            <Badge variant="outline" className="shrink-0 text-[10px]">{chartType}</Badge>
          </div>
        )}

        <div className="flex items-center gap-0.5 shrink-0">
          {!isEditing && onTitleChange && (
            <Button variant="ghost" size="icon-sm" onClick={() => setIsEditing(true)}>
              <Pencil className="w-3 h-3" />
            </Button>
          )}
          <Button variant="ghost" size="icon-sm">
            <Maximize2 className="w-3 h-3" />
          </Button>
          {onDelete && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={onDelete}
              className="hover:text-error-crimson"
            >
              <Trash2 className="w-3 h-3" />
            </Button>
          )}
        </div>
      </div>

      {/* Chart */}
      <CardContent className="p-0">
        <ChartPreview spec={spec} height={height} />
      </CardContent>
    </Card>
  );
}
