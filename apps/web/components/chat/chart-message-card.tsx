"use client";

import { useCallback } from "react";
import { LayoutDashboard, Copy, RefreshCw, Maximize2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { ChartPreview } from "@/components/charts/chart-preview";
import { useAssetStore } from "@/stores/asset-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { useUIStore } from "@/stores/ui-store";
import { generateId } from "@/lib/utils";
import { useI18n } from "@/lib/i18n/context";
import { getCanvasFormatPreset } from "@/lib/workspace/canvas-formats";
import { toast } from "sonner";
import type { ChartNodeData } from "@/types/workspace";

const DEFAULT_CHART_NODE_WIDTH = 520;
const DEFAULT_CHART_NODE_HEIGHT = 380;

type ChartMessageCardProps = {
  assetId: string;
  title: string;
  chartType: string;
};

export function ChartMessageCard({ assetId, title, chartType }: ChartMessageCardProps) {
  const { t } = useI18n();
  const getAsset = useAssetStore((s) => s.getAsset);
  const addNode = useWorkspaceStore((s) => s.addNode);
  const addNodeToWebDesign = useWorkspaceStore((s) => s.addNodeToWebDesign);
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId);
  const nodes = useWorkspaceStore((s) => s.nodes);
  const canvasFormat = useWorkspaceStore((s) => s.canvasFormat);
  const setActivePanel = useUIStore((s) => s.setActivePanel);

  const asset = getAsset(assetId);
  const canvasName = t(getCanvasFormatPreset(canvasFormat.id).labelKey);

  const handleAddToCanvas = useCallback(() => {
    if (!asset) {
      toast.error(t("chat.toast.chartAssetNotFound"));
      return;
    }

    if (!activeWorkspaceId) {
      toast.error(t("chat.toast.noWorkspace"));
      return;
    }

    const offsetX = 50 + (nodes.length % 3) * 560;
    const offsetY = 50 + Math.floor(nodes.length / 3) * 420;

    const nodeData: ChartNodeData = {
      type: "chart",
      assetId: asset.id,
      title: asset.title,
      chartType: asset.chartType,
      spec: asset.spec,
      width: DEFAULT_CHART_NODE_WIDTH,
      height: DEFAULT_CHART_NODE_HEIGHT,
    };

    const node = {
      id: `node-${generateId()}`,
      type: "chartNode",
      position: { x: offsetX, y: offsetY },
      width: DEFAULT_CHART_NODE_WIDTH,
      height: DEFAULT_CHART_NODE_HEIGHT,
      initialWidth: DEFAULT_CHART_NODE_WIDTH,
      initialHeight: DEFAULT_CHART_NODE_HEIGHT,
      data: nodeData,
    };

    if (canvasFormat.id === "web-design") {
      addNodeToWebDesign(node);
    } else {
      addNode(node);
    }

    setActivePanel("both");
    toast.success(t("chat.toast.addedToWorkspace", { title: asset.title, canvasName }));
  }, [asset, activeWorkspaceId, nodes.length, canvasFormat.id, addNode, addNodeToWebDesign, setActivePanel, t, canvasName]);

  return (
    <Card className="w-full max-w-lg overflow-hidden animate-fade-in">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-body font-sans font-semibold">{title}</CardTitle>
          <Badge variant="secondary">{chartType}</Badge>
        </div>
      </CardHeader>

      <CardContent className="pb-3">
        {asset ? (
          <div className="rounded-comfortable overflow-hidden border border-border-cream bg-parchment">
            <ChartPreview spec={asset.spec} height={220} />
          </div>
        ) : (
          <div className="h-[220px] rounded-comfortable bg-warm-sand flex items-center justify-center">
            <p className="text-caption text-stone-gray">{t("chat.chartPreviewUnavailable")}</p>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex items-center gap-2 mt-3">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="default" size="sm" onClick={handleAddToCanvas}>
                <LayoutDashboard className="w-3.5 h-3.5" />
                {t("chat.addToCanvas", { canvasName })}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t("chat.addToCanvasTooltip", { canvasName })}</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-sm">
                <Copy className="w-3.5 h-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t("chat.duplicate")}</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-sm">
                <RefreshCw className="w-3.5 h-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t("chat.regenerate")}</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-sm">
                <Maximize2 className="w-3.5 h-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t("chat.fullScreen")}</TooltipContent>
          </Tooltip>
        </div>
      </CardContent>
    </Card>
  );
}
