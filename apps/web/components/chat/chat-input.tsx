"use client";

import { useRef, useCallback, useEffect, useMemo, useState } from "react";
import { Send, Loader2, Paperclip, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/stores/chat-store";
import { useUIStore } from "@/stores/ui-store";
import { useSendMessage } from "@/hooks/use-chat";
import { useI18n } from "@/lib/i18n/context";
import type { IngestionProposalAction, IngestionTimeGrain } from "@/types/ingestion";

export function ChatInput({ sessionId }: { sessionId: string }) {
  const { t } = useI18n();
  const composerText = useChatStore((s) => s.composerText);
  const setComposerText = useChatStore((s) => s.setComposerText);
  const pendingApproval = useChatStore((s) => s.pendingIngestionBySession[sessionId]);
  const isSending = useUIStore((s) => s.isSending);
  const sendMessage = useSendMessage();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [customApprovalInput, setCustomApprovalInput] = useState(false);
  const approvalOptions = useMemo(
    () => collectPendingApprovalOptions(pendingApproval?.plan.humanApproval.options),
    [pendingApproval]
  );
  const inputLockedByApproval = Boolean(pendingApproval) && !customApprovalInput;

  useEffect(() => {
    if (pendingApproval) {
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      return;
    }
    setCustomApprovalInput(false);
  }, [pendingApproval]);

  const handleSubmit = useCallback(() => {
    const content = composerText.trim();
    if ((!content && !selectedFile) || isSending || inputLockedByApproval) return;

    sendMessage.mutate({ sessionId, content, attachment: selectedFile ?? undefined });
    setComposerText("");
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }

    requestAnimationFrame(() => {
      textareaRef.current?.focus();
    });
  }, [
    composerText,
    inputLockedByApproval,
    isSending,
    selectedFile,
    sendMessage,
    sessionId,
    setComposerText,
  ]);

  const handleApprovalOption = useCallback(
    (approvedAction: IngestionProposalAction) => {
      if (!pendingApproval || isSending) {
        return;
      }
      const label = formatApprovalActionLabel({
        action: approvedAction,
        timeGrain: pendingApproval.plan.proposal.timeGrain,
        t,
      });
      sendMessage.mutate({
        sessionId,
        content: label,
        approvedAction,
      });
      setComposerText("");
      setCustomApprovalInput(false);
      requestAnimationFrame(() => {
        textareaRef.current?.focus();
      });
    },
    [isSending, pendingApproval, sendMessage, sessionId, setComposerText, t]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  return (
    <div className="border-t border-border-cream bg-ivory px-4 py-3 shrink-0">
      <div className="max-w-4xl mx-auto space-y-2">
        {pendingApproval ? (
          <div className="rounded-comfortable border border-border-cream bg-amber-50 px-3 py-3">
            <p className="text-body-sm font-medium text-near-black">
              {pendingApproval.plan.humanApproval.question || t("chat.ingestion.approvalOptionsTitle")}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {approvalOptions.map((option) => {
                const isRecommended = pendingApproval.plan.humanApproval.recommendedOption === option;
                return (
                  <Button
                    key={option}
                    type="button"
                    size="sm"
                    variant={isRecommended ? "default" : "outline"}
                    onClick={() => handleApprovalOption(option)}
                    disabled={isSending}
                  >
                    {formatApprovalActionLabel({
                      action: option,
                      timeGrain: pendingApproval.plan.proposal.timeGrain,
                      t,
                    })}
                    {isRecommended ? ` · ${t("chat.ingestion.awaitingApprovalRecommendedTag")}` : ""}
                  </Button>
                );
              })}
              <Button
                type="button"
                size="sm"
                variant={customApprovalInput ? "default" : "outline"}
                onClick={() => {
                  setCustomApprovalInput(true);
                  requestAnimationFrame(() => textareaRef.current?.focus());
                }}
                disabled={isSending}
              >
                {t("chat.ingestion.approvalCustomInput")}
              </Button>
            </div>
            <p className="pt-2 text-caption text-stone-gray">
              {customApprovalInput
                ? t("chat.ingestion.approvalCustomInputHint")
                : t("chat.ingestion.approvalQuickPickHint")}
            </p>
          </div>
        ) : null}

        {selectedFile ? (
          <div className="inline-flex max-w-full items-center gap-2 rounded-full border border-border-cream bg-parchment px-3 py-1 text-caption text-near-black">
            <span className="truncate" title={selectedFile.name}>
              {t("chat.fileAttached", { fileName: selectedFile.name })}
            </span>
            <button
              type="button"
              className="rounded-full p-0.5 text-stone-gray hover:text-near-black"
              onClick={() => {
                setSelectedFile(null);
                if (fileInputRef.current) {
                  fileInputRef.current.value = "";
                }
              }}
              aria-label={t("chat.removeFile")}
              disabled={isSending}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ) : null}

        <div className="flex items-end gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            className="hidden"
            onChange={(event) => {
              setSelectedFile(event.target.files?.[0] ?? null);
            }}
            disabled={isSending}
          />

          <Button
            type="button"
            variant="outline"
            size="icon-sm"
            className="h-[44px] w-[44px] shrink-0"
            onClick={() => fileInputRef.current?.click()}
            disabled={isSending || Boolean(pendingApproval)}
            aria-label={t("chat.attachFile")}
          >
            <Paperclip className="h-4 w-4" />
          </Button>

          <div className="relative flex-1">
            <textarea
              ref={textareaRef}
              value={composerText}
              onChange={(e) => setComposerText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                inputLockedByApproval
                  ? t("chat.ingestion.approvalInputLocked")
                  : t("chat.inputPlaceholder")
              }
              rows={1}
              disabled={isSending || inputLockedByApproval}
              className="w-full resize-none rounded-generous border border-border-cream bg-parchment px-4 py-3 pr-12 text-body-sm text-near-black placeholder:text-stone-gray focus:outline-none focus:ring-2 focus:ring-focus-blue focus:border-focus-blue transition-colors disabled:opacity-50 min-h-[44px] max-h-[160px] scrollbar-thin"
              style={{
                height: "auto",
                minHeight: "44px",
              }}
              onInput={(e) => {
                const target = e.target as HTMLTextAreaElement;
                target.style.height = "auto";
                target.style.height = Math.min(target.scrollHeight, 160) + "px";
              }}
            />
          </div>

          <Button
            size="default"
            variant="default"
            onClick={handleSubmit}
            disabled={(!composerText.trim() && !selectedFile) || isSending || inputLockedByApproval}
            className="shrink-0 h-[44px] w-[44px] rounded-generous p-0"
          >
            {isSending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </Button>
        </div>
      </div>

      <p className="text-label text-stone-gray text-center mt-2">
        {t("chat.inputHintWithAttachment")}
      </p>
    </div>
  );
}

function collectPendingApprovalOptions(
  values: string[] | undefined
): IngestionProposalAction[] {
  const options = (values ?? [])
    .map(normalizeApprovalAction)
    .filter((item): item is IngestionProposalAction => item !== null);
  if (options.length === 0) {
    return ["update_existing", "time_partitioned_new_table", "new_table", "cancel"];
  }
  const deduped: IngestionProposalAction[] = [];
  for (const item of options) {
    if (!deduped.includes(item)) {
      deduped.push(item);
    }
  }
  return deduped;
}

function normalizeApprovalAction(value: string): IngestionProposalAction | null {
  const normalized = value.trim().toLowerCase();
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

function formatApprovalActionLabel({
  action,
  timeGrain,
  t,
}: {
  action: IngestionProposalAction;
  timeGrain: IngestionTimeGrain;
  t: (key: string, params?: Record<string, string | number | null | undefined>) => string;
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
  return t("ingestion.lifecycle.action.cancel");
}
