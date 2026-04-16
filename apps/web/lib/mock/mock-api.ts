import type { ChatSession, ChatMessage } from "@/types/chat";
import type { ChartAsset } from "@/types/chart";
import type { TableCatalogEntry, Workspace, WorkspaceSnapshot } from "@/types/workspace";
import {
  MOCK_TABLE_CATALOG,
  MOCK_WORKSPACES,
  MOCK_WORKSPACE_SNAPSHOTS,
  generateMockResponse,
} from "./mock-data";
import { generateId } from "@/lib/utils";
import {
  CHAT_STORAGE_KEY,
  CHART_ASSETS_STORAGE_KEY,
  safeLoadFromStorage,
  safeSaveToStorage,
} from "@/lib/chat/session-storage";

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));
const WORKSPACE_STORAGE_KEY = "smarthrbi.mock.workspaces";

type StoredWorkspaceState = {
  version: 1;
  workspaces: Workspace[];
  snapshots: Record<string, WorkspaceSnapshot>;
  tableCatalogByWorkspace: Record<string, TableCatalogEntry[]>;
};

type StoredChatState = {
  version: 1;
  sessions: ChatSession[];
  activeSessionId: string | null;
  messagesBySession: Record<string, ChatMessage[]>;
};

type StoredAssetState = {
  version: 1;
  assets: ChartAsset[];
};

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));

let sessions: ChatSession[] = [];
let activeSessionId: string | null = null;
let messages: Record<string, ChatMessage[]> = {};
let assets: ChartAsset[] = [];
let workspaces = clone(MOCK_WORKSPACES);
let snapshots: Record<string, WorkspaceSnapshot> = clone(MOCK_WORKSPACE_SNAPSHOTS);
let tableCatalogByWorkspace: Record<string, TableCatalogEntry[]> = clone(MOCK_TABLE_CATALOG);
let hasLoadedPersistedWorkspaces = false;

function getWorkspaceStorage(): Storage | null {
  if (typeof window === "undefined") return null;

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function loadPersistedChatState() {
  const state = safeLoadFromStorage<Partial<StoredChatState>>(CHAT_STORAGE_KEY);
  if (!state || !Array.isArray(state.sessions)) {
    sessions = [];
    activeSessionId = null;
    messages = {};
    return;
  }

  const sessionIds = new Set(state.sessions.map((session) => session.id));
  sessions = clone(state.sessions);
  activeSessionId =
    typeof state.activeSessionId === "string" && sessionIds.has(state.activeSessionId)
      ? state.activeSessionId
      : sessions[0]?.id ?? null;
  messages = isMessageMap(state.messagesBySession)
    ? clone(
        Object.fromEntries(
          Object.entries(state.messagesBySession).filter(([sessionId]) => sessionIds.has(sessionId))
        )
      )
    : {};
}

function persistChatState() {
  safeSaveToStorage<StoredChatState>(CHAT_STORAGE_KEY, {
    version: 1,
    sessions,
    activeSessionId,
    messagesBySession: messages,
  });
}

function loadPersistedAssets() {
  const state = safeLoadFromStorage<Partial<StoredAssetState>>(CHART_ASSETS_STORAGE_KEY);
  assets = Array.isArray(state?.assets) ? clone(state.assets) : [];
}

function persistAssets() {
  safeSaveToStorage<StoredAssetState>(CHART_ASSETS_STORAGE_KEY, {
    version: 1,
    assets,
  });
}

function isMessageMap(value: unknown): value is Record<string, ChatMessage[]> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  return Object.values(value).every((item) => Array.isArray(item));
}

function loadPersistedWorkspaceState() {
  if (hasLoadedPersistedWorkspaces) return;
  hasLoadedPersistedWorkspaces = true;

  const storage = getWorkspaceStorage();
  if (!storage) return;

  try {
    const rawState = storage.getItem(WORKSPACE_STORAGE_KEY);
    if (!rawState) {
      persistWorkspaceState();
      return;
    }

    const parsed = JSON.parse(rawState) as Partial<StoredWorkspaceState>;
    if (!Array.isArray(parsed.workspaces) || typeof parsed.snapshots !== "object" || !parsed.snapshots) {
      return;
    }

    workspaces = parsed.workspaces;
    snapshots = parsed.snapshots as Record<string, WorkspaceSnapshot>;
    if (typeof parsed.tableCatalogByWorkspace === "object" && parsed.tableCatalogByWorkspace) {
      tableCatalogByWorkspace = parsed.tableCatalogByWorkspace as Record<string, TableCatalogEntry[]>;
    }
  } catch {
    storage.removeItem(WORKSPACE_STORAGE_KEY);
  }
}

function persistWorkspaceState() {
  const storage = getWorkspaceStorage();
  if (!storage) return;

  const state: StoredWorkspaceState = {
    version: 1,
    workspaces,
    snapshots,
    tableCatalogByWorkspace,
  };

  try {
    storage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Ignore quota or private browsing errors; the in-memory mock API still works.
  }
}

// ─── Chat API ───────────────────────────────────────────────────────────────

export async function fetchSessions(): Promise<ChatSession[]> {
  await delay(300);
  loadPersistedChatState();
  return [...sessions].sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
}

