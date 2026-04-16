import { create } from "zustand";
import type { ChartAsset } from "@/types/chart";
import {
  CHART_ASSETS_STORAGE_KEY,
  safeLoadFromStorage,
  safeSaveToStorage,
} from "@/lib/chat/session-storage";

type AssetState = {
  assets: ChartAsset[];
  setAssets: (assets: ChartAsset[]) => void;
  addAsset: (asset: ChartAsset) => void;
  getAsset: (assetId: string) => ChartAsset | undefined;
};

type PersistedAssetState = {
  version: 1;
  assets: ChartAsset[];
};

function loadPersistedAssets(): ChartAsset[] {
  const state = safeLoadFromStorage<Partial<PersistedAssetState>>(CHART_ASSETS_STORAGE_KEY);
  return Array.isArray(state?.assets) ? state.assets : [];
}

function persistAssets(assets: ChartAsset[]): void {
  safeSaveToStorage<PersistedAssetState>(CHART_ASSETS_STORAGE_KEY, {
    version: 1,
    assets,
  });
}

const persistedAssets = loadPersistedAssets();

export const useAssetStore = create<AssetState>((set, get) => ({
  assets: persistedAssets,

  setAssets: (assets) => {
    persistAssets(assets);
    set({ assets });
  },

  addAsset: (asset) =>
    set((state) => {
      if (state.assets.some((a) => a.id === asset.id)) return state;
      const assets = [asset, ...state.assets];
      persistAssets(assets);
      return { assets };
    }),

  getAsset: (assetId) => get().assets.find((a) => a.id === assetId),
}));
