"use client";

import { ChangeEvent, FormEvent, useMemo, useRef, useState } from "react";

import { GenUIRegistry } from "../genui/registry";
import { EmptyPanel, ErrorPanel } from "../genui/state-panels";
import { getAuthorizationHeader } from "../../lib/auth/session";
import { parseSSEStream } from "../../lib/chat/sse";

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
type UploadStatus = "idle" | "uploading";


const DEFAULT_USER_ID = "demo-user";
const DEFAULT_PROJECT_ID = "demo-project";
const DEFAULT_ROLE = "hr";
const DEFAULT_DEPARTMENT = "HR";
const DEFAULT_CLEARANCE = 1;
const DEFAULT_DATASET = "employees_wide";

export function ChatWorkbench({ apiBaseUrl }: ChatWorkbenchProps) {
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const [conversationId, setConversationId] = useState<string>(makeRequestId());
  const [agentSessionId, setAgentSessionId] = useState<string | null>(null);
  const [userId, setUserId] = useState(DEFAULT_USER_ID);
  const [projectId, setProjectId] = useState(DEFAULT_PROJECT_ID);
  const [role, setRole] = useState(DEFAULT_ROLE);
  const [department, setDepartment] = useState(DEFAULT_DEPARTMENT);
  const [clearance, setClearance] = useState(DEFAULT_CLEARANCE);
  const [datasetTable, setDatasetTable] = useState(DEFAULT_DATASET);
  const [composer, setComposer] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [activeSpec, setActiveSpec] = useState<unknown>(null);
  const [lastToolEvent, setLastToolEvent] = useState<Record<string, unknown> | null>(null);
  const [toolTrace, setToolTrace] = useState<Record<string, unknown>[]>([]);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("idle");
  const [streamError, setStreamError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [shareLink, setShareLink] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>("idle");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadBatchId, setUploadBatchId] = useState<string | null>(null);
  const [uploadDiagnostics, setUploadDiagnostics] = useState<Record<string, unknown> | null>(null);
  const [qualityReport, setQualityReport] = useState<Record<string, unknown> | null>(null);

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

  function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
    setUploadError(null);
    setSelectedFiles(Array.from(event.target.files ?? []));
  }

  async function handleUploadFiles() {
    if (selectedFiles.length === 0 || uploadStatus === "uploading") {
      return;
    }

    setUploadStatus("uploading");
    setUploadError(null);

    try {
      const authorizationHeader = await getAuthorizationHeader(apiBaseUrl, {
        userId,
        projectId,
        role,
        department,
        clearance
      });

      const formData = new FormData();
      formData.set("user_id", userId);
      formData.set("project_id", projectId);
      selectedFiles.forEach((file) => {
        formData.append("files", file);
      });

      const uploadResponse = await fetch(`${apiBaseUrl}/datasets/upload`, {
        method: "POST",
        headers: authorizationHeader,
        body: formData
      });
      const uploadPayload = await uploadResponse.json().catch(() => null);

      if (!uploadResponse.ok) {
        throw new Error(readApiErrorMessage(uploadPayload, `upload_failed_${uploadResponse.status}`));
      }
      if (!isRecord(uploadPayload)) {
        throw new Error("upload_invalid_payload");
      }

      const nextDatasetTable = String(uploadPayload.dataset_table ?? "");
      const nextBatchId = String(uploadPayload.batch_id ?? "");
      const diagnostics = isRecord(uploadPayload.diagnostics) ? uploadPayload.diagnostics : null;
      if (!nextDatasetTable || !nextBatchId) {
        throw new Error("upload_missing_dataset_metadata");
      }

      setDatasetTable(nextDatasetTable);
      setUploadBatchId(nextBatchId);
      setUploadDiagnostics(diagnostics);

      const qualityResponse = await fetch(`${apiBaseUrl}/datasets/${nextBatchId}/quality-report`, {
        headers: authorizationHeader
      });
      const qualityPayload = await qualityResponse.json().catch(() => null);
      if (!qualityResponse.ok) {
        throw new Error(readApiErrorMessage(qualityPayload, `quality_report_failed_${qualityResponse.status}`));
      }
      if (!isRecord(qualityPayload)) {
        throw new Error("quality_report_invalid_payload");
      }

      setQualityReport(qualityPayload);
      appendAssistantMessage(
        `Uploaded ${selectedFiles.length} Excel file(s). Active dataset table switched to ${nextDatasetTable}.`
      );
      setSelectedFiles([]);
      if (uploadInputRef.current) {
        uploadInputRef.current.value = "";
      }
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "上传失败");
    } finally {
      setUploadStatus("idle");
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

  const selectedFilesLabel = useMemo(() => {
    if (selectedFiles.length === 0) {
      return "尚未选择文件";
    }
    if (selectedFiles.length === 1) {
      return selectedFiles[0]?.name ?? "1 file selected";
    }
    return `已选择 ${selectedFiles.length} 个文件`;
  }, [selectedFiles]);

  const uploadSummary = useMemo(() => {
    if (!isRecord(qualityReport)) {
      return null;
    }

    const summary = isRecord(qualityReport.summary) ? qualityReport.summary : null;
    const blockingIssues = Array.isArray(qualityReport.blocking_issues) ? qualityReport.blocking_issues : [];
    const canPublish = Boolean(qualityReport.can_publish_to_semantic_layer);
    const diagnosticsRowCount = Number(uploadDiagnostics?.result_row_count ?? 0);
    const diagnosticsColumnCount = Number(uploadDiagnostics?.result_column_count ?? 0);

    return {
      rowCount: Number(summary?.row_count ?? diagnosticsRowCount ?? 0),
      columnCount: Number(summary?.column_count ?? diagnosticsColumnCount ?? 0),
      issueCount: blockingIssues.length,
      canPublish
    };
  }, [qualityReport, uploadDiagnostics]);

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
          <section className="upload-panel">
            <div className="upload-panel__copy">
              <h3>Excel Upload</h3>
              <p>上传 `.xlsx` 后会自动创建数据表，并回填到当前会话的 `Dataset Table`。</p>
            </div>
            <input
              ref={uploadInputRef}
              aria-label="Excel Upload"
              type="file"
              accept=".xlsx"
              multiple
              onChange={handleFileSelection}
            />
            <div className="upload-panel__actions">
              <button type="button" onClick={handleUploadFiles} disabled={!selectedFiles.length || uploadStatus === "uploading"}>
                {uploadStatus === "uploading" ? "Uploading..." : "Upload Excel"}
              </button>
              <p className="muted">{selectedFilesLabel}</p>
            </div>
            <p className="upload-panel__hint">限制：单文件 10MB，单次最多 20 个 `.xlsx` 文件。</p>
            {uploadError ? <p className="upload-error">{uploadError}</p> : null}
            {uploadBatchId ? (
              <div className="upload-summary" data-testid="upload-summary">
                <p>
                  Batch ID: <strong>{uploadBatchId}</strong>
                </p>
                <p>
                  Dataset Table: <strong>{datasetTable}</strong>
                </p>
                {uploadSummary ? (
                  <p>
                    Rows {uploadSummary.rowCount}, Columns {uploadSummary.columnCount}, Blocking issues {uploadSummary.issueCount},
                    Semantic layer {uploadSummary.canPublish ? "ready" : "blocked"}.
                  </p>
                ) : null}
              </div>
            ) : null}
          </section>
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

function readApiErrorMessage(payload: unknown, fallback: string): string {
  if (!isRecord(payload)) {
    return fallback;
  }

  const detail = isRecord(payload.detail) ? payload.detail : null;
  const detailMessage = detail ? String(detail.message ?? "") : "";
  if (detailMessage) {
    return detailMessage;
  }

  const payloadMessage = String(payload.message ?? "");
  return payloadMessage || fallback;
}
