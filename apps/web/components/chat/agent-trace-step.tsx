"use client";

import { useState } from "react";
import { Brain, Box, AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TraceStep } from "@/types/trace";

function formatDurationMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatArgPreview(args: Record<string, unknown>): string {
  const sql = args.sql ?? args.query;
  if (typeof sql === "string") {
    return sql.slice(0, 80) + (sql.length > 80 ? "…" : "");
  }
  const table = args.table_name ?? args.table;
  if (typeof table === "string") return table;
  const keys = Object.keys(args);
  if (keys.length === 0) return "";
  const firstKey = keys[0]!;
  const firstVal = String(args[firstKey] ?? "");
  return firstVal.slice(0, 80) + (firstVal.length > 80 ? "…" : "");
}

function PulsingDot() {
  return (
    <span className="inline-block w-1.5 h-1.5 rounded-full bg-stone-gray animate-pulse shrink-0 mt-[5px]" />
  );
}

type Props = {
  step: TraceStep;
  isLive: boolean;
  isLatest: boolean;
  nowMs: number;
};

export function AgentTraceStep({ step, isLive, isLatest, nowMs }: Props) {
  const [open, setOpen] = useState(false);

  if (step.kind === "planning") {
    const preview = step.text.slice(0, 80) + (step.text.length > 80 ? "…" : "");
    return (
      <div className="flex items-start gap-2 py-1.5">
        {isLive && isLatest ? <PulsingDot /> : <span className="w-1.5 shrink-0" />}
        <Brain className="w-3.5 h-3.5 text-stone-gray shrink-0 mt-px" />
        <button
          className="flex-1 text-left min-w-0"
          onClick={() => setOpen((v) => !v)}
          type="button"
        >
          <span className="text-[11px] text-stone-gray leading-snug block">
            {open ? step.text : preview}
          </span>
        </button>
        <button
          className="text-stone-gray shrink-0"
          onClick={() => setOpen((v) => !v)}
          type="button"
        >
          {open ? (
            <ChevronDown className="w-3 h-3" />
          ) : (
            <ChevronRight className="w-3 h-3" />
          )}
        </button>
      </div>
    );
  }

  if (step.kind === "tool") {
    const isRunning = step.status === "running";
    const durationMs = isRunning
      ? nowMs - step.startedAt
      : step.completedAt !== undefined
        ? step.completedAt - step.startedAt
        : undefined;
    const argPreview = formatArgPreview(step.args);

    return (
      <div className="flex flex-col py-1.5 gap-0.5">
        <div className="flex items-center gap-2">
          {isLive && isLatest && isRunning ? <PulsingDot /> : <span className="w-1.5 shrink-0" />}
          <Box
            className={cn(
              "w-3.5 h-3.5 shrink-0",
              step.status === "error" ? "text-terracotta" : "text-stone-gray"
            )}
          />
          <button
            className="flex-1 min-w-0 text-left"
            onClick={() => setOpen((v) => !v)}
            type="button"
          >
            <span
              className={cn(
                "text-[11px] leading-snug font-mono",
                step.status === "error" ? "text-terracotta" : "text-near-black"
              )}
            >
              {step.tool}
            </span>
          </button>
          {durationMs !== undefined && (
            <span className="text-[10px] text-stone-gray shrink-0 tabular-nums">
              {formatDurationMs(durationMs)}
            </span>
          )}
          <button
            className="text-stone-gray shrink-0"
            onClick={() => setOpen((v) => !v)}
            type="button"
          >
            {open ? (
              <ChevronDown className="w-3 h-3" />
            ) : (
              <ChevronRight className="w-3 h-3" />
            )}
          </button>
        </div>

        {!open && argPreview && (
          <div className="ml-6 text-[10px] text-stone-gray font-mono truncate">
            {argPreview}
          </div>
        )}

        {open && (
          <div className="ml-6 mt-1 space-y-1">
            {Object.keys(step.args).length > 0 && (
              <pre className="text-[10px] font-mono text-near-black bg-warm-sand rounded px-2 py-1.5 whitespace-pre-wrap break-all overflow-hidden">
                {JSON.stringify(step.args, null, 2)}
              </pre>
            )}
            {step.resultPreview && (
              <div className="text-[10px] font-mono text-stone-gray bg-warm-sand rounded px-2 py-1.5 whitespace-pre-wrap break-all overflow-hidden">
                {step.resultPreview}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // error step
  return (
    <div className="flex items-start gap-2 py-1.5">
      {isLive && isLatest ? <PulsingDot /> : <span className="w-1.5 shrink-0" />}
      <AlertTriangle className="w-3.5 h-3.5 text-terracotta shrink-0 mt-px" />
      <button
        className="flex-1 text-left min-w-0"
        onClick={() => setOpen((v) => !v)}
        type="button"
      >
        <span className="text-[11px] text-terracotta leading-snug block">
          {step.code ? `[${step.code}] ` : ""}
          {open ? step.message : step.message.slice(0, 80) + (step.message.length > 80 ? "…" : "")}
        </span>
      </button>
    </div>
  );
}
