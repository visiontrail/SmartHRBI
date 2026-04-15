# ADR-0001 Agentic Query Runtime

## Context

The original SmartHRBI chat path used a fixed rule-based flow:

1. Parse user intent with `IntentParser`.
2. Map the request to a fixed tool.
3. Compile semantic SQL or render a small set of canned responses.

That path is stable for predefined metrics, but it breaks on long-tail questions such as:

- "Show a bar chart of hire year distribution"
- "View turnover trends by region"
- "Display project delay rates and highlight high-risk projects"

These requests require schema exploration, sample inspection, fallback SQL planning, and multi-step reasoning that the original metric matcher does not support.

## Decision

We introduce an Agentic Query runtime with these decisions:

1. `POST /chat/stream` remains the single frontend entrypoint.
2. Backend orchestration uses the Agent runtime as the single chat path.
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

## `AgentRuntime` Implementation

The current implementation is a self-developed orchestration layer in
`apps/api/agent_runtime.py`. It owns the whole agent turn lifecycle instead of
delegating orchestration to the old fixed chat router.

At a high level, one chat turn is executed as:

1. `ChatStreamService` receives `POST /chat/stream` and builds an
   `AgentRequest`.
2. `AgentRuntime.run_turn()` loads or creates the session for
   `conversation_id`.
3. `AgentGuardrails` validates the user message before any LLM call.
4. `AgentRuntime` composes the system prompt from:
   - the static BI analyst prompt,
   - active dataset and available table hints,
   - user role and RLS context,
   - the previous turn result when available.
5. `AnthropicAgentClient` sends the conversation to an OpenAI-compatible
   Chat Completions endpoint with function-calling tool definitions.
6. The runtime runs a bounded ReAct/tool loop up to `AGENT_MAX_TOOL_STEPS`.
7. Each model tool call is validated, audited, executed through
   `ToolCallingService`, and appended back to the model as a tool result.
8. The turn ends when the model calls the virtual `submit_answer` tool, returns
   parseable structured JSON, or exhausts the bounded loop.
9. The final answer is normalized into a frontend chart/table spec and emitted
   as SSE events.
10. Session state and the latest AI state are persisted for follow-up turns and
    restart recovery.

### Session Model

`AgentSessionState` is the durable session object. It stores:

- `conversation_id`
- `agent_session_id`
- recent `history`
- `last_result`
- `last_spec`
- `last_tool_trace`
- `turn_count`
- `runtime_backend`

`AgentSessionStore` persists this state in
`UPLOAD_DIR/state/agent_sessions.sqlite3`. `AgentRuntime` also keeps a hot
in-memory session cache keyed by `conversation_id`, so normal multi-turn
conversations avoid a database read while service restarts can still recover
the same `agent_session_id`.

Only the latest ten user/assistant messages are replayed into the LLM request.
The previous structured result is additionally summarized into the system
context so follow-up requests such as "改成折线图" can reuse the last result
without forcing the model to rediscover the dataset.

### Tool Loop

The runtime exposes a narrow BI tool registry through `AGENT_TOOL_DEFINITIONS`:

- `list_tables`
- `describe_table`
- `sample_rows`
- `get_distinct_values`
- `get_metric_catalog`
- `run_semantic_query`
- `execute_readonly_sql`
- `save_view`
- `submit_answer`

`submit_answer` is a virtual finalization tool. It is not executed by
`ToolCallingService`; the runtime acknowledges it and uses its arguments as the
structured final answer. All other tools are delegated to `ToolCallingService`,
which keeps the existing secure data path in place.

For every non-final tool call, `AgentRuntime`:

1. validates the tool name and arguments with `AgentGuardrails`;
2. emits a `tool_use` event and writes an `agent_pre_tool_use` audit entry;
3. invokes `ToolCallingService` with request identity, role, department,
   clearance, dataset table, and an idempotency key;
4. emits `tool_result` plus legacy `tool` mirror events;
5. writes an `agent_post_tool_use` audit entry;
6. appends the result to the LLM message list as a tool response.

This keeps tool execution deterministic and auditable even though the model
chooses the tool sequence.

### Guardrails

`AgentGuardrails` applies checks before and during the loop:

- user messages that ask for system prompts, shell/filesystem access, web
  access, or instruction override are blocked;
- sensitive columns forbidden for the caller's role are rejected early;
- only the BI allowlisted tools can be called;
- `execute_readonly_sql` must contain SQL and cannot use write/DDL verbs;
- oversized SQL result limits and scan budgets are rejected before execution.

The actual SQL execution still goes through the existing readonly validator,
RLS injector, sensitive column filter, response redaction, and audit logger in
the backend data stack.

