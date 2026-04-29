import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { useChatStore } from "../../stores/chat-store";

const MSG_ID = "msg-stream-test";

function reset() {
  useChatStore.setState({ traceByMessageId: {} });
}

function getTrace() {
  return useChatStore.getState().traceByMessageId[MSG_ID];
}

describe("Agent trace store — SSE sequence integration", () => {
  beforeEach(() => {
    reset();
    useChatStore.getState().startTrace(MSG_ID, Date.now());
  });
  afterEach(() => {
    reset();
  });

  it("5.2: handles out-of-order tool_use/tool_result pairs (B result before A result)", () => {
    const store = useChatStore.getState();
    const now = Date.now();

    // 1. planning
    store.pushTraceStep(MSG_ID, {
      kind: "planning",
      id: "plan-0",
      text: "I will run two queries.",
      startedAt: now,
    });

    // 2. tool_use A
    store.pushTraceStep(MSG_ID, {
      kind: "tool",
      id: "step-A",
      tool: "execute_readonly_sql",
      args: { sql: "SELECT A" },
      startedAt: now + 100,
      status: "running",
    });

    // 3. tool_use B
    store.pushTraceStep(MSG_ID, {
      kind: "tool",
      id: "step-B",
      tool: "execute_readonly_sql",
      args: { sql: "SELECT B" },
      startedAt: now + 200,
      status: "running",
    });

    // 4. tool_result B arrives first (out of order)
    store.patchTraceStep(MSG_ID, "step-B", {
      result: { rows: [{ v: 2 }] },
      resultPreview: "1 rows",
      completedAt: now + 500,
      status: "ok",
    });

    // 5. tool_result A arrives second
    store.patchTraceStep(MSG_ID, "step-A", {
      result: { rows: [{ v: 1 }] },
      resultPreview: "1 rows",
      completedAt: now + 600,
      status: "ok",
    });

    // 6. final → endTrace
    store.endTrace(MSG_ID, "final");

    const trace = getTrace();
    expect(trace?.state).toBe("collapsed");
    expect(trace?.steps).toHaveLength(3); // planning + A + B in arrival order

    const planStep = trace?.steps[0];
    expect(planStep?.kind).toBe("planning");

    const stepA = trace?.steps.find((s) => s.kind === "tool" && s.id === "step-A");
    const stepB = trace?.steps.find((s) => s.kind === "tool" && s.id === "step-B");
    expect(stepA).toBeDefined();
    expect(stepB).toBeDefined();

    if (stepA?.kind === "tool") {
      expect(stepA.status).toBe("ok");
      expect(stepA.id).toBe("step-A");
    }
    if (stepB?.kind === "tool") {
      expect(stepB.status).toBe("ok");
      expect(stepB.id).toBe("step-B");
    }
  });

  it("5.3: error-path — trace collapses with status error when stream ends with error event", () => {
    const store = useChatStore.getState();
    const now = Date.now();

    store.pushTraceStep(MSG_ID, {
      kind: "tool",
      id: "step-1",
      tool: "execute_readonly_sql",
      args: { sql: "DROP TABLE" },
      startedAt: now,
      status: "running",
    });

    store.pushTraceStep(MSG_ID, {
      kind: "error",
      id: `error-${now}`,
      message: "SQL blocked by guardrail",
      code: "GUARDRAIL_VIOLATION",
      at: now + 100,
    });

    // No final event — stream ended after error
    store.endTrace(MSG_ID, "error");

    const trace = getTrace();
    expect(trace?.state).toBe("collapsed");
    expect(trace?.steps.some((s) => s.kind === "error")).toBe(true);

    // traceSummary should reflect error status when built by streamAssistantResponse
    // Here we just verify the store has terminated with the right terminal reason
    // (traceSummary.status === "error" is computed by streamAssistantResponse)
    expect(trace?.endedAt).toBeDefined();
  });

  it("5.4: interruption — stream closes after one tool_use with no matching tool_result", () => {
    const store = useChatStore.getState();
    const now = Date.now();

    store.pushTraceStep(MSG_ID, {
      kind: "tool",
      id: "step-orphan",
      tool: "execute_readonly_sql",
      args: { sql: "SELECT 1" },
      startedAt: now,
      status: "running",
    });

    // Stream reader closes — no tool_result, no final
    store.endTrace(MSG_ID, "closed");

    const trace = getTrace();
    expect(trace?.state).toBe("collapsed");
    expect(trace?.endedAt).toBeDefined();

    // Orphan tool step is still in running status
    const orphan = trace?.steps.find((s) => s.kind === "tool" && s.id === "step-orphan");
    expect(orphan).toBeDefined();
    if (orphan?.kind === "tool") {
      expect(orphan.status).toBe("running");
      expect(orphan.completedAt).toBeUndefined();
    }
  });
});
