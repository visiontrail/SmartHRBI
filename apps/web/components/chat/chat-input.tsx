"use client";

import { useRef, useCallback } from "react";
import { Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/stores/chat-store";
import { useUIStore } from "@/stores/ui-store";
import { useSendMessage } from "@/hooks/use-chat";

export function ChatInput({ sessionId }: { sessionId: string }) {
  const composerText = useChatStore((s) => s.composerText);
  const setComposerText = useChatStore((s) => s.setComposerText);
  const isSending = useUIStore((s) => s.isSending);
  const sendMessage = useSendMessage();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = useCallback(() => {
    const content = composerText.trim();
    if (!content || isSending) return;

    sendMessage.mutate({ sessionId, content });
    setComposerText("");

    requestAnimationFrame(() => {
      textareaRef.current?.focus();
    });
  }, [composerText, isSending, sendMessage, sessionId, setComposerText]);

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
      <div className="flex items-end gap-3 max-w-4xl mx-auto">
        <div className="relative flex-1">
          <textarea
            ref={textareaRef}
            value={composerText}
            onChange={(e) => setComposerText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about headcount, turnover, salary distribution, project progress…"
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
          disabled={!composerText.trim() || isSending}
          className="shrink-0 h-[44px] w-[44px] rounded-generous p-0"
        >
          {isSending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Send className="w-4 h-4" />
          )}
        </Button>
      </div>

      <p className="text-label text-stone-gray text-center mt-2">
        Press Enter to send, Shift+Enter for new line
      </p>
    </div>
  );
}
