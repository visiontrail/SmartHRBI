"use client";

import { useQuery } from "@tanstack/react-query";
import { useAssetStore } from "@/stores/asset-store";
import * as api from "@/lib/mock/mock-api";

export function useChartAssets() {
  const setAssets = useAssetStore((s) => s.setAssets);

  return useQuery({
    queryKey: ["chart-assets"],
    queryFn: async () => {
      const assets = await api.fetchChartAssets();
      setAssets(assets);
      return assets;
    },
  });
}

export function useChartAsset(assetId: string | null) {
  return useQuery({
    queryKey: ["chart-asset", assetId],
    queryFn: () => (assetId ? api.fetchChartAsset(assetId) : null),
    enabled: !!assetId,
  });
}
