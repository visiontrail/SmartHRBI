"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useChatStore, type PendingIngestionApproval } from "@/stores/chat-store";
import { useAssetStore } from "@/stores/asset-store";
import { useUIStore } from "@/stores/ui-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { parseSSEStream } from "@/lib/chat/sse";
import { getAuthorizationHeader } from "@/lib/auth/session";
import { useI18n } from "@/lib/i18n/context";
import {
  approveIngestionProposal,
  confirmIngestionSetup,
  createIngestionPlan,
  createIngestionUpload,
  executeIngestionProposal,
} from "@/lib/ingestion/api";
import { generateId, isRecord } from "@/lib/utils";
import type { ChartAsset, ChartSpec, ChartType, KnownChartType } from "@/types/chart";
import type { ChatMessage, ChatSession } from "@/types/chat";
import type {
  IngestionApprovalResult,
  IngestionExecuteResult,
  IngestionPlanAwaitingApproval,
  IngestionPlanResult,
  IngestionProposalAction,
  IngestionTimeGrain,
  IngestionUploadResult,
} from "@/types/ingestion";

const EMPTY_MESSAGES: ChatMessage[] = [];

export function useChatSessions() {
  const setSessions = useChatStore((s) => s.setSessions);

  return useQuery({
    queryKey: ["chat-sessions"],
    queryFn: async () => {
      const sessions = useChatStore.getState().sessions;
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
      const messages = useChatStore.getState().messagesBySession[sessionId] ?? EMPTY_MESSAGES;
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
    mutationFn: async (title?: string) => createLocalSession(title),
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
    mutationFn: async (_sessionId: string) => undefined,
    onSuccess: (_, sessionId) => {
      removeSession(sessionId);
      queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
    },
  });
}

export function useSendMessage() {
  const { t } = useI18n();
  const appendMessage = useChatStore((s) => s.appendMessage);
  const touchSession = useChatStore((s) => s.touchSession);
  const addAsset = useAssetStore((s) => s.addAsset);
  const setIsSending = useUIStore((s) => s.setIsSending);

  return useMutation({
    mutationFn: async ({
      sessionId,
      content,
      attachment,
      approvedAction,
    }: {
      sessionId: string;
      content: string;
      attachment?: File;
      approvedAction?: IngestionProposalAction;
    }) => {
      setIsSending(true);
      const workspaceId = useWorkspaceStore.getState().activeWorkspaceId;
      if (!workspaceId) {
        throw new Error(t("chat.toast.noWorkspace"));
      }
      const trimmedContent = content.trim();
      const pendingApproval = useChatStore.getState().pendingIngestionBySession[sessionId];
      if (attachment) {
        useChatStore.getState().clearPendingIngestionApproval(sessionId);
        return runIngestionConversationResponse({
          sessionId,
          workspaceId,
          content: trimmedContent || t("chat.ingestion.defaultRequirement"),
          attachment,
          t,
        });
      }
      if (pendingApproval) {
        const options = collectApprovalOptions(pendingApproval.plan);
        const resolvedAction =
          approvedAction && options.includes(approvedAction)
            ? approvedAction
            : resolvePendingApprovalAction({
                rawInput: trimmedContent,
                pending: pendingApproval,
              });
        if (!resolvedAction) {
          throw new Error(
            t("chat.ingestion.awaitingApprovalInvalidChoice", {
              options: formatPendingApprovalOptions({
                pending: pendingApproval,
                t,
              }),
            })
          );
        }
        return runIngestionApprovalResponse({
          sessionId,
          pending: pendingApproval,
          approvedAction: resolvedAction,
          t,
        });
      }
      return streamAssistantResponse({ sessionId, content: trimmedContent, workspaceId, t });
    },
    onMutate: ({ sessionId, content, attachment }) => {
      const normalizedContent = formatUserMessageContent({
        content,
        attachmentName: attachment?.name,
        t,
      });
      const userMessage = createUserMessage(sessionId, normalizedContent);
      appendMessage(sessionId, userMessage);
      touchSession(sessionId, {
        lastMessage: userMessage.content,
        messageDelta: 1,
        title: suggestSessionTitle(sessionId, normalizedContent),
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
        content: error instanceof Error ? error.message : t("chat.requestFailed"),
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
type TranslateFn = (key: string, params?: Record<string, string | number | null | undefined>) => string;

async function streamAssistantResponse({
  sessionId,
  content,
  workspaceId,
  t,
}: {
  sessionId: string;
  content: string;
  workspaceId: string;
  t: TranslateFn;
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
      finalText = String(payload.message ?? t("chat.requestFailed"));
    }
  }

  const chartAsset = toChartAsset(latestSpec, {
    sessionId,
    prompt: content,
  });
  const fallbackText = chartAsset
    ? t("chat.generatedChart", { title: chartAsset.title })
    : t("chat.completed");
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

async function runIngestionConversationResponse({
  sessionId,
  workspaceId,
  content,
  attachment,
  t,
}: {
  sessionId: string;
  workspaceId: string;
  content: string;
  attachment: File;
  t: TranslateFn;
}): Promise<{ assistantMessage: ChatMessage; chartAsset?: ChartAsset }> {
  const upload = await createIngestionUpload({
    workspaceId,
    file: attachment,
  });
  let plan = await createIngestionPlan({
    workspaceId,
    jobId: upload.jobId,
    conversationId: sessionId,
    message: content,
  });
  let autoSetupApplied = false;
  let setupTableName: string | null = null;

  if (plan.status === "awaiting_catalog_setup") {
    autoSetupApplied = true;
    setupTableName = plan.suggestedCatalogSeed.tableName;
    plan = await confirmIngestionSetup({
      workspaceId,
      jobId: upload.jobId,
      conversationId: sessionId,
      message: content,
      setup: plan.suggestedCatalogSeed,
    });
  }

  let approvalResult: IngestionApprovalResult | null = null;
  let executionResult: IngestionExecuteResult | null = null;
  if (plan.status === "awaiting_user_approval") {
    useChatStore.getState().setPendingIngestionApproval(sessionId, {
      upload,
      plan,
    });
  }

  const assistantMessage: ChatMessage = {
    id: `msg-${generateId()}`,
    sessionId,
    role: "assistant",
    content: buildIngestionSummaryMessage({
      upload,
      plan,
      autoSetupApplied,
      setupTableName,
      approvalResult,
      executionResult,
      t,
    }),
    timestamp: new Date().toISOString(),
  };
  return { assistantMessage };
}

async function runIngestionApprovalResponse({
  sessionId,
  pending,
  approvedAction,
  t,
}: {
  sessionId: string;
  pending: PendingIngestionApproval;
  approvedAction: IngestionProposalAction;
  t: TranslateFn;
}): Promise<{ assistantMessage: ChatMessage; chartAsset?: ChartAsset }> {
  const plan = pending.plan;
  const approvalResult = await approveIngestionProposal({
    workspaceId: plan.workspaceId,
    jobId: plan.jobId,
    proposalId: plan.proposalId,
    approvedAction,
    userOverrides:
      approvedAction === "time_partitioned_new_table"
        ? {
            timeGrain: plan.proposal.timeGrain,
          }
        : undefined,
  });
  useChatStore.getState().clearPendingIngestionApproval(sessionId);

  let executionResult: IngestionExecuteResult | null = null;
  if (approvalResult.status === "approved") {
    executionResult = await executeIngestionProposal({
      workspaceId: plan.workspaceId,
      jobId: plan.jobId,
      proposalId: plan.proposalId,
    });
  }

  const assistantMessage: ChatMessage = {
    id: `msg-${generateId()}`,
    sessionId,
    role: "assistant",
    content: buildIngestionSummaryMessage({
      upload: pending.upload,
      plan,
      autoSetupApplied: false,
      setupTableName: null,
      approvalResult,
      executionResult,
      t,
    }),
    timestamp: new Date().toISOString(),
  };
  return { assistantMessage };
}

function createLocalSession(title?: string): ChatSession {
  const now = new Date().toISOString();
  return {
    id: `session-${generateId()}`,
    title: title?.trim() || "New Conversation",
    createdAt: now,
    updatedAt: now,
    messageCount: 0,
  };
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

function formatUserMessageContent({
  content,
  attachmentName,
  t,
}: {
  content: string;
  attachmentName?: string;
  t: TranslateFn;
}): string {
  const trimmed = content.trim();
  if (!attachmentName) {
    return trimmed;
  }
  if (!trimmed) {
    return t("chat.userAttachedFileOnly", { fileName: attachmentName });
  }
  return t("chat.userAttachedFileWithPrompt", {
    fileName: attachmentName,
    prompt: trimmed,
  });
}

function buildIngestionSummaryMessage({
  upload,
  plan,
  autoSetupApplied,
  setupTableName,
  approvalResult,
  executionResult,
  t,
}: {
  upload: IngestionUploadResult;
  plan: IngestionPlanResult;
  autoSetupApplied: boolean;
  setupTableName: string | null;
  approvalResult: IngestionApprovalResult | null;
  executionResult: IngestionExecuteResult | null;
  t: TranslateFn;
}): string {
  const parseStats = extractUploadStats(upload);
  const lines: string[] = [
    t("chat.ingestion.summaryTitle"),
    t("chat.ingestion.parsedFile", {
      fileName: upload.fileSummary.fileName,
      sheetCount: parseStats.sheetCount,
      rowCount: parseStats.totalRows,
    }),
    t("chat.ingestion.jobId", { jobId: upload.jobId }),
  ];

  if (plan.status === "awaiting_catalog_setup") {
    if (autoSetupApplied) {
      lines.push(
        t("chat.ingestion.autoSetupApplied", {
          tableName: setupTableName ?? t("ingestion.lifecycle.targetNotSet"),
        })
      );
    }
    lines.push(
      t("chat.ingestion.setupStillRequired", {
        businessType: plan.agentGuess.businessType,
      })
    );
    return lines.join("\n");
  }

  if (autoSetupApplied) {
    lines.push(
      t("chat.ingestion.autoSetupApplied", {
        tableName: setupTableName ?? t("ingestion.lifecycle.targetNotSet"),
      })
    );
  }
  lines.push(...buildAwaitingApprovalSummary(plan, approvalResult, executionResult, t));
  return lines.join("\n");
}

function buildAwaitingApprovalSummary(
  plan: IngestionPlanAwaitingApproval,
  approvalResult: IngestionApprovalResult | null,
  executionResult: IngestionExecuteResult | null,
  t: TranslateFn
): string[] {
  const actionLabel = toProposalActionLabel({
    action: plan.proposal.recommendedAction,
    timeGrain: plan.proposal.timeGrain,
    t,
  });
  const lines = [
    t("chat.ingestion.recommended", {
      action: actionLabel,
      table: plan.proposal.targetTable ?? t("ingestion.lifecycle.targetNotSet"),
    }),
    t("chat.ingestion.diffPreview", {
      insertCount: plan.proposal.diffPreview.predictedInsertCount,
      updateCount: plan.proposal.diffPreview.predictedUpdateCount,
      conflictCount: plan.proposal.diffPreview.predictedConflictCount,
    }),
  ];

  if (plan.proposal.risks.length > 0) {
    lines.push(
      `${t("chat.ingestion.risksTitle")}\n${plan.proposal.risks
        .slice(0, 3)
        .map((risk, index) => `${index + 1}. ${risk}`)
        .join("\n")}`
    );
  }

  if (approvalResult?.status === "cancelled") {
    lines.push(t("chat.ingestion.autoDecisionCancelled"));
    return lines;
  }

  if (!approvalResult) {
    const options = collectApprovalOptions(plan);
    lines.push(
      t("chat.ingestion.awaitingApprovalQuestion", {
        question: plan.humanApproval.question,
      })
    );
    lines.push(
      t("chat.ingestion.awaitingApprovalOptions", {
        options: formatApprovalActionsForDisplay({
          actions: options,
          timeGrain: plan.proposal.timeGrain,
          t,
        }),
      })
    );
    if (plan.humanApproval.recommendedOption) {
      lines.push(
        t("chat.ingestion.awaitingApprovalRecommended", {
          action: toProposalActionLabel({
            action: plan.humanApproval.recommendedOption,
            timeGrain: plan.proposal.timeGrain,
            t,
          }),
        })
      );
    }
    return lines;
  }

  if (approvalResult?.status === "approved") {
    lines.push(
      t("chat.ingestion.autoApproved", {
        action: toProposalActionLabel({
          action: approvalResult.approvedAction,
          timeGrain: approvalResult.timeGrain,
          t,
        }),
      })
    );
  }
  if (executionResult) {
    lines.push(
      t("chat.ingestion.executionReceipt", {
        targetTable: executionResult.receipt.targetTable,
        insertedRows: executionResult.receipt.insertedRows,
        updatedRows: executionResult.receipt.updatedRows,
      })
    );
    lines.push(
      t("chat.ingestion.executionRows", {
        affectedRows: executionResult.receipt.affectedRows,
        rowsAfter: executionResult.receipt.rowsAfter,
      })
    );
  }
  return lines;
}

function normalizeProposalAction(action: string): IngestionProposalAction | null {
  const normalized = action.trim().toLowerCase();
  if (
    normalized === "update_existing" ||
    normalized === "time_partitioned_new_table" ||
    normalized === "new_table" ||
    normalized === "cancel"
  ) {
    return normalized;
  }
  return null;
}

function collectApprovalOptions(plan: IngestionPlanAwaitingApproval): IngestionProposalAction[] {
  const fromApproval = plan.humanApproval.options
    .map((item) => normalizeProposalAction(item))
    .filter((item): item is IngestionProposalAction => item !== null);
  const fromProposal = plan.proposal.candidateActions
    .map((item) => normalizeProposalAction(item))
    .filter((item): item is IngestionProposalAction => item !== null);
  const merged = fromApproval.length > 0 ? fromApproval : fromProposal;
  if (merged.length === 0) {
    return ["update_existing", "time_partitioned_new_table", "new_table", "cancel"];
  }
  const deduped: IngestionProposalAction[] = [];
  for (const item of merged) {
    if (!deduped.includes(item)) {
      deduped.push(item);
    }
  }
  return deduped;
}

function formatApprovalActionsForDisplay({
  actions,
  timeGrain,
  t,
}: {
  actions: IngestionProposalAction[];
  timeGrain: IngestionTimeGrain;
  t: TranslateFn;
}): string {
  return actions
    .map((action, index) => `${index + 1}) ${action} (${toProposalActionLabel({ action, timeGrain, t })})`)
    .join("  ");
}

function formatPendingApprovalOptions({
  pending,
  t,
}: {
  pending: PendingIngestionApproval;
  t: TranslateFn;
}): string {
  return formatApprovalActionsForDisplay({
    actions: collectApprovalOptions(pending.plan),
    timeGrain: pending.plan.proposal.timeGrain,
    t,
  });
}

function resolvePendingApprovalAction({
  rawInput,
  pending,
}: {
  rawInput: string;
  pending: PendingIngestionApproval;
}): IngestionProposalAction | null {
  const options = collectApprovalOptions(pending.plan);
  if (options.length === 0) {
    return null;
  }
  const normalized = rawInput.trim().toLowerCase();
  if (!normalized) {
    return null;
  }

  const direct = normalizeProposalAction(normalized);
  if (direct && options.includes(direct)) {
    return direct;
  }

  const compact = normalized.replace(/\s+/g, "");
  const aliases: Record<string, IngestionProposalAction> = {
    "updateexisting": "update_existing",
    "更新现有表": "update_existing",
    "更新已有表": "update_existing",
    "timepartitionednewtable": "time_partitioned_new_table",
    "分区新表": "time_partitioned_new_table",
    "按时间分区新建表": "time_partitioned_new_table",
    "newtable": "new_table",
    "创建新表": "new_table",
    "cancel": "cancel",
    "取消": "cancel",
    "recommended": pending.plan.proposal.recommendedAction,
    "推荐": pending.plan.proposal.recommendedAction,
    "建议": pending.plan.proposal.recommendedAction,
  };
  const aliasAction = aliases[compact];
  if (aliasAction && options.includes(aliasAction)) {
    return aliasAction;
  }

  const asIndex = Number.parseInt(compact, 10);
  if (Number.isFinite(asIndex) && asIndex >= 1 && asIndex <= options.length) {
    return options[asIndex - 1] ?? null;
  }

  for (const option of options) {
    if (normalized.includes(option)) {
      return option;
    }
  }
  return null;
}

function toProposalActionLabel({
  action,
  timeGrain,
  t,
}: {
  action: string;
  timeGrain: string;
  t: TranslateFn;
}): string {
  if (action === "update_existing") {
    return t("ingestion.lifecycle.action.updateExisting");
  }
  if (action === "new_table") {
    return t("ingestion.lifecycle.action.newTable");
  }
  if (action === "time_partitioned_new_table") {
    if (timeGrain === "month") {
      return t("ingestion.lifecycle.action.newMonthly");
    }
    if (timeGrain === "quarter") {
      return t("ingestion.lifecycle.action.newQuarterly");
    }
    if (timeGrain === "year") {
      return t("ingestion.lifecycle.action.newYearly");
    }
    return t("ingestion.lifecycle.action.newTable");
  }
  if (action === "cancel") {
    return t("ingestion.lifecycle.action.cancel");
  }
  return action;
}

function extractUploadStats(upload: IngestionUploadResult): { sheetCount: number; totalRows: number } {
  if (!isRecord(upload.sheetSummary)) {
    return { sheetCount: 0, totalRows: 0 };
  }
  const sheets = Array.isArray(upload.sheetSummary.sheets)
    ? upload.sheetSummary.sheets.filter(isRecord)
    : [];
  const normalizedSheetCount = asNumber(upload.sheetSummary.sheet_count);
  const sheetCount = normalizedSheetCount > 0 ? normalizedSheetCount : sheets.length;
  const totalRows = sheets.reduce((sum, sheet) => sum + asNumber(sheet.row_count), 0);
  return { sheetCount, totalRows };
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