### Output Normalization

The model is required to produce a structured final answer with chart metadata,
rows, conclusion, scope, and anomaly notes. `AgentRuntime` converts that answer
into the frontend visualization spec:

- Recharts for common chart types such as `bar`, `line`, `pie`, `area`,
  `scatter`, `radar`, `treemap`, `funnel`, `radialBar`, `composed`, `table`,
  and `single_value`;
- ECharts for advanced chart types such as `heatmap`, `gauge`, `sankey`,
  `sunburst`, `boxplot`, `graph`, and `map`.

If the model fails to call `submit_answer` but has successful grounding tool
observations, the runtime attempts a conservative recovery from the latest tool
result. If no successful grounding observation exists, it returns an empty spec
instead of producing an ungrounded answer.

## Claude Agent SDK Positioning

`AgentRuntime` is intentionally shaped around Claude Agent SDK concepts, but the
current code does not directly instantiate `ClaudeSDKClient`. Instead, it maps
the SDK's agent capabilities onto an in-process Python orchestration layer and
an OpenAI-compatible Chat Completions function-calling adapter. This keeps the
runtime portable across providers while preserving a clear migration path to a
native Claude Agent SDK client.

The SDK capabilities used or mirrored are:

1. **Resumable session model**

   The SDK-style `agent_session_id` is first-class in runtime state, SSE events,
   AI state, and persisted storage. SmartHRBI maps:

   - `conversation_id -> agent_session_id -> persisted AgentSessionState`

   This mirrors a long-lived agent session that can survive hot cache eviction
   and process restarts.

2. **Tool-first agent execution**

   The model is not asked to answer from prior knowledge. It receives a tool
   surface and must inspect schema, samples, metrics, or SQL results before
   finalizing. This follows the SDK pattern where the agent's progress is
   expressed as tool use and tool results rather than a single opaque text
   completion.

3. **Custom tool definitions**

   The BI tools are described with JSON schemas equivalent to SDK custom tool
   contracts. The runtime currently transports them through Chat Completions
   `tools` / `tool_choice=auto`, then parses returned tool calls into internal
   `AnthropicToolCall` objects.

4. **Permission boundary**

   Claude Agent SDK permission controls are represented by
   `AgentGuardrails.allowed_tools`, prompt restrictions, SQL budget checks, and
   role-aware sensitive field checks. The effective permission model is
   least-privilege: the agent can only call SmartHRBI BI tools and cannot access
   shell, filesystem, browser, or arbitrary network tools.

5. **PreToolUse/PostToolUse hook semantics**

   The SDK hook lifecycle is mirrored around every tool invocation:

   - pre-tool: validate the tool call, enforce budgets, emit `tool_use`, and
     audit `agent_pre_tool_use`;
   - post-tool: emit `tool_result`, audit `agent_post_tool_use`, and append the
     result back into the agent message stream.

   These hooks are implemented in-process today instead of using SDK hook APIs.

6. **Streaming/event surface**

   SDK-style agent stream events are translated into the frontend SSE contract:

   - `planning`
   - `tool_use`
   - `tool_result`
   - `spec`
   - `final`
   - `error`

   Legacy consumers still receive `reasoning` and `tool` compatibility mirrors.

7. **MCP-compatible boundary**

   The current runtime keeps tools in process behind `ToolCallingService`
   instead of exposing a separate MCP server. The tool registry and permission
   boundary are deliberately shaped so the same BI tools can later be exposed as
   SDK MCP tools without changing the frontend API or security model.

The `claude-agent-sdk` dependency and `CLAUDE_AGENT_SDK_ENABLED=true` setting
therefore mark the intended agent architecture and integration boundary. The
production path today is the self-developed `AgentRuntime` plus compatible tool
calling adapter; a future native SDK swap should be an adapter replacement, not
a frontend or data-access rewrite.

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
4. Keep the Agent runtime as the only supported chat path.

## Reused Modules

- `ToolCallingService`
- `ChartStrategyRouter`
- `SQLReadOnlyValidator`
- `RLSInjector`
- `redact_rows` and schema filtering
- `AuditLogger`
- `ViewStorageService`

## Replaced or Wrapped Modules

- `ChatStreamService` now routes chat requests directly through `AgentRuntime`.
- Legacy tool routing no longer owns a runtime mode.

## Consequences

Positive:

- Long-tail BI questions can inspect schema and sample rows before querying.
- Session continuity works across turns and service restarts.
- The system keeps a one-step rollback switch.

Tradeoffs:

- Agent runtime has higher latency than the retired fixed tool-routing path.
- Tool traces and session state increase storage and audit volume.
- SQL planning heuristics still need evaluation and incremental hardening.
