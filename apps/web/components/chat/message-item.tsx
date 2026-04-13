"use client";

import type { ChatMessage } from "@/types/chat";
import { ChartMessageCard } from "./chart-message-card";
import { User, Bot } from "lucide-react";
import { cn } from "@/lib/utils";

export function MessageItem({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex gap-3 py-3 animate-fade-in",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "shrink-0 w-8 h-8 rounded-full flex items-center justify-center",
          isUser ? "bg-near-black" : "bg-warm-sand"
        )}
      >
        {isUser ? (
          <User className="w-4 h-4 text-ivory" />
        ) : (
          <Bot className="w-4 h-4 text-terracotta" />
        )}
      </div>

      {/* Content */}
      <div
        className={cn(
          "max-w-[85%] space-y-3",
          isUser ? "items-end" : "items-start"
        )}
      >
        {/* Text Bubble */}
        <div
          className={cn(
            "rounded-very px-4 py-3",
            isUser
              ? "bg-near-black text-ivory rounded-tr-subtle"
              : "bg-ivory border border-border-cream text-near-black rounded-tl-subtle shadow-whisper"
          )}
        >
          <p className="text-body-sm leading-relaxed whitespace-pre-wrap">
            {message.content}
          </p>
        </div>

        {/* Chart Card */}
        {message.chartAsset && !isUser && (
          <ChartMessageCard
            assetId={message.chartAsset.assetId}
            title={message.chartAsset.title}
            chartType={message.chartAsset.chartType}
          />
        )}
      </div>
    </div>
  );
}
