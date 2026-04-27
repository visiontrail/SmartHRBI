"use client";

import { useMemo, useState, type DragEvent, type MouseEvent as ReactMouseEvent } from "react";
import {
  BotMessageSquare,
  Check,
  ChevronDown,
  ChevronUp,
  Eye,
  Minus,
  PanelLeft,
  Plus,
  Send,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ChartPreview } from "@/components/charts/chart-preview";
import { cn } from "@/lib/utils";
import { extractChartRows } from "@/lib/workspace/chart-rows";
import { publishWorkspace, fetchPublishHistory, type PublishHistoryItem } from "@/lib/workspace/publish";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { ChartNodeData, WebDesignSidebarItem, WebDesignZone, WorkspaceNode } from "@/types/workspace";

const WEB_DESIGN_ZONE_MIME = "application/x-web-design-zone";

export function WebDesignCanvas() {
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId);
  const nodes = useWorkspaceStore((s) => s.nodes);
  const layout = useWorkspaceStore((s) => s.webDesign);
  const setColumns = useWorkspaceStore((s) => s.setWebDesignColumns);
  const addRow = useWorkspaceStore((s) => s.addWebDesignRow);
  const removeRow = useWorkspaceStore((s) => s.removeWebDesignRow);
  const setRowHeight = useWorkspaceStore((s) => s.setWebDesignRowHeight);
  const moveZone = useWorkspaceStore((s) => s.moveWebDesignZone);
  const resizeZone = useWorkspaceStore((s) => s.resizeWebDesignZone);
  const removeZone = useWorkspaceStore((s) => s.removeWebDesignZone);
  const setPreview = useWorkspaceStore((s) => s.setWebDesignPreview);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<PublishHistoryItem[]>([]);
  const [isPublishing, setIsPublishing] = useState(false);

  const chartNodes = useMemo(
    () => nodes.filter((node): node is WorkspaceNode & { data: ChartNodeData } => node.data.type === "chart"),
    [nodes]
  );
  const publishBlocked = layout.zones.some((zone) => {
    const node = chartNodes.find((item) => item.id === zone.nodeId);
    return !node || extractChartRows(node.data).length === 0;
  });

  const handlePublish = async () => {
    if (!activeWorkspaceId) return;
    setIsPublishing(true);
    try {
      const result = await publishWorkspace(activeWorkspaceId, layout, nodes);
      toast.success("Published", {
        description: `Version ${result.version} is ready.`,
        action: {
          label: "View Published Page",
          onClick: () => {
            window.location.href = `/portal?page=${encodeURIComponent(result.published_page_id)}`;
          },
        },
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Publish failed");
    } finally {
      setIsPublishing(false);
    }
  };

  const loadHistory = async () => {
    if (!activeWorkspaceId) return;
    setHistoryOpen((value) => !value);
    if (!historyOpen) {
      setHistory(await fetchPublishHistory(activeWorkspaceId));
    }
  };

  return (
    <div className="flex h-full min-h-0 bg-[#f7f4eb] text-[#2f332f]">
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#d8d1c1] bg-[#fffdf7] px-4 py-2">
          <div className="flex items-center gap-2">
            <PanelLeft className="h-4 w-4 text-[#996b35]" />
            <span className="text-sm font-semibold">Web Page Design</span>
            {!layout.preview && (
              <>
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    variant="outline"
                    size="icon-sm"
                    disabled={layout.grid.columns <= 2}
                    onClick={() => setColumns(layout.grid.columns - 1)}
                  >
                    <Minus className="h-3.5 w-3.5" />
                  </Button>
                  <span className="w-20 whitespace-nowrap text-center text-sm">{layout.grid.columns} columns</span>
                  <Button
                    variant="outline"
                    size="icon-sm"
                    onClick={() => {
                      if (layout.grid.columns >= 10) {
                        toast.error("最多只能添加 10 列");
                        return;
                      }
                      setColumns(layout.grid.columns + 1);
                    }}
                  >
                    <Plus className="h-3.5 w-3.5" />
                  </Button>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    variant="outline"
                    size="icon-sm"
                    disabled={layout.grid.rows.length <= 1}
                    onClick={() => removeRow(layout.grid.rows[layout.grid.rows.length - 1].id)}
                  >
                    <Minus className="h-3.5 w-3.5" />
                  </Button>
                  <span className="w-20 whitespace-nowrap text-center text-sm">{layout.grid.rows.length} rows</span>
                  <Button
                    variant="outline"
                    size="icon-sm"
                    onClick={() => {
                      if (layout.grid.rows.length >= 10) {
                        toast.error("最多只能添加 10 行");
                        return;
                      }
                      addRow();
                    }}
                  >
                    <Plus className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setPreview(!layout.preview)}>
              {layout.preview ? <Check className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              {layout.preview ? "Edit" : "Preview"}
            </Button>
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button
                    size="sm"
                    onClick={handlePublish}
                    disabled={publishBlocked || isPublishing || !layout.zones.length}
                  >
                    <Send className="h-4 w-4" />
                    Publish
                  </Button>
                </span>
              </TooltipTrigger>
              {publishBlocked && (
                <TooltipContent>All charts must have data before publishing</TooltipContent>
              )}
            </Tooltip>
            <Button variant="ghost" size="sm" onClick={loadHistory}>
              {historyOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              History
            </Button>
          </div>
        </div>

        {historyOpen && (
          <div className="border-b border-[#d8d1c1] bg-[#fffaf0] px-4 py-2 text-sm">
            {history.length === 0 ? (
              <span className="text-[#777166]">No published versions yet.</span>
            ) : (
              <div className="flex flex-wrap gap-2">
                {history.map((item) => (
                  <span key={item.page_id} className="rounded-md border border-[#d8d1c1] bg-white px-2 py-1">
                    v{item.version} · {new Date(item.published_at).toLocaleString()}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="grid min-h-0 flex-1 grid-cols-[220px_minmax(0,1fr)] overflow-hidden">
          <SidebarEditor preview={layout.preview} />
          <div className="overflow-auto p-5">
            <div className="relative">
              <div
                className={cn(
                  "grid rounded-md border border-[#d8d1c1] bg-white shadow-sm",
                  layout.preview && "border-transparent shadow-none"
                )}
                style={{
                  gridTemplateColumns: `repeat(${layout.grid.columns}, minmax(180px, 1fr))`,
                  gridTemplateRows: layout.grid.rows.map((row) => `${row.height}px`).join(" "),
                }}
              >
                {layout.grid.rows.map((row, rowIndex) =>
                  Array.from({ length: layout.grid.columns }).map((_, columnIndex) => (
                    <GridCell
                      key={`${row.id}-${columnIndex}`}
                      rowId={row.id}
                      rowIndex={rowIndex}
                      columnIndex={columnIndex}
                      preview={layout.preview}
                      onDropZone={(zoneId) => moveZone(zoneId, columnIndex, rowIndex)}
                    />
                  ))
                )}
                {layout.zones.map((zone) => (
                  <GridZone
                    key={zone.id}
                    zone={zone}
                    node={chartNodes.find((node) => node.id === zone.nodeId)}
                    preview={layout.preview}
                    onResize={(colSpan, rowSpan) => resizeZone(zone.id, colSpan, rowSpan)}
                    onRemove={() => removeZone(zone.id)}
                  />
                ))}
              </div>
              {!layout.preview &&
                layout.grid.rows.map((row, index) => {
                  const topPx = layout.grid.rows
                    .slice(0, index + 1)
                    .reduce((sum, r) => sum + r.height, 0);
                  return (
                    <RowResizeHandle
                      key={row.id}
                      rowId={row.id}
                      topPx={topPx}
                      currentHeight={row.height}
                      onSetHeight={(height) => setRowHeight(row.id, height)}
                    />
                  );
                })}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

function GridCell({
  rowId,
  rowIndex,
  columnIndex,
  preview,
  onDropZone,
}: {
  rowId: string;
  rowIndex: number;
  columnIndex: number;
  preview: boolean;
  onDropZone: (zoneId: string) => void;
}) {
  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    if (preview) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    if (preview) return;
    event.preventDefault();
    const zoneId = event.dataTransfer.getData(WEB_DESIGN_ZONE_MIME);
    if (zoneId) {
      onDropZone(zoneId);
    }
  };

  return (
    <div
      id={columnIndex === 0 ? rowId : undefined}
      aria-label={`Grid cell row ${rowIndex + 1} column ${columnIndex + 1}`}
      className={cn("border border-dashed border-[#e2dccf]", preview && "border-transparent")}
      style={{ gridColumn: columnIndex + 1, gridRow: rowIndex + 1 }}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    />
  );
}

function GridZone({
  zone,
  node,
  preview,
  onResize,
  onRemove,
}: {
  zone: WebDesignZone;
  node?: WorkspaceNode & { data: ChartNodeData };
  preview: boolean;
  onResize: (colSpan: number, rowSpan: number) => void;
  onRemove: () => void;
}) {
  if (!node) return null;
  const handleDragStart = (event: DragEvent<HTMLElement>) => {
    if (preview) {
      event.preventDefault();
      return;
    }
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData(WEB_DESIGN_ZONE_MIME, zone.id);
    event.dataTransfer.setData("text/plain", zone.id);
  };

  return (
    <section
      aria-label={`Chart zone ${node.data.title}`}
      draggable={!preview}
      onDragStart={handleDragStart}
      className={cn(
        "relative z-10 overflow-hidden rounded-md border border-[#cfc5b2] bg-white",
        !preview && "cursor-grab active:cursor-grabbing"
      )}
      style={{
        gridColumn: `${zone.column + 1} / span ${zone.colSpan}`,
        gridRow: `${zone.row + 1} / span ${zone.rowSpan}`,
      }}
    >
      {!preview && (
        <div className="absolute right-2 top-2 z-20 flex gap-1 rounded-md bg-white/90 p-1 shadow">
          <Button
            aria-label="Increase column span"
            variant="ghost"
            size="icon-sm"
            onClick={() => onResize(zone.colSpan + 1, zone.rowSpan)}
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
          <Button
            aria-label="Decrease column span"
            variant="ghost"
            size="icon-sm"
            onClick={() => onResize(zone.colSpan - 1, zone.rowSpan)}
          >
            <Minus className="h-3.5 w-3.5" />
          </Button>
          <Button
            aria-label="Increase row span"
            variant="ghost"
            size="icon-sm"
            onClick={() => onResize(zone.colSpan, zone.rowSpan + 1)}
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </Button>
          <Button
            aria-label="Decrease row span"
            variant="ghost"
            size="icon-sm"
            onClick={() => onResize(zone.colSpan, zone.rowSpan - 1)}
          >
            <ChevronUp className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={onRemove}>
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
      <div className="border-b border-[#eee8dc] px-3 py-2 text-sm font-semibold">{node.data.title}</div>
      <ChartPreview spec={node.data.spec} height={Math.max(180, zone.rowSpan * 260)} />
    </section>
  );
}

function SidebarEditor({ preview }: { preview: boolean }) {
  const layout = useWorkspaceStore((s) => s.webDesign);
  const addItem = useWorkspaceStore((s) => s.addWebDesignSidebarItem);
  const updateItem = useWorkspaceStore((s) => s.updateWebDesignSidebarItem);
  const removeItem = useWorkspaceStore((s) => s.removeWebDesignSidebarItem);

  if (preview) {
    return (
      <nav className="border-r border-[#e2dccf] bg-[#fbfaf5] p-4">
        {layout.sidebar.map((item) => (
          <a key={item.id} href={`#${item.anchorRowId}`} className="block py-2 text-sm font-medium">
            {item.label}
            {item.children.map((child) => (
              <span key={child.id} className="ml-4 block py-1 text-xs font-normal text-[#777166]">
                {child.label}
              </span>
            ))}
          </a>
        ))}
      </nav>
    );
  }

  return (
    <aside className="overflow-auto border-r border-[#d8d1c1] bg-[#fbfaf5] p-3">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-semibold">Page sidebar</span>
        <Button variant="outline" size="icon-sm" onClick={() => addItem()}>
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      <div className="space-y-3">
        {layout.sidebar.map((item) => (
          <SidebarItemEditor
            key={item.id}
            item={item}
            rows={layout.grid.rows}
            onAddChild={() => addItem(item.id)}
            onUpdate={updateItem}
            onRemove={removeItem}
          />
        ))}
      </div>
    </aside>
  );
}

function RowResizeHandle({
  rowId,
  topPx,
  currentHeight,
  onSetHeight,
}: {
  rowId: string;
  topPx: number;
  currentHeight: number;
  onSetHeight: (height: number) => void;
}) {
  const [dragging, setDragging] = useState(false);

  const handleMouseDown = (e: ReactMouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startHeight = currentHeight;
    setDragging(true);
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";

    const onMove = (ev: MouseEvent) => {
      onSetHeight(startHeight + ev.clientY - startY);
    };
    const onUp = () => {
      setDragging(false);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  return (
    <div
      aria-label={`Resize ${rowId}`}
      className={cn(
        "group absolute inset-x-0 z-30 flex h-3 cursor-row-resize select-none items-center",
        dragging && "z-40"
      )}
      style={{ top: topPx - 6 }}
      onMouseDown={handleMouseDown}
    >
      <div
        className={cn(
          "h-0.5 w-full transition-colors",
          dragging ? "bg-[#996b35]" : "bg-transparent group-hover:bg-[#d8d1c1]"
        )}
      />
    </div>
  );
}

function SidebarItemEditor({
  item,
  rows,
  onAddChild,
  onUpdate,
  onRemove,
}: {
  item: WebDesignSidebarItem;
  rows: { id: string }[];
  onAddChild: () => void;
  onUpdate: (itemId: string, updates: Partial<Omit<WebDesignSidebarItem, "id" | "children">>) => void;
  onRemove: (itemId: string) => void;
}) {
  return (
    <div className="space-y-2 rounded-md border border-[#d8d1c1] bg-white p-2">
      <Input value={item.label} onChange={(event) => onUpdate(item.id, { label: event.target.value })} />
      <select
        className="h-8 w-full rounded-md border border-[#d8d1c1] bg-white px-2 text-sm"
        value={item.anchorRowId}
        onChange={(event) => onUpdate(item.id, { anchorRowId: event.target.value })}
      >
        {rows.map((row) => (
          <option key={row.id} value={row.id}>
            {row.id}
          </option>
        ))}
      </select>
      <div className="flex gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={onAddChild}>
              <Plus className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Sidebar supports two levels only</TooltipContent>
        </Tooltip>
        <Button variant="ghost" size="icon-sm" onClick={() => onRemove(item.id)}>
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
      {item.children.map((child) => (
        <div key={child.id} className="ml-3 border-l border-[#d8d1c1] pl-2">
          <Input value={child.label} onChange={(event) => onUpdate(child.id, { label: event.target.value })} />
        </div>
      ))}
    </div>
  );
}
