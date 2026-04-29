## 1. Backend — SSE payload enrichment

- [ ] 1.1 In `apps/api/agent_runtime.py`, generate a UUID `step_id` and capture `started_at` (epoch seconds) inside `_sdk_pre_tool_use_hook`; store on the in-flight `SDKToolInvocationRecord`.
- [ ] 1.2 Include `step_id` and `started_at` in the dict payload emitted for `tool_use` events (both SDK and non-SDK code paths).
- [ ] 1.3 In `_sdk_post_tool_use_hook` (and the equivalent post-result paths), copy `step_id` + original `started_at` onto the `tool_result` payload and add `completed_at = time.time()`.
- [ ] 1.4 Mirror the same enrichment in any non-SDK tool emission paths in `agent_runtime.py` so portal chat (`ChartQueryAgent`) inherits the contract.
- [ ] 1.5 Update `tests/integration/test_agent_runtime.py` and `tests/api/test_chat_stream.py` to assert `step_id`, `started_at`, `completed_at` fields and verify call/result pairs share `step_id`.
- [ ] 1.6 Run `make test` (Python) — confirm green.

## 2. Frontend — types, store, SSE consumer

- [ ] 2.1 Extend `apps/web/types/chat.ts`: add `traceSummary?: { stepCount: number; durationMs: number; status: "ok" | "error" | "incomplete" }` to `ChatMessage`.
- [ ] 2.2 In `apps/web/stores/chat-store.ts`, add `traceByMessageId: Record<string, MessageTrace>` plus actions `startTrace`, `pushTraceStep`, `patchTraceStep`, `endTrace`, `setTraceState`. Define `TraceStep` and `MessageTrace` types in a new `apps/web/types/trace.ts`.
- [ ] 2.3 In `apps/web/hooks/use-chat.ts` `streamAssistantResponse`, generate the assistant `messageId` upfront, call `startTrace(messageId, Date.now())` before reading the stream.
- [ ] 2.4 In the SSE loop, wire `planning` → `pushTraceStep({kind:"planning"})`, `tool_use` → `pushTraceStep({kind:"tool", id: step_id, status:"running"})`, `tool_result` → `patchTraceStep(step_id, {result, resultPreview, completedAt, status})`, `error` → `pushTraceStep({kind:"error"})`. Tolerate out-of-order arrival (stub-and-patch on orphan `tool_result`).
- [ ] 2.5 On stream loop exit, call `endTrace(messageId, terminalReason)`; compute `traceSummary` and attach it to the assistant `ChatMessage` returned by `streamAssistantResponse`.
- [ ] 2.6 Compute a one-line `resultPreview` at receive time (truncate to ~80 chars; for arrays, show `N rows`).

## 3. Frontend — UI components

- [ ] 3.1 Create `apps/web/components/chat/agent-trace.tsx`: reads `traceByMessageId[messageId]` from the store; renders either the live step list, the collapsed chip, or the expanded re-view. Handles click-to-toggle between collapsed/expanded.
- [ ] 3.2 Create `apps/web/components/chat/agent-trace-step.tsx`: one row per step (icon + label + duration + chevron); expandable to show full thought / args / result preview. Apply restrained styling per design (monochrome, single-color error accent, monospace for args/result).
- [ ] 3.3 Add a 1Hz tick (e.g., `useEffect` interval gated on `traceState === "live"`) so running tool steps display elapsed time live.
- [ ] 3.4 Wire `<AgentTrace messageId={message.id} />` into `apps/web/components/chat/message-item.tsx`, rendered above the assistant text bubble for assistant role only.
- [ ] 3.5 Auto-scroll the most recent live step into view when new steps are pushed.
- [ ] 3.6 Cap the live trace block at `max-h-[60vh]` with internal scroll; ensure the assistant bubble remains pinned underneath.
- [ ] 3.7 After reload, when a `traceSummary` exists but no in-memory trace entry, render a non-clickable summary chip that reveals "trace bodies unavailable after reload" on hover/click.

## 4. i18n

- [ ] 4.1 Add to `apps/web/lib/i18n/dictionary.ts` (en + zh): `chat.trace.thoughtFor`, `chat.trace.toolCallsCount`, `chat.trace.errored`, `chat.trace.incomplete`, `chat.trace.expand`, `chat.trace.collapse`, `chat.trace.bodiesUnavailableAfterReload`, `chat.trace.runningElapsed`, `chat.trace.resultRowCount`.

## 5. Tests

- [ ] 5.1 Add `apps/web/tests/ui/agent-trace.test.tsx`: mount with a fake `MessageTrace` in `live` with one running tool step → assert pulsing dot is on that row; flip state to `collapsed` → assert chip shows correct count and duration; click chip → assert state becomes `expanded`.
- [ ] 5.2 Add `apps/web/tests/ui/agent-trace-stream.test.tsx`: feed a sequence of fake SSE events (planning, tool_use A, tool_use B, tool_result B, tool_result A, final) and assert the trace ends with the steps in arrival order, both tools paired correctly by `step_id`, and the trace ends in `collapsed` state.
- [ ] 5.3 Add an error-path test: SSE sequence ending in `error` (no `final`) → trace collapses with error styling and `traceSummary.status === "error"`.
- [ ] 5.4 Add an interruption test: SSE reader closes after one `tool_use` with no matching `tool_result` → trace collapses to `incomplete` and the orphan tool step shows as still-running in the expanded view.
- [ ] 5.5 Update `apps/web/tests/ui/chat-workbench.test.tsx` if any existing assertions fail because trace events now mutate state; do not weaken the assertions, fix the stub event sequences.
- [ ] 5.6 Run `cd apps/web && npx vitest run` — confirm green.

## 6. Manual verification

- [ ] 6.1 `make dev`; in the Designer Conversation panel, send a query that triggers ≥3 tool calls (e.g., "show me headcount by department, then the trend by month"); confirm planning + each tool_use + each tool_result render live with elapsed time on the running step.
- [ ] 6.2 Wait for the turn to finish; confirm trace auto-collapses to a single chip showing duration and tool-call count.
- [ ] 6.3 Click the chip; confirm full trace re-expands; click again; confirm it re-collapses.
- [ ] 6.4 Trigger an error path (e.g., ask something that hits the guardrail); confirm error step renders inline and the collapsed chip uses error styling.
- [ ] 6.5 Reload the page; confirm the assistant message still shows the chip but a fresh click reveals the "bodies unavailable after reload" affordance.
- [ ] 6.6 Compare side-by-side with the published portal chat surface; confirm portal output is unchanged (no trace UI there).

## 7. Documentation

- [ ] 7.1 Update `CLAUDE.md` "SSE event types" line to note that `tool_use` and `tool_result` carry `step_id`/`started_at`/`completed_at`.
- [ ] 7.2 Add a one-paragraph note in `CLAUDE.md` "Frontend → ChatPanel" describing the agent-trace disclosure pattern (live → collapsed → expanded).
