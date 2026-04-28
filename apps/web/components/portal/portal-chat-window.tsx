"use client";

import { useState, useEffect, useRef } from "react";
import { BotMessageSquare, ArrowUp, X } from "lucide-react";
import { sendPortalChatMessage } from "@/lib/portal/chat";
import { useI18n } from "@/lib/i18n/context";

type Message = {
  role: "user" | "assistant";
  text: string;
};

export function PortalChatWindow({
  pageId,
  activeChartId,
  activeChartTitle,
  onClearChart,
  onClose,
}: {
  pageId: string;
  activeChartId: string | null;
  activeChartTitle?: string;
  onClearChart: () => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  const send = async () => {
    const message = draft.trim();
    if (!message || sending) return;
    setDraft("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setMessages((prev) => [...prev, { role: "user", text: message }]);
    setSending(true);
    try {
      const events = await sendPortalChatMessage(pageId, message, { chartId: activeChartId });
      const final = events.find((e) => e.type === "final");
      const text = typeof final?.payload.text === "string" ? final.payload.text : t("portal.chatDone");
      setMessages((prev) => [...prev, { role: "assistant", text }]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", text: t("portal.chatUnableToAnswer") }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Header */}
      <header className="flex shrink-0 items-center gap-3 border-b border-[#eee8dc] px-4 py-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#996b35]/10">
          <BotMessageSquare className="h-4 w-4 text-[#996b35]" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-[#2f332f]">{t("portal.newChat")}</p>
          {activeChartId ? (
            <p className="truncate text-xs text-[#777166]">
              {activeChartTitle || activeChartId}
              <button className="ml-1.5 underline" onClick={onClearChart}>
                {t("portal.chatClearChart")}
              </button>
            </p>
          ) : (
            <p className="text-xs text-[#777166]">{t("portal.chatSubtitle")}</p>
          )}
        </div>
        <button
          onClick={onClose}
          className="rounded-md p-1.5 text-[#777166] transition-colors hover:bg-[#f3eadb] hover:text-[#2f332f]"
          aria-label={t("portal.chatCloseAriaLabel")}
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      {/* Messages */}
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-5">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#996b35]/10">
              <BotMessageSquare className="h-7 w-7 text-[#996b35]" />
            </div>
            <p className="text-sm font-semibold text-[#2f332f]">{t("portal.chatEmptyTitle")}</p>
            <p className="max-w-[200px] text-xs leading-relaxed text-[#777166]">
              {t("portal.chatEmptyDesc")}
            </p>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              className={`flex items-end gap-2.5 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}
            >
              {msg.role === "assistant" && (
                <div className="mb-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#996b35]/10">
                  <BotMessageSquare className="h-3 w-3 text-[#996b35]" />
                </div>
              )}
              <div
                className={`max-w-[78%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "rounded-br-sm bg-[#2f332f] text-white"
                    : "rounded-bl-sm border border-[#eee8dc] bg-[#f7f4eb] text-[#2f332f]"
                }`}
              >
                {msg.text}
              </div>
            </div>
          ))
        )}

        {/* Typing indicator */}
        {sending && (
          <div className="flex items-end gap-2.5">
            <div className="mb-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#996b35]/10">
              <BotMessageSquare className="h-3 w-3 text-[#996b35]" />
            </div>
            <div className="rounded-2xl rounded-bl-sm border border-[#eee8dc] bg-[#f7f4eb] px-4 py-3">
              <span className="flex items-center gap-1">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#996b35]/60 [animation-delay:0ms]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#996b35]/60 [animation-delay:150ms]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#996b35]/60 [animation-delay:300ms]" />
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-[#eee8dc] p-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
          className="relative rounded-xl border border-[#d8d1c1] bg-[#fbfaf5] px-3.5 py-3 transition-colors focus-within:border-[#ad7d3d] focus-within:bg-white"
        >
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder={t("portal.chatPlaceholder")}
            rows={1}
            className="w-full resize-none bg-transparent pr-10 text-sm text-[#2f332f] placeholder:text-[#b0a898] focus:outline-none"
            autoFocus
          />
          <button
            type="submit"
            disabled={sending || !draft.trim()}
            className="absolute bottom-2.5 right-2.5 flex h-7 w-7 items-center justify-center rounded-lg bg-[#2f332f] text-white transition-all hover:bg-[#444a44] disabled:opacity-25"
            aria-label={t("chat.send")}
          >
            <ArrowUp className="h-3.5 w-3.5" />
          </button>
        </form>
        <p className="mt-2 text-center text-[10px] text-[#b0a898]">{t("portal.chatHint")}</p>
      </div>
    </div>
  );
}
