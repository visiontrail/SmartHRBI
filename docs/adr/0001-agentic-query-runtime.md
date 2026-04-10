# ADR-0001 Agentic Query Runtime

## Status

Accepted, implemented in M9.

## Context

The original SmartHRBI chat path used a deterministic flow:

1. Parse user intent with `IntentParser`.
2. Map the request to a fixed tool.
3. Compile semantic SQL or render a small set of canned responses.

That path is stable for predefined metrics, but it breaks on long-tail questions such as:

- "柱状图显示入职年份统计"
- "按地区看离职人数趋势"
- "展示项目延期率并标出高风险项目"

These requests require schema exploration, sample inspection, fallback SQL planning, and multi-step reasoning that the original metric matcher does not support.

## Decision

We introduce an Agentic Query runtime with these decisions:

1. `POST /chat/stream` remains the single frontend entrypoint.
2. Backend orchestration now supports three modes through `CHAT_ENGINE`:
   - `deterministic`
   - `agent_shadow`
   - `agent_primary`
3. `AgentRuntime` is the new orchestration layer for agent mode.
4. Conversation state is modeled as:
   - `conversation_id -> agent_session_id -> persisted session state`
5. Session persistence is stored in a local sqlite file under `UPLOAD_DIR/state/agent_sessions.sqlite3`.
6. The tool surface is restricted to BI-specific tools:
   - `list_tables`
   - `describe_table`
   - `sample_rows`
   - `get_metric_catalog`
   - `run_semantic_query`
   - `execute_readonly_sql`
   - `get_distinct_values`
   - `save_view`
7. All data access still reuses the existing secure backend chain:
   - readonly SQL guard
   - RLS injection
   - sensitive column filtering
   - response redaction
   - structured audit logging
8. SSE now emits agent-native events:
   - `planning`
   - `tool_use`
   - `tool_result`
   - `spec`
   - `final`
   - `error`
9. Compatibility mirrors are still emitted for legacy consumers:
   - `reasoning`
   - `tool`

## Claude Agent SDK Positioning

`AgentRuntime` is shaped around a Claude Agent SDK style session model, with `agent_session_id`, hot session caching, persisted recovery, and tool-first execution. The current runtime uses an in-process simulated adapter when the SDK is not installed or not enabled, so local development and tests remain self-contained.

This keeps the production integration path open while avoiding hard dependency on an external agent runtime in local CI.

## Alternatives Considered

### 1. Keep extending `IntentParser`

Rejected. The parser would continue to grow brittle and still lack schema-first exploration for unknown requests.

### 2. Replace the semantic layer with free-form SQL generation

Rejected. That would weaken safety and discard existing semantic definitions that already work well for common KPIs.

### 3. Add a second public API for agent mode

Rejected. It would complicate frontend integration and split observability between two chat surfaces.

## Migration Plan

1. Add `AgentRuntime`, persisted agent sessions, and BI-only tools.
2. Add guardrails and audit hooks around every tool invocation.
3. Upgrade SSE to expose planning and tool traces.
4. Gate rollout with `CHAT_ENGINE`.
5. Keep deterministic mode as the immediate rollback path.

## Reused Modules

- `ToolCallingService`
- `ChartStrategyRouter`
- `SQLReadOnlyValidator`
- `RLSInjector`
- `redact_rows` and schema filtering
- `AuditLogger`
- `ViewStorageService`

## Replaced or Wrapped Modules

- `ChatStreamService` now selects between deterministic orchestration and `AgentRuntime`.
- Deterministic tool routing remains available but no longer owns the only chat path.

## Consequences

Positive:

- Long-tail BI questions can inspect schema and sample rows before querying.
- Session continuity works across turns and service restarts.
- The system keeps a one-step rollback switch.

Tradeoffs:

- Agent mode is slower than deterministic mode.
- Tool traces and session state increase storage and audit volume.
- SQL planning heuristics still need evaluation and incremental hardening.
