"use client";

import { BarChart3, MessageSquare, Layout, Sparkles } from "lucide-react";
import { useCreateSession } from "@/hooks/use-chat";
import { Button } from "@/components/ui/button";

const SUGGESTED_PROMPTS = [
  { icon: BarChart3, text: "Show headcount breakdown by department" },
  { icon: MessageSquare, text: "What's the monthly turnover trend?" },
  { icon: Layout, text: "Analyze project milestone progress" },
  { icon: Sparkles, text: "Show team performance scores over time" },
];

export function ChatEmptyState() {
  const createSession = useCreateSession();

  return (
    <div className="flex flex-col items-center justify-center h-full px-8 py-12">
      <div className="w-14 h-14 rounded-maximum bg-warm-sand flex items-center justify-center mb-6">
        <Sparkles className="w-7 h-7 text-terracotta" />
      </div>

      <h2 className="font-serif text-heading text-near-black mb-2 text-center">
        Start a Conversation
      </h2>
      <p className="text-body text-olive-gray text-center max-w-md mb-8 leading-relaxed">
        Ask questions about your HR and project data. The AI will analyze your data 
        and generate interactive visualizations you can add to your report workspace.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
        {SUGGESTED_PROMPTS.map((prompt) => (
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
        Start New Conversation
      </Button>
    </div>
  );
}
