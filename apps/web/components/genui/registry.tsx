"use client";

import type { ComponentType } from "react";

import { GENUI_REGISTRY_KEYS, isKnownRegistryKey, type GenUIRegistryKey } from "../../lib/genui/catalog";
import { parseGenUISpec } from "../../lib/genui/spec";
import { ChartRenderer } from "./chart-renderer";
import { ErrorPanel, SkeletonPanel } from "./state-panels";

type GenUIRegistryProps = {
  rawSpec: unknown;
  isStreaming?: boolean;
};

const REGISTRY: Record<GenUIRegistryKey, ComponentType<{ rawSpec: unknown }>> = GENUI_REGISTRY_KEYS.reduce(
  (accumulator, key) => {
    accumulator[key] = RegistryChart;
    return accumulator;
  },
  {} as Record<GenUIRegistryKey, ComponentType<{ rawSpec: unknown }>>
);

export function GenUIRegistry({ rawSpec, isStreaming = false }: GenUIRegistryProps) {
  if (!rawSpec && isStreaming) {
    return <SkeletonPanel />;
  }

  const parsed = parseGenUISpec(rawSpec);
  if (!parsed.ok) {
    return <ErrorPanel description={`Invalid chart spec: ${parsed.error}`} />;
  }

  const key = `${parsed.spec.engine}:${parsed.spec.chart_type}`;
  if (!isKnownRegistryKey(key)) {
    return <ErrorPanel description={`Unknown chart registry key: ${key}`} />;
  }

  const Renderer = REGISTRY[key];
  if (!Renderer) {
    return <ErrorPanel description={`Registry component missing for ${key}`} />;
  }

  return <Renderer rawSpec={parsed.spec} />;
}

export function hasRegistryEntry(key: string): boolean {
  return isKnownRegistryKey(key) && Boolean(REGISTRY[key]);
}

function RegistryChart({ rawSpec }: { rawSpec: unknown }) {
  const parsed = parseGenUISpec(rawSpec);
  if (!parsed.ok) {
    return <ErrorPanel description={`Invalid chart spec: ${parsed.error}`} />;
  }
  return <ChartRenderer spec={parsed.spec} />;
}
