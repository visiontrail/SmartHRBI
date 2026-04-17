"use client";

import { useEffect, useMemo, useState } from "react";

import { GenUIRegistry } from "../genui/registry";
import { EmptyPanel, ErrorPanel, SkeletonPanel } from "../genui/state-panels";
import { getAuthorizationHeader } from "../../lib/auth/session";
import { useI18n } from "@/lib/i18n/context";

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
  const { t } = useI18n();
  const [payload, setPayload] = useState<SharePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchPayload() {
      setLoading(true);
      setError(null);
      try {
        const authorizationHeader = await getAuthorizationHeader(apiBaseUrl, {
          userId: "share-viewer",
          projectId: "shared-views",
          role: "viewer",
          department: null,
          clearance: 0
        });
        const response = await fetch(`${apiBaseUrl}/share/${encodeURIComponent(viewId)}`, {
          headers: authorizationHeader
        });
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
          <h1>{t("share.title")}</h1>
          <p>{t("share.loading")}</p>
        </header>
        <SkeletonPanel />
      </main>
    );
  }

  if (error) {
    return (
      <main className="share-page">
        <header className="share-page__header">
          <h1>{t("share.title")}</h1>
        </header>
        <ErrorPanel description={error} />
      </main>
    );
  }

  if (!payload) {
    return (
      <main className="share-page">
        <header className="share-page__header">
          <h1>{t("share.title")}</h1>
        </header>
        <EmptyPanel title={t("share.notFound")} />
      </main>
    );
  }

  return (
    <main className="share-page">
      <header className="share-page__header">
        <h1>{payload.title}</h1>
        <p>
          {t("share.viewMeta", { viewId: payload.view_id, version: payload.current_version })}
        </p>
      </header>

      <section className="share-page__meta">
        <strong>{t("share.owner")}</strong> {payload.owner_user_id}
        <br />
        <strong>{t("share.updated")}</strong> {payload.updated_at}
      </section>

      {activeSpec ? <GenUIRegistry rawSpec={activeSpec} /> : <EmptyPanel title={t("share.noSpec")} />}

      <section className="share-page__messages">
        <h2>{t("share.savedConversation")}</h2>
        {messages.length ? (
          <ul>
            {messages.map((message) => (
              <li key={message.id}>
                <strong>{message.role === "user" ? t("share.you") : t("share.ai")}:</strong> {message.text}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">{t("share.noMessages")}</p>
        )}
      </section>
    </main>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
