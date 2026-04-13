import { create } from "zustand";
import type { ChartAsset } from "@/types/chart";

type AssetState = {
  assets: ChartAsset[];
  setAssets: (assets: ChartAsset[]) => void;
  addAsset: (asset: ChartAsset) => void;
  getAsset: (assetId: string) => ChartAsset | undefined;
};

export const useAssetStore = create<AssetState>((set, get) => ({
  assets: [],

  setAssets: (assets) => set({ assets }),

  addAsset: (asset) =>
    set((state) => {
      if (state.assets.some((a) => a.id === asset.id)) return state;
      return { assets: [asset, ...state.assets] };
    }),

  getAsset: (assetId) => get().assets.find((a) => a.id === assetId),
}));
