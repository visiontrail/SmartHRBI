"use client";

import { useState } from "react";
import { BotMessageSquare, Send, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { sendPortalChatMessage } from "@/lib/portal/chat";

export function PortalChatWindow({
  pageId,
  activeChartId,
  activeChartTitle,
  onClearChart,
}: {
  pageId: string;
  activeChartId: string | null;
  activeChartTitle?: string;
  onClearChart: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<string[]>([]);
  const [sending, setSending] = useState(false);

  const send = async () => {
    const message = draft.trim();
    if (!message) return;
    setDraft("");
    setMessages((items) => [...items, `You: ${message}`]);
    setSending(true);
    try {
      const events = await sendPortalChatMessage(pageId, message, { chartId: activeChartId });
      const final = events.find((event) => event.type === "final");
      const text = typeof final?.payload.text === "string" ? final.payload.text : "Done.";
      setMessages((items) => [...items, `AI: ${text}`]);
    } catch {
      setMessages((items) => [...items, "AI: Unable to answer right now."]);
    } finally {
      setSending(false);
    }
  };

  if (!open) {
    return (
      <Button
        className="fixed bottom-5 right-5 z-40 rounded-full shadow-lg"
        size="icon"
        onClick={() => setOpen(true)}
        aria-label="Open portal chat"
      >
        <BotMessageSquare className="h-5 w-5" />
      </Button>
    );
  }

  return (
    <section className="fixed bottom-5 right-5 z-40 flex max-h-[72vh] w-[min(30vw,420px)] min-w-[320px] flex-col rounded-md border border-[#d8d1c1] bg-white shadow-2xl">
      <header className="flex items-center justify-between border-b border-[#eee8dc] px-3 py-2">
        <div>
          <div className="text-sm font-semibold">AI chat</div>
          {activeChartId && (
            <div className="text-xs text-[#777166]">
              Asking about: {activeChartTitle || activeChartId}
              <button className="ml-2 underline" onClick={onClearChart}>
                clear
              </button>
            </div>
          )}
        </div>
        <Button variant="ghost" size="icon-sm" onClick={() => setOpen(false)} aria-label="Collapse portal chat">
          <X className="h-4 w-4" />
        </Button>
      </header>
      <div className="min-h-0 flex-1 space-y-2 overflow-auto p-3 text-sm">
        {messages.length === 0 ? (
          <p className="text-[#777166]">Ask about this published page.</p>
        ) : (
          messages.map((message, index) => (
            <div key={`${message}-${index}`} className="rounded-md bg-[#f7f4eb] px-3 py-2">
              {message}
            </div>
          ))
        )}
      </div>
      <form
        className="flex gap-2 border-t border-[#eee8dc] p-3"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <Input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Ask a question..." />
        <Button type="submit" size="icon" disabled={sending} aria-label="Send portal chat message">
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </section>
  );
}
