export type TraceStep =
  | {
      kind: "planning";
      id: string;
      text: string;
      startedAt: number;
    }
  | {
      kind: "tool";
      id: string;
      tool: string;
      args: Record<string, unknown>;
      result?: unknown;
      resultPreview?: string;
      startedAt: number;
      completedAt?: number;
      status: "running" | "ok" | "error";
    }
  | {
      kind: "error";
      id: string;
      message: string;
      code?: string;
      at: number;
    };

export type MessageTrace = {
  state: "live" | "collapsed" | "expanded";
  steps: TraceStep[];
  startedAt: number;
  endedAt?: number;
  terminationReason?: "final" | "error" | "closed";
};
