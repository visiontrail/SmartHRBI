import { z } from "zod";

import { GENUI_CATALOG } from "./catalog";

const routeSchema = z
  .object({
    complexity_score: z.number().int().min(0),
    threshold: z.number().int().min(1),
    reasons: z.array(z.string()).default([]),
    selected_engine: z.string().min(1)
  })
  .optional();

const rechartsChartTypeSchema = z.enum(GENUI_CATALOG.recharts);
const echartsChartTypeSchema = z.enum(GENUI_CATALOG.echarts);

const baseSpecSchema = z.object({
  title: z.string().min(1),
  data: z.array(z.record(z.string(), z.unknown())).default([]),
  route: routeSchema
});

const rechartsSpecSchema = baseSpecSchema.extend({
  engine: z.literal("recharts"),
  chart_type: rechartsChartTypeSchema,
  config: z
    .object({
      xKey: z.string().optional(),
      yKey: z.string().optional(),
      series: z
        .array(
          z.object({
            name: z.string(),
            dataKey: z.string()
          })
        )
        .optional(),
      columns: z.array(z.string()).optional()
    })
    .catchall(z.unknown())
    .default({})
});

const echartsSpecSchema = baseSpecSchema.extend({
  engine: z.literal("echarts"),
  chart_type: echartsChartTypeSchema,
  config: z.object({
    option: z.record(z.string(), z.unknown())
  })
});

export const genUISpecSchema = z.union([rechartsSpecSchema, echartsSpecSchema]);

export type GenUISpec = z.infer<typeof genUISpecSchema>;

export type ParsedSpec =
  | {
      ok: true;
      spec: GenUISpec;
    }
  | {
      ok: false;
      error: string;
    };

export function parseGenUISpec(input: unknown): ParsedSpec {
  const parsed = genUISpecSchema.safeParse(input);
  if (parsed.success) {
    return {
      ok: true,
      spec: parsed.data
    };
  }

  return {
    ok: false,
    error: parsed.error.issues.map((issue) => issue.message).join("; ")
  };
}

export function isSpecEmpty(spec: GenUISpec): boolean {
  return spec.chart_type === "empty" || spec.data.length === 0;
}
