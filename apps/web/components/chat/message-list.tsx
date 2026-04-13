"use client";

import { useRef, useEffect } from "react";
import { useChatStore } from "@/stores/chat-store";
import { MessageItem } from "./message-item";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useUIStore } from "@/stores/ui-store";
import { Loader2 } from "lucide-react";

export function MessageList({ sessionId }: { sessionId: string }) {
  const messages = useChatStore((s) => s.messagesBySession[sessionId] ?? []);
  const isSending = useUIStore((s) => s.isSending);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isSending]);

  return (
    <ScrollArea className="h-full">
      <div className="flex flex-col gap-1 px-4 py-4">
        {messages.length === 0 && !isSending ? (
          <div className="text-center py-12">
            <p className="text-body text-stone-gray">
              Send a message to start the analysis.
            </p>
          </div>
        ) : (
          messages.map((message) => (
            <MessageItem key={message.id} message={message} />
          ))
        )}

        {isSending && (
          <div className="flex items-center gap-3 px-4 py-4">
            <div className="w-8 h-8 rounded-full bg-warm-sand flex items-center justify-center">
              <Loader2 className="w-4 h-4 text-terracotta animate-spin" />
            </div>
            <div className="space-y-2">
              <div className="h-3 w-48 rounded bg-warm-sand animate-pulse" />
              <div className="h-3 w-32 rounded bg-warm-sand animate-pulse" />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
