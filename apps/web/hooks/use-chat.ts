"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useChatStore } from "@/stores/chat-store";
import { useAssetStore } from "@/stores/asset-store";
import { useUIStore } from "@/stores/ui-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { parseSSEStream } from "@/lib/chat/sse";
import { getAuthorizationHeader } from "@/lib/auth/session";
import { generateId, isRecord } from "@/lib/utils";
import type { ChartAsset, ChartSpec, ChartType, KnownChartType } from "@/types/chart";
import type { ChatMessage } from "@/types/chat";
import * as api from "@/lib/mock/mock-api";

const EMPTY_MESSAGES: ChatMessage[] = [];

export function useChatSessions() {
  const setSessions = useChatStore((s) => s.setSessions);

  return useQuery({
    queryKey: ["chat-sessions"],
    queryFn: async () => {
      const sessions = await api.fetchSessions();
      setSessions(sessions);
      return sessions;
    },
  });
}

export function useChatMessages(sessionId: string | null) {
  const setMessages = useChatStore((s) => s.setMessages);

  return useQuery({
    queryKey: ["chat-messages", sessionId],
    queryFn: async () => {
      if (!sessionId) {
        return EMPTY_MESSAGES;
      }
      const messages = await api.fetchMessages(sessionId);
      setMessages(sessionId, messages);
      return messages;
    },
    enabled: !!sessionId,
    staleTime: Infinity,
  });
}

export function useCreateSession() {
  const queryClient = useQueryClient();
  const addSession = useChatStore((s) => s.addSession);
  const setActiveSession = useChatStore((s) => s.setActiveSession);

  return useMutation({
    mutationFn: (title?: string) => api.createSession(title),
    onSuccess: (session) => {
      addSession(session);
      setActiveSession(session.id);
      queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
    },
  });
}

export function useDeleteSession() {
  const queryClient = useQueryClient();
  const removeSession = useChatStore((s) => s.removeSession);

  return useMutation({
    mutationFn: (sessionId: string) => api.deleteSession(sessionId),
    onSuccess: (_, sessionId) => {
      removeSession(sessionId);
      queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
    },
  });
}

