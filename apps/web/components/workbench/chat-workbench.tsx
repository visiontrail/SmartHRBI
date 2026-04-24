"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { GenUIRegistry } from "../genui/registry";
import { EmptyPanel, ErrorPanel } from "../genui/state-panels";
import { getAuthorizationHeader } from "../../lib/auth/session";
import { parseSSEStream } from "../../lib/chat/sse";
import {
  SESSION_STORAGE_KEY,
  safeLoadFromStorage,
  safeSaveToStorage
} from "../../lib/chat/session-storage";

type ChatWorkbenchProps = {
  apiBaseUrl: string;
};

type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
};

type StreamStatus = "idle" | "streaming";
type SaveStatus = "idle" | "saving";

type StoredWorkbenchState = {
  version: 1;
  conversationId: string;
  agentSessionId: string | null;
  userId: string;
  projectId: string;
  role: string;
  department: string;
  clearance: number;
  datasetTable: string;
  composer: string;
  messages: Message[];
  activeSpec: unknown;
  lastToolEvent: Record<string, unknown> | null;
  toolTrace: Record<string, unknown>[];
};

const DEFAULT_USER_ID = "demo-user";
const DEFAULT_PROJECT_ID = "demo-project";
const DEFAULT_ROLE = "hr";
const DEFAULT_DEPARTMENT = "HR";
const DEFAULT_CLEARANCE = 1;
const DEFAULT_DATASET = "employees_wide";

