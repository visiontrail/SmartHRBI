import { create } from "zustand";
import type { ChartAsset } from "@/types/chart";
import {
  assetStorageKeyForUser,
  safeLoadFromStorage,
  safeSaveToStorage,
} from "@/lib/chat/session-storage";

type AssetState = {
  assets: ChartAsset[];
  setAssets: (assets: ChartAsset[]) => void;
  addAsset: (asset: ChartAsset) => void;
  getAsset: (assetId: string) => ChartAsset | undefined;
  initForUser: (userId: string) => void;
  clearForUser: () => void;
};

type PersistedAssetState = {
  version: 1;
  assets: ChartAsset[];
};

let _currentUserId: string | null = null;
let _initializedUserId: string | null = null;

function loadPersistedAssets(userId: string): ChartAsset[] {
  const state = safeLoadFromStorage<Partial<PersistedAssetState>>(assetStorageKeyForUser(userId));
  return Array.isArray(state?.assets) ? state.assets : [];
}

function persistAssets(assets: ChartAsset[]): void {
  if (!_currentUserId) return;
  safeSaveToStorage<PersistedAssetState>(assetStorageKeyForUser(_currentUserId), {
    version: 1,
    assets,
  });
}

export const useAssetStore = create<AssetState>((set, get) => ({
  assets: [],

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

  initForUser: (userId: string) => {
    if (_initializedUserId === userId) return;
    _currentUserId = userId;
    _initializedUserId = userId;
    set({ assets: loadPersistedAssets(userId) });
  },

  clearForUser: () => {
    _currentUserId = null;
    _initializedUserId = null;
    set({ assets: [] });
  },
}));