export function useSendMessage() {
  const appendMessage = useChatStore((s) => s.appendMessage);
  const touchSession = useChatStore((s) => s.touchSession);
  const addAsset = useAssetStore((s) => s.addAsset);
  const setIsSending = useUIStore((s) => s.setIsSending);

  return useMutation({
    mutationFn: async ({ sessionId, content }: { sessionId: string; content: string }) => {
      setIsSending(true);
      const workspaceId = useWorkspaceStore.getState().activeWorkspaceId;
      if (!workspaceId) {
        throw new Error("No workspace selected. Create or select a workspace first.");
      }
      return streamAssistantResponse({ sessionId, content, workspaceId });
    },
    onMutate: ({ sessionId, content }) => {
      const userMessage = createUserMessage(sessionId, content);
      appendMessage(sessionId, userMessage);
      touchSession(sessionId, {
        lastMessage: userMessage.content,
        messageDelta: 1,
        title: suggestSessionTitle(sessionId, content),
      });
      return { sessionId };
    },
    onSuccess: ({ assistantMessage, chartAsset }, { sessionId }) => {
      appendMessage(sessionId, assistantMessage);
      if (chartAsset) {
        addAsset(chartAsset);
      }
      touchSession(sessionId, {
        lastMessage: assistantMessage.content,
        messageDelta: 1,
      });
    },
    onError: (error, { sessionId }) => {
      const errorMessage: ChatMessage = {
        id: `msg-${generateId()}`,
        sessionId,
        role: "assistant",
        content: error instanceof Error ? error.message : "请求失败，请稍后重试。",
        timestamp: new Date().toISOString(),
      };
      appendMessage(sessionId, errorMessage);
      touchSession(sessionId, {
        lastMessage: errorMessage.content,
        messageDelta: 1,
      });
    },
    onSettled: () => {
      setIsSending(false);
    },
  });
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const DEFAULT_DATASET_TABLE = process.env.NEXT_PUBLIC_DEFAULT_DATASET_TABLE ?? "employees_wide";
const configuredClearance = Number(process.env.NEXT_PUBLIC_DEFAULT_CLEARANCE ?? 1);
const DEFAULT_CLEARANCE = Number.isFinite(configuredClearance)
  ? Math.max(0, Math.trunc(configuredClearance))
  : 1;
const DEFAULT_AUTH_CONTEXT = {
  userId: process.env.NEXT_PUBLIC_DEFAULT_USER_ID ?? "demo-user",
  projectId: process.env.NEXT_PUBLIC_DEFAULT_PROJECT_ID ?? "demo-project",
  role: process.env.NEXT_PUBLIC_DEFAULT_ROLE ?? "hr",
  department: process.env.NEXT_PUBLIC_DEFAULT_DEPARTMENT ?? "HR",
  clearance: DEFAULT_CLEARANCE,
};
const SESSION_TITLE_MAX = 32;
const SUPPORTED_CHART_TYPES = new Set<KnownChartType>([
  "bar",
  "line",
  "pie",
  "area",
  "stacked_bar",
  "scatter",
  "radar",
  "funnel",
  "radialBar",
  "composed",
  "gauge",
  "heatmap",
  "treemap",
  "sankey",
  "sunburst",
  "boxplot",
  "candlestick",
  "graph",
  "map",
  "parallel",
  "wordCloud",
  "table",
  "single_value",
  "note",
  "empty",
]);
const SUPPORTED_CHART_TYPES_BY_LOWER = new Map<string, KnownChartType>(
  Array.from(SUPPORTED_CHART_TYPES).map((item) => [item.toLowerCase(), item])
);
const CHART_TYPE_ALIASES: Record<string, KnownChartType> = {
  "stackedbar": "stacked_bar",
  "stacked-bar": "stacked_bar",
  "singlevalue": "single_value",
  "single-value": "single_value",
  "radialbar": "radialBar",
  "radial_bar": "radialBar",
  "wordcloud": "wordCloud",
  "word_cloud": "wordCloud",
};
const FALLBACK_OPTION_TYPES = new Set<KnownChartType>([
  "bar",
  "line",
  "pie",
  "area",
  "stacked_bar",
  "scatter",
  "radar",
  "funnel",
  "treemap",
  "single_value",
  "gauge",
]);

async function streamAssistantResponse({
  sessionId,
  content,
  workspaceId,
}: {
  sessionId: string;
  content: string;
  workspaceId: string;
}): Promise<{ assistantMessage: ChatMessage; chartAsset?: ChartAsset }> {
  const authorizationHeader = await getAuthorizationHeader(API_BASE_URL, DEFAULT_AUTH_CONTEXT);
  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authorizationHeader,
    },
    body: JSON.stringify({
      user_id: DEFAULT_AUTH_CONTEXT.userId,
      project_id: DEFAULT_AUTH_CONTEXT.projectId,
      workspace_id: workspaceId,
      role: DEFAULT_AUTH_CONTEXT.role,
      department: DEFAULT_AUTH_CONTEXT.department,
      clearance: DEFAULT_AUTH_CONTEXT.clearance,
      dataset_table: DEFAULT_DATASET_TABLE,
      message: content,
      conversation_id: sessionId,
      request_id: generateId(),
    }),
  });

  if (!response.ok || !response.body) {
    throw new Error(`chat_stream_failed_${response.status}`);
  }

  let finalText = "";
  let latestSpec: unknown = null;
  for await (const streamEvent of parseSSEStream(response.body)) {
    const payload = isRecord(streamEvent.data) ? streamEvent.data : {};
    if (streamEvent.event === "spec") {
      latestSpec = payload.spec ?? null;
      continue;
    }
    if (streamEvent.event === "final") {
      finalText = String(payload.text ?? finalText);
      continue;
    }
    if (streamEvent.event === "error" && !finalText) {
      finalText = String(payload.message ?? "请求失败，请稍后重试。");
    }
  }

  const chartAsset = toChartAsset(latestSpec, {
    sessionId,
    prompt: content,
  });
  const fallbackText = chartAsset ? `已生成图表：${chartAsset.title}` : "已完成。";
  const assistantMessage: ChatMessage = {
    id: `msg-${generateId()}`,
    sessionId,
    role: "assistant",
    content: finalText || fallbackText,
    chartAsset: chartAsset
      ? {
          assetId: chartAsset.id,
          title: chartAsset.title,
          chartType: chartAsset.chartType,
        }
      : undefined,
    timestamp: new Date().toISOString(),
  };
  return { assistantMessage, chartAsset: chartAsset ?? undefined };
}

function createUserMessage(sessionId: string, content: string): ChatMessage {
  return {
    id: `msg-${generateId()}`,
    sessionId,
    role: "user",
    content,
    timestamp: new Date().toISOString(),
  };
}

