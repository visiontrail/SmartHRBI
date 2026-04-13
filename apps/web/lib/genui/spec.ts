export type GenUISpec = {
  engine: string;
  chart_type: string;
  title: string;
  data: Array<Record<string, unknown>>;
  config: Record<string, unknown>;
  route?: {
    complexity_score: number;
    threshold: number;
    reasons: string[];
    selected_engine: string;
  };
};

export type ParsedSpec =
  | { ok: true; spec: GenUISpec }
  | { ok: false; error: string };

export function parseGenUISpec(input: unknown): ParsedSpec {
  if (!input || typeof input !== "object") {
    return { ok: false, error: "Input must be an object" };
  }

  const spec = input as Record<string, unknown>;

  if (typeof spec.title !== "string" || !spec.title) {
    return { ok: false, error: "Missing title" };
  }

  if (typeof spec.engine !== "string" || !spec.engine) {
    return { ok: false, error: "Missing engine" };
  }

  if (typeof spec.chart_type !== "string" || !spec.chart_type) {
    return { ok: false, error: "Missing chart_type" };
  }

  return {
    ok: true,
    spec: {
      engine: spec.engine as string,
      chart_type: spec.chart_type as string,
      title: spec.title as string,
      data: Array.isArray(spec.data) ? spec.data : [],
      config: (typeof spec.config === "object" && spec.config ? spec.config : {}) as Record<string, unknown>,
      route: spec.route as GenUISpec["route"],
    },
  };
}

export function isSpecEmpty(spec: GenUISpec): boolean {
  return spec.chart_type === "empty" || spec.data.length === 0;
}