export function ChatWorkbench({ apiBaseUrl }: ChatWorkbenchProps) {
  const restoredStateRef = useRef<StoredWorkbenchState | null | undefined>(undefined);
  if (restoredStateRef.current === undefined) {
    restoredStateRef.current = loadStoredWorkbenchState();
  }
  const restoredState = restoredStateRef.current;

  const [conversationId, setConversationId] = useState<string>(restoredState?.conversationId ?? makeRequestId());
  const [agentSessionId, setAgentSessionId] = useState<string | null>(restoredState?.agentSessionId ?? null);
  const [userId, setUserId] = useState(restoredState?.userId ?? DEFAULT_USER_ID);
  const [projectId, setProjectId] = useState(restoredState?.projectId ?? DEFAULT_PROJECT_ID);
  const [role, setRole] = useState(restoredState?.role ?? DEFAULT_ROLE);
  const [department, setDepartment] = useState(restoredState?.department ?? DEFAULT_DEPARTMENT);
  const [clearance, setClearance] = useState(restoredState?.clearance ?? DEFAULT_CLEARANCE);
  const [datasetTable, setDatasetTable] = useState(restoredState?.datasetTable ?? DEFAULT_DATASET);
  const [composer, setComposer] = useState(restoredState?.composer ?? "");
  const [messages, setMessages] = useState<Message[]>(restoredState?.messages ?? []);
  const [activeSpec, setActiveSpec] = useState<unknown>(restoredState?.activeSpec ?? null);
  const [lastToolEvent, setLastToolEvent] = useState<Record<string, unknown> | null>(
    restoredState?.lastToolEvent ?? null
  );
  const [toolTrace, setToolTrace] = useState<Record<string, unknown>[]>(restoredState?.toolTrace ?? []);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("idle");
  const [streamError, setStreamError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [shareLink, setShareLink] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  useEffect(() => {
    safeSaveToStorage<StoredWorkbenchState>(SESSION_STORAGE_KEY, {
      version: 1,
      conversationId,
      agentSessionId,
      userId,
      projectId,
      role,
      department,
      clearance,
      datasetTable,
      composer,
      messages,
      activeSpec,
      lastToolEvent,
      toolTrace
    });
  }, [
    activeSpec,
    agentSessionId,
    clearance,
    composer,
    conversationId,
    datasetTable,
    department,
    lastToolEvent,
    messages,
    projectId,
    role,
    toolTrace,
    userId
  ]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = composer.trim();
    if (!message || streamStatus === "streaming") {
      return;
    }

    setStreamError(null);
    setStreamStatus("streaming");
    setComposer("");
    setToolTrace([]);
    setMessages((previous) => [...previous, { id: makeRequestId(), role: "user", text: message }]);

    try {
      const authorizationHeader = await getAuthorizationHeader(apiBaseUrl, {
        userId,
        projectId,
        role,
        department,
        clearance
      });
      const response = await fetch(`${apiBaseUrl}/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authorizationHeader
        },
        body: JSON.stringify({
          user_id: userId,
          project_id: projectId,
          role,
          department,
          clearance,
          dataset_table: datasetTable,
          message,
          conversation_id: conversationId,
          request_id: makeRequestId()
        })
      });

      if (!response.ok || !response.body) {
        throw new Error(`stream_failed_${response.status}`);
      }

      for await (const streamEvent of parseSSEStream(response.body)) {
        const payload = isRecord(streamEvent.data) ? streamEvent.data : {};
        syncAgentSessionId(payload);
        if (streamEvent.event === "planning") {
          appendAssistantMessage(String(payload.text ?? "Planning the analysis..."));
          continue;
        }
        if (streamEvent.event === "reasoning") {
          if (payload.compatibility_mirror === true) {
            continue;
          }
          appendAssistantMessage(String(payload.text ?? "Reasoning in progress..."));
          continue;
        }
        if (streamEvent.event === "tool_use") {
          appendToolTrace(payload);
          continue;
        }
        if (streamEvent.event === "tool_result") {
          appendToolTrace(payload);
          setLastToolEvent(payload);
          continue;
        }
        if (streamEvent.event === "tool") {
          setLastToolEvent(payload);
          continue;
        }
        if (streamEvent.event === "spec") {
          setActiveSpec(payload.spec ?? null);
          continue;
        }
        if (streamEvent.event === "error") {
          const messageText = String(payload.message ?? "请求失败，请稍后重试。");
          appendAssistantMessage(messageText);
          setStreamError(messageText);
          continue;
        }
        if (streamEvent.event === "final") {
          appendAssistantMessage(String(payload.text ?? "Response completed."));
          if (payload.status === "failed") {
            setStreamError(String(payload.text ?? "请求失败，请稍后重试。"));
          }
        }
      }
    } catch (error) {
      setStreamError(error instanceof Error ? error.message : "未知流式错误");
    } finally {
      setStreamStatus("idle");
    }
  }

  async function handleSaveView() {
    if (!activeSpec || saveStatus === "saving") {
      return;
    }

    setSaveStatus("saving");
    setSaveError(null);
    try {
      const authorizationHeader = await getAuthorizationHeader(apiBaseUrl, {
        userId,
        projectId,
        role,
        department,
        clearance
      });
      const response = await fetch(`${apiBaseUrl}/views`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authorizationHeader
        },
        body: JSON.stringify({
          user_id: userId,
          project_id: projectId,
          role,
          department,
          clearance,
          dataset_table: datasetTable,
          title: "Saved from Workbench",
          conversation_id: conversationId,
          ai_state: {
            conversation_id: conversationId,
            user_id: userId,
            project_id: projectId,
            role,
            department,
            clearance,
            dataset_table: datasetTable,
            messages,
            active_spec: activeSpec,
            last_tool_event: lastToolEvent,
            tool_trace: toolTrace,
            agent_session_id: agentSessionId
          }
        })
      });

      const payload = await response.json();
      if (!response.ok) {
        const detail = isRecord(payload.detail) ? payload.detail : null;
        throw new Error(String(detail?.message ?? payload.message ?? "save_view_failed"));
      }

      const path = String(payload.share_url ?? payload.share_path ?? "");
      if (!path) {
        throw new Error("missing_share_url");
      }
      setShareLink(path);
      appendAssistantMessage(`View saved: ${path}`);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaveStatus("idle");
    }
  }

  function appendAssistantMessage(text: string) {
    setMessages((previous) => [...previous, { id: makeRequestId(), role: "assistant", text }]);
  }

  function appendToolTrace(payload: Record<string, unknown>) {
    setToolTrace((previous) => [...previous, payload]);
  }

  function syncAgentSessionId(payload: Record<string, unknown>) {
    const nextAgentSessionId = String(payload.agent_session_id ?? "").trim();
    if (nextAgentSessionId) {
      setAgentSessionId(nextAgentSessionId);
    }
  }

  const streamLabel = useMemo(() => {
    if (streamStatus === "streaming") {
      return "Streaming...";
    }
    return "Idle";
  }, [streamStatus]);

  return (
    <main className="workspace">
      <header className="workspace-header">
        <h1>Cognitrix Chat Workbench</h1>
        <p>状态: {streamLabel}</p>
      </header>

      <section className="workspace-top-grid">
        <section className="workspace-card workspace-card--chat">
          <h2>Chat</h2>
          <div className="chat-log" data-testid="chat-log">
            {messages.length === 0 ? <p className="muted">先输入一个问题开始分析。</p> : null}
            {messages.map((message) => (
              <article
                key={message.id}
                className={`chat-message ${message.role === "user" ? "chat-message--user" : "chat-message--assistant"}`}
              >
                <strong>{message.role === "user" ? "You" : "AI"}</strong>
                <p>{message.text}</p>
              </article>
            ))}
          </div>
          <form className="composer" onSubmit={handleSubmit}>
            <textarea
              aria-label="Chat Input"
              placeholder="例如：按部门查看离职率趋势"
              value={composer}
              onChange={(event) => setComposer(event.target.value)}
            />
            <button type="submit" disabled={streamStatus === "streaming"}>
              {streamStatus === "streaming" ? "Running..." : "Send"}
            </button>
          </form>
        </section>

        <section className="workspace-card workspace-card--visualization">
          <h2>Visualization</h2>
          <div className="visualization-stage">
            {streamError ? (
              <ErrorPanel description={streamError} />
            ) : !activeSpec && streamStatus === "idle" ? (
              <EmptyPanel title="Chart not generated yet" />
            ) : (
              <GenUIRegistry rawSpec={activeSpec} isStreaming={streamStatus === "streaming"} />
            )}
          </div>
          <section className="share-actions">
            <button type="button" onClick={handleSaveView} disabled={!activeSpec || saveStatus === "saving"}>
              {saveStatus === "saving" ? "Saving..." : "Save & Share"}
            </button>
            {saveError ? <p className="share-error">{saveError}</p> : null}
            {shareLink ? (
              <p className="share-link">
                Share Link: <a href={shareLink}>{shareLink}</a>
              </p>
            ) : null}
          </section>
        </section>
      </section>

      <section className="workspace-card workspace-card--dataset">
        <h2>Dataset Context</h2>
        <div className="dataset-context-grid">
          <section className="dataset-context-column dataset-context-column--upload">
            <section className="upload-panel">
              <div className="upload-panel__copy">
                <h3>Excel Upload</h3>
                <p>上传 `.xlsx` 请使用聊天输入框的附件入口。文件会进入 Agentic ingestion，先生成写入方案，再经审批执行。</p>
              </div>
              <p className="upload-panel__hint">旧的自动解析并直接写表流程已关闭。</p>
            </section>
          </section>

          <section className="dataset-context-column dataset-context-column--session">
            <h3>Session Context</h3>
            <div className="context-grid">
              <label>
                User ID
                <input value={userId} onChange={(event) => setUserId(event.target.value)} />
              </label>
              <label>
                Project ID
                <input value={projectId} onChange={(event) => setProjectId(event.target.value)} />
              </label>
              <label>
                Role
                <select aria-label="Role" value={role} onChange={(event) => setRole(event.target.value)}>
                  <option value="admin">admin</option>
                  <option value="hr">hr</option>
                  <option value="pm">pm</option>
                  <option value="viewer">viewer</option>
                </select>
              </label>
              <label>
                Department
                <input value={department} onChange={(event) => setDepartment(event.target.value)} />
              </label>
              <label>
                Clearance
                <input
                  aria-label="Clearance"
                  type="number"
                  min={0}
                  step={1}
                  value={clearance}
                  onChange={(event) => setClearance(Number(event.target.value) || 0)}
                />
              </label>
              <label>
                Dataset Table
                <input value={datasetTable} onChange={(event) => setDatasetTable(event.target.value)} />
              </label>
              <label>
                Conversation ID
                <input value={conversationId} onChange={(event) => setConversationId(event.target.value)} />
              </label>
            </div>
          </section>

          <section className="dataset-context-column dataset-context-column--tools">
            <section className="tool-status" data-testid="tool-status">
              <h3>Tool Trace</h3>
              {agentSessionId ? (
                <p className="muted">
                  Agent Session: <strong>{agentSessionId}</strong>
                </p>
              ) : null}
              {toolTrace.length > 0 ? (
                <pre>{JSON.stringify(toolTrace, null, 2)}</pre>
              ) : lastToolEvent ? (
                <pre>{JSON.stringify(lastToolEvent, null, 2)}</pre>
              ) : (
                <p className="muted">暂无工具调用事件。</p>
              )}
            </section>
          </section>
        </div>
      </section>
    </main>
  );
}

function makeRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `req-${Math.random().toString(16).slice(2)}-${Date.now()}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function loadStoredWorkbenchState(): StoredWorkbenchState | null {
  const state = safeLoadFromStorage<Partial<StoredWorkbenchState>>(SESSION_STORAGE_KEY);
  if (!state || typeof state.conversationId !== "string" || !state.conversationId.trim()) {
    return null;
  }

  const messages = Array.isArray(state.messages) ? state.messages.filter(isMessage) : [];
  const toolTrace = Array.isArray(state.toolTrace) ? state.toolTrace.filter(isRecord) : [];
  const lastToolEvent = isRecord(state.lastToolEvent) ? state.lastToolEvent : null;
  const clearance = Number(state.clearance);

  return {
    version: 1,
    conversationId: state.conversationId,
    agentSessionId:
      typeof state.agentSessionId === "string" && state.agentSessionId.trim()
        ? state.agentSessionId
        : null,
    userId: typeof state.userId === "string" && state.userId.trim() ? state.userId : DEFAULT_USER_ID,
    projectId: typeof state.projectId === "string" && state.projectId.trim() ? state.projectId : DEFAULT_PROJECT_ID,
    role: typeof state.role === "string" && state.role.trim() ? state.role : DEFAULT_ROLE,
    department: typeof state.department === "string" ? state.department : DEFAULT_DEPARTMENT,
    clearance: Number.isFinite(clearance) ? Math.max(0, Math.trunc(clearance)) : DEFAULT_CLEARANCE,
    datasetTable:
      typeof state.datasetTable === "string" && state.datasetTable.trim()
        ? state.datasetTable
        : DEFAULT_DATASET,
    composer: typeof state.composer === "string" ? state.composer : "",
    messages,
    activeSpec: state.activeSpec ?? null,
    lastToolEvent,
    toolTrace
  };
}

function isMessage(value: unknown): value is Message {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.id === "string" &&
    (value.role === "user" || value.role === "assistant") &&
    typeof value.text === "string"
  );
}