function suggestSessionTitle(sessionId: string, content: string): string | undefined {
  const session = useChatStore.getState().sessions.find((item) => item.id === sessionId);
  if (!session) {
    return undefined;
  }
  if (session.messageCount > 0 && session.title !== "New Conversation") {
    return undefined;
  }
  const trimmed = content.trim();
  if (!trimmed) {
    return undefined;
  }
  return trimmed.length > SESSION_TITLE_MAX ? `${trimmed.slice(0, SESSION_TITLE_MAX)}...` : trimmed;
}

function toChartAsset(
  rawSpec: unknown,
  source: { sessionId: string; prompt: string }
): ChartAsset | null {
  if (!isRecord(rawSpec)) {
    return null;
  }

  const chartType = normalizeChartType(rawSpec.chart_type);
  if (chartType === "empty") {
    return null;
  }
  const title = typeof rawSpec.title === "string" && rawSpec.title.trim() ? rawSpec.title : "Chart";
  const echartsOption = resolveEchartsOption(rawSpec);
  if (!echartsOption) {
    return null;
  }

  const spec: ChartSpec = {
    chartType,
    title,
    subtitle: typeof rawSpec.subtitle === "string" ? rawSpec.subtitle : undefined,
    echartsOption,
  };
  const now = new Date().toISOString();
  return {
    id: `asset-${generateId()}`,
    title,
    description: spec.subtitle,
    chartType,
    spec,
    sourceMeta: {
      sessionId: source.sessionId,
      messageId: `msg-${generateId()}`,
      prompt: source.prompt,
      datasetTable: DEFAULT_DATASET_TABLE,
    },
    createdAt: now,
    updatedAt: now,
  };
}

function resolveEchartsOption(rawSpec: Record<string, unknown>): Record<string, unknown> | null {
  const config = isRecord(rawSpec.config) ? rawSpec.config : {};
  const option = config.option;
  if (isRecord(option)) {
    return option;
  }

  const rows = Array.isArray(rawSpec.data) ? rawSpec.data.filter(isRecord) : [];
  const title = typeof rawSpec.title === "string" ? rawSpec.title : "Chart";
  const chartType = normalizeChartType(rawSpec.chart_type);
  const configuredYKey = typeof config.yKey === "string" ? config.yKey : null;
  if (chartType === "single_value" || chartType === "gauge") {
    const yKey = configuredYKey ?? inferYKey(rows, null);
    const value = rows.length > 0 && yKey ? asNumber(rows[0]?.[yKey]) : 0;
    return {
      title: { text: title, left: "center" },
      series: [
        {
          type: "gauge",
          detail: { formatter: "{value}" },
          data: [{ value, name: configuredYKey ?? yKey ?? "value" }],
        },
      ],
    };
  }

  if (!FALLBACK_OPTION_TYPES.has(chartType as KnownChartType)) {
    // Never rewrite unsupported/advanced chart types to a different fallback type.
    return null;
  }

  const xKey = typeof config.xKey === "string" ? config.xKey : inferXKey(rows);
  const yKey = configuredYKey ?? inferYKey(rows, xKey);
  if (!xKey || !yKey) {
    return null;
  }

  const categories = rows.map((row, index) => String(row[xKey] ?? `item-${index + 1}`));
  const values = rows.map((row) => asNumber(row[yKey]));

  if (chartType === "treemap") {
    return {
      title: { text: title, left: "center" },
      series: [
        {
          type: "treemap",
          roam: false,
          nodeClick: false,
          data: rows.map((row, index) => ({
            name: String(row[xKey] ?? `item-${index + 1}`),
            value: asNumber(row[yKey]),
          })),
        },
      ],
    };
  }

  if (chartType === "funnel") {
    return {
      title: { text: title, left: "center" },
      tooltip: { trigger: "item" },
      series: [
        {
          type: "funnel",
          left: "10%",
          top: 60,
          bottom: 20,
          width: "80%",
          data: rows.map((row, index) => ({
            name: String(row[xKey] ?? `item-${index + 1}`),
            value: asNumber(row[yKey]),
          })),
        },
      ],
    };
  }

  if (chartType === "radar") {
    const maxValue = Math.max(1, ...values);
    return {
      title: { text: title, left: "center" },
      tooltip: {},
      radar: {
        indicator: categories.map((name) => ({
          name,
          max: Math.ceil(maxValue * 1.2),
        })),
      },
      series: [
        {
          type: "radar",
          data: [{ value: values, name: title }],
        },
      ],
    };
  }

  if (chartType === "pie") {
    return {
      title: { text: title, left: "center" },
      tooltip: { trigger: "item" },
      series: [
        {
          type: "pie",
          radius: "65%",
          data: rows.map((row, index) => ({
            name: String(row[xKey] ?? `item-${index + 1}`),
            value: asNumber(row[yKey]),
          })),
        },
      ],
    };
  }

  if (chartType === "scatter") {
    const points = rows.map((row, index) => {
      const xValue = row[xKey];
      if (typeof xValue === "number") {
        return [xValue, asNumber(row[yKey])];
      }
      return [index + 1, asNumber(row[yKey])];
    });
    return {
      title: { text: title, left: "center" },
      tooltip: { trigger: "item" },
      xAxis: { type: "value", name: xKey },
      yAxis: { type: "value", name: yKey },
      series: [{ type: "scatter", data: points }],
    };
  }

  if (chartType === "stacked_bar") {
    const seriesKey = typeof config.seriesKey === "string" ? config.seriesKey : null;
    if (!seriesKey) {
      return {
        title: { text: title, left: "center" },
        tooltip: { trigger: "axis" },
        grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
        xAxis: { type: "category", data: categories },
        yAxis: { type: "value" },
        series: [{ type: "bar", stack: "total", data: values }],
      };
    }

    const categoryOrder: string[] = [];
    const categorySet = new Set<string>();
    const seriesOrder: string[] = [];
    const seriesSet = new Set<string>();
    const matrix = new Map<string, Map<string, number>>();

    for (const row of rows) {
      const category = String(row[xKey] ?? "");
      const seriesName = String(row[seriesKey] ?? "");
      if (!categorySet.has(category)) {
        categorySet.add(category);
        categoryOrder.push(category);
      }
      if (!seriesSet.has(seriesName)) {
        seriesSet.add(seriesName);
        seriesOrder.push(seriesName);
      }
      const rowMap = matrix.get(seriesName) ?? new Map<string, number>();
      rowMap.set(category, asNumber(row[yKey]));
      matrix.set(seriesName, rowMap);
    }

    return {
      title: { text: title, left: "center" },
      tooltip: { trigger: "axis" },
      legend: { top: 28 },
      grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
      xAxis: { type: "category", data: categoryOrder },
      yAxis: { type: "value" },
      series: seriesOrder.map((seriesName) => ({
        type: "bar",
        name: seriesName,
        stack: "total",
        data: categoryOrder.map((category) => matrix.get(seriesName)?.get(category) ?? 0),
      })),
    };
  }

  const seriesType = chartType === "line" || chartType === "area" ? "line" : "bar";
  return {
    title: { text: title, left: "center" },
    tooltip: { trigger: "axis" },
    grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
    xAxis: { type: "category", data: categories },
    yAxis: { type: "value" },
    series: [
      {
        type: seriesType,
        data: values,
        smooth: chartType === "line" || chartType === "area",
        ...(chartType === "area" ? { areaStyle: {} } : {}),
      },
    ],
  };
}

