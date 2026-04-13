import type { ChatSession, ChatMessage } from "@/types/chat";
import type { ChartAsset } from "@/types/chart";
import type { Workspace, WorkspaceSnapshot } from "@/types/workspace";
import {
  MOCK_SESSIONS,
  MOCK_MESSAGES,
  MOCK_CHART_ASSETS,
  MOCK_WORKSPACES,
  MOCK_WORKSPACE_SNAPSHOTS,
  generateMockResponse,
} from "./mock-data";
import { generateId } from "@/lib/utils";

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

let sessions = [...MOCK_SESSIONS];
let messages: Record<string, ChatMessage[]> = JSON.parse(JSON.stringify(MOCK_MESSAGES));
let assets = [...MOCK_CHART_ASSETS];
let workspaces = [...MOCK_WORKSPACES];
let snapshots: Record<string, WorkspaceSnapshot> = JSON.parse(JSON.stringify(MOCK_WORKSPACE_SNAPSHOTS));

// ─── Chat API ───────────────────────────────────────────────────────────────

export async function fetchSessions(): Promise<ChatSession[]> {
  await delay(300);
  return [...sessions].sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
}

export async function createSession(title?: string): Promise<ChatSession> {
  await delay(200);
  const session: ChatSession = {
    id: `session-${generateId()}`,
    title: title || "New Conversation",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    messageCount: 0,
  };
  sessions.unshift(session);
  messages[session.id] = [];
  return session;
}

export async function deleteSession(sessionId: string): Promise<void> {
  await delay(200);
  sessions = sessions.filter((s) => s.id !== sessionId);
  delete messages[sessionId];
}

export async function fetchMessages(sessionId: string): Promise<ChatMessage[]> {
  await delay(300);
  return messages[sessionId] ?? [];
}

export async function sendMessage(
  sessionId: string,
  content: string
): Promise<{ userMessage: ChatMessage; assistantMessage: ChatMessage; chartAsset?: ChartAsset }> {
  await delay(800 + Math.random() * 700);

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

  return { userMessage: userMsg, assistantMessage: assistantMsg, chartAsset: newAsset };
}

// ─── Chart Assets API ───────────────────────────────────────────────────────

export async function fetchChartAssets(): Promise<ChartAsset[]> {
  await delay(300);
  return [...assets].sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

export async function fetchChartAsset(assetId: string): Promise<ChartAsset | null> {
  await delay(200);
  return assets.find((a) => a.id === assetId) ?? null;
}

// ─── Workspace API ──────────────────────────────────────────────────────────

export async function fetchWorkspaces(): Promise<Workspace[]> {
  await delay(300);
  return [...workspaces].sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
}

export async function createWorkspace(title?: string, description?: string): Promise<Workspace> {
  await delay(200);
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
  return ws;
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
  await delay(200);
  workspaces = workspaces.filter((w) => w.id !== workspaceId);
  delete snapshots[workspaceId];
}

export async function fetchWorkspaceSnapshot(workspaceId: string): Promise<WorkspaceSnapshot | null> {
  await delay(300);
  return snapshots[workspaceId] ?? null;
}

export async function saveWorkspaceSnapshot(snapshot: WorkspaceSnapshot): Promise<void> {
  await delay(400);
  snapshots[snapshot.workspaceId] = JSON.parse(JSON.stringify(snapshot));
  const ws = workspaces.find((w) => w.id === snapshot.workspaceId);
  if (ws) {
    ws.updatedAt = new Date().toISOString();
    ws.nodeCount = snapshot.nodes.length;
  }
}

export async function updateWorkspaceTitle(workspaceId: string, title: string): Promise<void> {
  await delay(200);
  const ws = workspaces.find((w) => w.id === workspaceId);
  if (ws) {
    ws.title = title;
    ws.updatedAt = new Date().toISOString();
  }
}
