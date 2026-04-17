"use client";

import { BarChart3, MessageSquare, Layout, Sparkles } from "lucide-react";
import { useCreateSession } from "@/hooks/use-chat";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/context";

export function ChatEmptyState() {
  const { t } = useI18n();
  const createSession = useCreateSession();
  const suggestedPrompts = [
    { icon: BarChart3, text: t("chat.emptyPrompt1") },
    { icon: MessageSquare, text: t("chat.emptyPrompt2") },
    { icon: Layout, text: t("chat.emptyPrompt3") },
    { icon: Sparkles, text: t("chat.emptyPrompt4") },
  ];

  return (
    <div className="flex flex-col items-center justify-center h-full px-8 py-12">
      <div className="w-14 h-14 rounded-maximum bg-warm-sand flex items-center justify-center mb-6">
        <Sparkles className="w-7 h-7 text-terracotta" />
      </div>

      <h2 className="font-serif text-heading text-near-black mb-2 text-center">
        {t("chat.emptyStartTitle")}
      </h2>
      <p className="text-body text-olive-gray text-center max-w-md mb-8 leading-relaxed">
        {t("chat.emptyDescription")}
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
        {suggestedPrompts.map((prompt) => (
          <button
            key={prompt.text}
            onClick={() => createSession.mutate(prompt.text.slice(0, 30))}
            className="flex items-start gap-3 p-4 rounded-comfortable border border-border-cream bg-ivory hover:bg-warm-sand hover:shadow-ring-warm transition-all text-left group"
          >
            <prompt.icon className="w-5 h-5 text-stone-gray group-hover:text-terracotta shrink-0 mt-0.5 transition-colors" />
            <span className="text-body-sm text-olive-gray group-hover:text-near-black transition-colors">
              {prompt.text}
            </span>
          </button>
        ))}
      </div>

      <Button
        variant="default"
        className="mt-8"
        onClick={() => createSession.mutate(undefined)}
        disabled={createSession.isPending}
      >
        <MessageSquare className="w-4 h-4" />
        {t("chat.startNewConversation")}
      </Button>
    </div>
  );
}