function inferXKey(rows: Array<Record<string, unknown>>): string | null {
  if (!rows.length) {
    return null;
  }
  const firstRow = rows[0];
  const keys = Object.keys(firstRow);
  if (!keys.length) {
    return null;
  }
  if (keys.includes("label")) {
    return "label";
  }
  const stringKey = keys.find((key) => typeof firstRow[key] === "string");
  return stringKey ?? keys[0];
}

function inferYKey(rows: Array<Record<string, unknown>>, xKey: string | null): string | null {
  if (!rows.length) {
    return null;
  }
  const firstRow = rows[0];
  const keys = Object.keys(firstRow);
  const numberKey = keys.find((key) => key !== xKey && typeof firstRow[key] === "number");
  if (numberKey) {
    return numberKey;
  }
  if (keys.includes("metric_value")) {
    return "metric_value";
  }
  return keys.find((key) => key !== xKey) ?? null;
}

function normalizeChartType(rawChartType: unknown): ChartType {
  const normalized = String(rawChartType ?? "bar").trim();
  if (!normalized) {
    return "bar";
  }

  if (SUPPORTED_CHART_TYPES.has(normalized as KnownChartType)) {
    return normalized as KnownChartType;
  }

  const lowered = normalized.toLowerCase();
  const canonical = SUPPORTED_CHART_TYPES_BY_LOWER.get(lowered);
  if (canonical) {
    return canonical;
  }

  const aliased = CHART_TYPE_ALIASES[lowered];
  if (aliased) {
    return aliased;
  }

  return normalized as ChartType;
}

function asNumber(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return 0;
}
