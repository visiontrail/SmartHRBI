"use client";

import { useEffect, useMemo, useState } from "react";

import { GenUIRegistry } from "../genui/registry";
import { EmptyPanel, ErrorPanel, SkeletonPanel } from "../genui/state-panels";

type ShareViewProps = {
  apiBaseUrl: string;
  viewId: string;
};

type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
};

type SharePayload = {
  view_id: string;
  title: string;
  current_version: number;
  owner_user_id: string;
  updated_at: string;
  ai_state: Record<string, unknown>;
};

export function ShareView({ apiBaseUrl, viewId }: ShareViewProps) {
  const [payload, setPayload] = useState<SharePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchPayload() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${apiBaseUrl}/share/${encodeURIComponent(viewId)}`);
        const body = (await response.json()) as SharePayload | { detail?: { message?: string } };

        if (!response.ok) {
          if (!cancelled) {
            const detail =
              isRecord(body) && "detail" in body && isRecord((body as { detail?: unknown }).detail)
                ? ((body as { detail: { message?: string } }).detail ?? null)
                : null;
            setError(String(detail?.message ?? `load_failed_${response.status}`));
          }
          return;
        }

        if (!cancelled) {
          setPayload(body as SharePayload);
        }
      } catch (fetchError) {
        if (!cancelled) {
          setError(fetchError instanceof Error ? fetchError.message : "load_failed");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void fetchPayload();

    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, viewId]);

  const activeSpec = useMemo(() => {
    if (!payload || !isRecord(payload.ai_state)) {
      return null;
    }
    return payload.ai_state.active_spec ?? payload.ai_state.chart_spec ?? null;
  }, [payload]);

  const messages = useMemo<Message[]>(() => {
    if (!payload || !isRecord(payload.ai_state)) {
      return [];
    }

    const raw = payload.ai_state.messages;
    if (!Array.isArray(raw)) {
      return [];
    }

    return raw
      .filter(isRecord)
      .map((item, index) => {
        const role: Message["role"] = item.role === "user" ? "user" : "assistant";
        return {
          id: String(item.id ?? `msg-${index}`),
          role,
          text: String(item.text ?? "")
        };
      })
      .filter((item) => item.text.length > 0);
  }, [payload]);

  if (loading) {
    return (
      <main className="share-page">
        <header className="share-page__header">
          <h1>Shared View</h1>
          <p>Loading shared state...</p>
        </header>
        <SkeletonPanel />
      </main>
    );
  }

  if (error) {
    return (
      <main className="share-page">
        <header className="share-page__header">
          <h1>Shared View</h1>
        </header>
        <ErrorPanel description={error} />
      </main>
    );
  }

  if (!payload) {
    return (
      <main className="share-page">
        <header className="share-page__header">
          <h1>Shared View</h1>
        </header>
        <EmptyPanel title="Shared view not found" />
      </main>
    );
  }

  return (
    <main className="share-page">
      <header className="share-page__header">
        <h1>{payload.title}</h1>
        <p>
          View ID: {payload.view_id} · Version: {payload.current_version}
        </p>
      </header>

      <section className="share-page__meta">
        <strong>Owner:</strong> {payload.owner_user_id}
        <br />
        <strong>Updated:</strong> {payload.updated_at}
      </section>

      {activeSpec ? <GenUIRegistry rawSpec={activeSpec} /> : <EmptyPanel title="No saved chart spec" />}

      <section className="share-page__messages">
        <h2>Saved Conversation</h2>
        {messages.length ? (
          <ul>
            {messages.map((message) => (
              <li key={message.id}>
                <strong>{message.role === "user" ? "You" : "AI"}:</strong> {message.text}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No messages were stored for this view.</p>
        )}
      </section>
    </main>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
