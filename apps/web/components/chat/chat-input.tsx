"use client";

import { useRef, useCallback, useState } from "react";
import { Send, Loader2, Paperclip, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/stores/chat-store";
import { useUIStore } from "@/stores/ui-store";
import { useSendMessage } from "@/hooks/use-chat";
import { useI18n } from "@/lib/i18n/context";

export function ChatInput({ sessionId }: { sessionId: string }) {
  const { t } = useI18n();
  const composerText = useChatStore((s) => s.composerText);
  const setComposerText = useChatStore((s) => s.setComposerText);
  const isSending = useUIStore((s) => s.isSending);
  const sendMessage = useSendMessage();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const handleSubmit = useCallback(() => {
    const content = composerText.trim();
    if ((!content && !selectedFile) || isSending) return;

    sendMessage.mutate({ sessionId, content, attachment: selectedFile ?? undefined });
    setComposerText("");
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }

    requestAnimationFrame(() => {
      textareaRef.current?.focus();
    });
  }, [composerText, isSending, selectedFile, sendMessage, sessionId, setComposerText]);

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
            disabled={isSending}
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
              placeholder={t("chat.inputPlaceholder")}
              rows={1}
              disabled={isSending}
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
            disabled={(!composerText.trim() && !selectedFile) || isSending}
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
