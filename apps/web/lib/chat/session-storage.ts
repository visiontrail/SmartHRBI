export const SESSION_STORAGE_KEY = "smarthrbi:chat-workbench:v1";
export const CHAT_STORAGE_KEY = "smarthrbi:chat:v1";
export const CHART_ASSETS_STORAGE_KEY = "smarthrbi:chart-assets:v1";

export function safeLoadFromStorage<T>(key: string): T | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function safeSaveToStorage<T>(key: string, value: T): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Ignore storage failures, UI should still function in memory.
  }
}
