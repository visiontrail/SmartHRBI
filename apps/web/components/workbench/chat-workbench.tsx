"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { GenUIRegistry } from "../genui/registry";
import { EmptyPanel, ErrorPanel } from "../genui/state-panels";
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

type PersistedWorkbenchState = {
  conversationId: string;
  userId: string;
  projectId: string;
  datasetTable: string;
  composer: string;
  messages: Message[];
  activeSpec: unknown;
  lastToolEvent: Record<string, unknown> | null;
  shareLink: string | null;
};

const DEFAULT_USER_ID = "demo-user";
const DEFAULT_PROJECT_ID = "demo-project";
const DEFAULT_DATASET = "employees_wide";

export function ChatWorkbench({ apiBaseUrl }: ChatWorkbenchProps) {
  const [conversationId, setConversationId] = useState<string>(makeRequestId());
  const [userId, setUserId] = useState(DEFAULT_USER_ID);
  const [projectId, setProjectId] = useState(DEFAULT_PROJECT_ID);
  const [datasetTable, setDatasetTable] = useState(DEFAULT_DATASET);
  const [composer, setComposer] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [activeSpec, setActiveSpec] = useState<unknown>(null);
  const [lastToolEvent, setLastToolEvent] = useState<Record<string, unknown> | null>(null);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("idle");
  const [streamError, setStreamError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [shareLink, setShareLink] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isRestored, setIsRestored] = useState(false);

  useEffect(() => {
    const persisted = safeLoadFromStorage<PersistedWorkbenchState>(SESSION_STORAGE_KEY);
    if (persisted) {
      setConversationId(persisted.conversationId || makeRequestId());
      setUserId(persisted.userId || DEFAULT_USER_ID);
      setProjectId(persisted.projectId || DEFAULT_PROJECT_ID);
      setDatasetTable(persisted.datasetTable || DEFAULT_DATASET);
      setComposer(persisted.composer || "");
      setMessages(Array.isArray(persisted.messages) ? persisted.messages : []);
      setActiveSpec(persisted.activeSpec ?? null);
      setLastToolEvent(persisted.lastToolEvent ?? null);
      setShareLink(persisted.shareLink ?? null);
    }
    setIsRestored(true);
  }, []);

  useEffect(() => {
    if (!isRestored) {
      return;
    }
    safeSaveToStorage<PersistedWorkbenchState>(SESSION_STORAGE_KEY, {
      conversationId,
      userId,
      projectId,
      datasetTable,
      composer,
      messages,
      activeSpec,
      lastToolEvent,
      shareLink
    });
  }, [
    activeSpec,
    composer,
    conversationId,
    datasetTable,
    isRestored,
    lastToolEvent,
    messages,
    projectId,
    shareLink,
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
    setMessages((previous) => [...previous, { id: makeRequestId(), role: "user", text: message }]);

    try {
      const response = await fetch(`${apiBaseUrl}/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          user_id: userId,
          project_id: projectId,
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
        if (streamEvent.event === "reasoning") {
          appendAssistantMessage(String(payload.text ?? "Reasoning in progress..."));
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
      const response = await fetch(`${apiBaseUrl}/views`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          user_id: userId,
          project_id: projectId,
          dataset_table: datasetTable,
          role: "viewer",
          title: "Saved from Workbench",
          conversation_id: conversationId,
          ai_state: {
            conversation_id: conversationId,
            user_id: userId,
            project_id: projectId,
            dataset_table: datasetTable,
            messages,
            active_spec: activeSpec,
            last_tool_event: lastToolEvent
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

  const streamLabel = useMemo(() => {
    if (streamStatus === "streaming") {
      return "Streaming...";
    }
    return "Idle";
  }, [streamStatus]);

  return (
    <main className="workspace">
      <header className="workspace-header">
        <h1>SmartHRBI Chat Workbench</h1>
        <p>状态: {streamLabel}</p>
      </header>

      <section className="workspace-grid">
        <section className="workspace-card">
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

        <section className="workspace-card">
          <h2>Visualization</h2>
          {streamError ? (
            <ErrorPanel description={streamError} />
          ) : !activeSpec && streamStatus === "idle" ? (
            <EmptyPanel title="Chart not generated yet" />
          ) : (
            <GenUIRegistry rawSpec={activeSpec} isStreaming={streamStatus === "streaming"} />
          )}
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

        <section className="workspace-card">
          <h2>Dataset Context</h2>
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
              Dataset Table
              <input value={datasetTable} onChange={(event) => setDatasetTable(event.target.value)} />
            </label>
            <label>
              Conversation ID
              <input value={conversationId} onChange={(event) => setConversationId(event.target.value)} />
            </label>
          </div>

          <section className="tool-status" data-testid="tool-status">
            <h3>Latest Tool Event</h3>
            {lastToolEvent ? (
              <pre>{JSON.stringify(lastToolEvent, null, 2)}</pre>
            ) : (
              <p className="muted">暂无工具调用事件。</p>
            )}
          </section>
        </section>
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