export async function createSession(title?: string): Promise<ChatSession> {
  await delay(200);
  loadPersistedChatState();
  const session: ChatSession = {
    id: `session-${generateId()}`,
    title: title || "New Conversation",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    messageCount: 0,
  };
  sessions.unshift(session);
  activeSessionId = session.id;
  messages[session.id] = [];
  persistChatState();
  return session;
}

export async function deleteSession(sessionId: string): Promise<void> {
  await delay(200);
  loadPersistedChatState();
  sessions = sessions.filter((s) => s.id !== sessionId);
  if (activeSessionId === sessionId) {
    activeSessionId = sessions[0]?.id ?? null;
  }
  delete messages[sessionId];
  persistChatState();
}

export async function fetchMessages(sessionId: string): Promise<ChatMessage[]> {
  await delay(300);
  loadPersistedChatState();
  return clone(messages[sessionId] ?? []);
}

export async function sendMessage(
  sessionId: string,
  content: string
): Promise<{ userMessage: ChatMessage; assistantMessage: ChatMessage; chartAsset?: ChartAsset }> {
  await delay(800 + Math.random() * 700);
  loadPersistedChatState();
  loadPersistedAssets();

  const userMsg: ChatMessage = {
    id: `msg-${generateId()}`,
    sessionId,
    role: "user",
    content,
    timestamp: new Date().toISOString(),
  };

  const mockResp = generateMockResponse(content);
  let newAsset: ChartAsset | undefined;

  if (mockResp.chartSpec) {
    newAsset = {
      id: `asset-${generateId()}`,
      title: mockResp.chartSpec.title,
      description: mockResp.chartSpec.subtitle,
      chartType: mockResp.chartSpec.chartType,
      spec: mockResp.chartSpec,
      sourceMeta: { sessionId, messageId: mockResp.messageId, prompt: content },
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    assets.push(newAsset);
    persistAssets();
  }

  const assistantMsg: ChatMessage = {
    id: mockResp.messageId,
    sessionId,
    role: "assistant",
    content: mockResp.content,
    chartAsset: newAsset
      ? { assetId: newAsset.id, title: newAsset.title, chartType: newAsset.chartType }
      : undefined,
    timestamp: new Date().toISOString(),
  };

  if (!messages[sessionId]) messages[sessionId] = [];
  messages[sessionId].push(userMsg, assistantMsg);

  const session = sessions.find((s) => s.id === sessionId);
  if (session) {
    session.messageCount += 2;
    session.lastMessage = content;
    session.updatedAt = new Date().toISOString();
  }
  persistChatState();

  return { userMessage: userMsg, assistantMessage: assistantMsg, chartAsset: newAsset };
}

// ─── Chart Assets API ───────────────────────────────────────────────────────

export async function fetchChartAssets(): Promise<ChartAsset[]> {
  await delay(300);
  loadPersistedAssets();
  return [...assets].sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

export async function fetchChartAsset(assetId: string): Promise<ChartAsset | null> {
  await delay(200);
  loadPersistedAssets();
  return assets.find((a) => a.id === assetId) ?? null;
}

// ─── Workspace API ──────────────────────────────────────────────────────────

export async function fetchWorkspaces(): Promise<Workspace[]> {
  await delay(300);
  loadPersistedWorkspaceState();
  return [...workspaces].sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
}

export async function createWorkspace(title?: string, description?: string): Promise<Workspace> {
  await delay(200);
  loadPersistedWorkspaceState();
  const ws: Workspace = {
    id: `ws-${generateId()}`,
    title: title || "Untitled Workspace",
    description,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    nodeCount: 0,
  };
  workspaces.unshift(ws);
  snapshots[ws.id] = {
    workspaceId: ws.id,
    nodes: [],
    edges: [],
    viewport: { x: 0, y: 0, zoom: 1 },
  };
  tableCatalogByWorkspace[ws.id] = [];
  persistWorkspaceState();
  return ws;
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
  await delay(200);
  loadPersistedWorkspaceState();
  workspaces = workspaces.filter((w) => w.id !== workspaceId);
  delete snapshots[workspaceId];
  delete tableCatalogByWorkspace[workspaceId];
  persistWorkspaceState();
}

export async function fetchWorkspaceSnapshot(workspaceId: string): Promise<WorkspaceSnapshot | null> {
  await delay(300);
  loadPersistedWorkspaceState();
  return snapshots[workspaceId] ?? null;
}

export async function saveWorkspaceSnapshot(snapshot: WorkspaceSnapshot): Promise<void> {
  await delay(400);
  loadPersistedWorkspaceState();
  snapshots[snapshot.workspaceId] = JSON.parse(JSON.stringify(snapshot));
  const ws = workspaces.find((w) => w.id === snapshot.workspaceId);
  if (ws) {
    ws.updatedAt = new Date().toISOString();
    ws.nodeCount = snapshot.nodes.length;
  }
  persistWorkspaceState();
}

export async function updateWorkspaceTitle(workspaceId: string, title: string): Promise<void> {
  await delay(200);
  loadPersistedWorkspaceState();
  const ws = workspaces.find((w) => w.id === workspaceId);
  if (ws) {
    ws.title = title;
    ws.updatedAt = new Date().toISOString();
    persistWorkspaceState();
  }
}

export async function fetchWorkspaceCatalog(workspaceId: string): Promise<TableCatalogEntry[]> {
  await delay(250);
  loadPersistedWorkspaceState();
  return clone(tableCatalogByWorkspace[workspaceId] ?? []);
}
