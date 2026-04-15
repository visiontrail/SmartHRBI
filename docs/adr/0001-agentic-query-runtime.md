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

The current implementation uses Claude Agent SDK as the primary agent runtime.
`apps/api/agent_runtime.py` is now a thin host around SDK capabilities: it
constructs SDK options, exposes SmartHRBI BI tools as an in-process SDK MCP
server, maps SDK stream/hook events into the frontend SSE contract, and keeps
SmartHRBI-specific chart normalization and persistence.

At a high level, one chat turn is executed as:

1. `ChatStreamService` receives `POST /chat/stream` and builds an
   `AgentRequest`.
2. `AgentRuntime.run_turn()` loads or creates the session for
   `conversation_id`.
3. `AgentGuardrails` validates the user message before starting the SDK client.
4. `AgentRuntime` composes the SDK system prompt from:
   - the static BI analyst prompt,
   - active dataset and available table hints,
   - user role and RLS context,
   - the previous structured result when available.
5. `AgentRuntime` creates a Claude Agent SDK in-process MCP server with
   `create_sdk_mcp_server()` and `@tool` handlers for the SmartHRBI BI tools.
6. `ClaudeSDKClient` is started with:
   - `tools=[]` so Claude Code built-in filesystem/shell/browser tools are not
     part of the base tool surface;
   - `mcp_servers={"smarthrbi": sdk_server}`;
   - `can_use_tool` for SDK permission decisions;
   - `PreToolUse` / `PostToolUse` / `PostToolUseFailure` hooks for deterministic
     validation, audit, and SSE tracing;
   - `max_turns=AGENT_MAX_TOOL_STEPS`;
   - `output_format={"type": "json_schema", ...}` for the final structured
     answer.
7. Claude Agent SDK owns tool selection, the agent loop, tool result appending,
   and final structured-output completion.
8. Each MCP tool handler executes the existing BI data path through
   `ToolCallingService`.
9. The final structured answer is normalized into a frontend chart/table spec
   and emitted as SSE events.
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

Claude Agent SDK owns the live conversation transcript through
`ClaudeSDKClient` and the SDK session id. SmartHRBI stores the same
`agent_session_id` plus the latest structured result/spec/tool trace in SQLite
so service restarts and frontend state recovery can reattach to the known
conversation. The previous structured result is also summarized into the
system context so follow-up requests such as "改成折线图" can reuse the last
result without forcing the model to rediscover the dataset.

### Tool Surface

The runtime exposes a narrow BI tool registry as an SDK MCP server named
`smarthrbi`:

- `list_tables`
- `describe_table`
- `sample_rows`
- `get_distinct_values`
- `get_metric_catalog`
- `run_semantic_query`
- `execute_readonly_sql`
- `save_view`

There is no longer a virtual `submit_answer` tool. Finalization uses Claude
Agent SDK structured output (`output_format`) with the same chart/table answer
schema.

For every SDK MCP tool call:

1. SDK permission flow calls `can_use_tool`;
2. `PreToolUse` validates the tool name and arguments with `AgentGuardrails`,
   emits `tool_use`, and writes an `agent_pre_tool_use` audit entry;
3. the SDK MCP handler invokes `ToolCallingService` with request identity,
   role, department, clearance, dataset table, and an idempotency key;
4. `PostToolUse` emits `tool_result` plus legacy `tool` mirror events and writes
   an `agent_post_tool_use` audit entry;
5. Claude Agent SDK appends the MCP tool result back into the model context.

This keeps tool execution deterministic and auditable even though the model
chooses the tool sequence and the SDK owns the loop.

### Guardrails

`AgentGuardrails` applies SmartHRBI domain checks before and during SDK tool
permission/hook flow:

- user messages that ask for system prompts, shell/filesystem access, web
  access, or instruction override are blocked;
- sensitive columns forbidden for the caller's role are rejected early;
- only `mcp__smarthrbi__*` BI tools can be called;
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

If the SDK run does not return a usable structured answer but has successful
grounding tool observations, the runtime attempts a conservative recovery from
the latest tool result. If no successful grounding observation exists, it
returns an empty spec instead of producing an ungrounded answer.

## Claude Agent SDK Positioning

`AgentRuntime` now directly instantiates `ClaudeSDKClient` and uses SDK-native
capabilities wherever they map cleanly to SmartHRBI's product requirements.
SmartHRBI code remains responsible for BI domain execution, security policy,
frontend SSE compatibility, and visualization-spec normalization.

The SDK capabilities used directly are:

1. **Resumable session model**

   The SDK-style `agent_session_id` is first-class in runtime state, SSE events,
   AI state, and persisted storage. SmartHRBI maps:

   - `conversation_id -> agent_session_id -> persisted AgentSessionState`

   `ClaudeSDKClient` receives the SDK session id via `session_id`/`resume`.
   SmartHRBI persists the id and latest app state for hot cache eviction and
   process restart recovery.

2. **Tool-first agent execution**

   The model receives an SDK MCP tool surface and Claude Agent SDK owns the
   tool-selection and bounded agent loop. SmartHRBI rejects ungrounded final
   answers when no current or prior successful BI observation exists.

3. **Custom tool definitions**

   The BI tools are implemented with the SDK `@tool` decorator and exposed via
   `create_sdk_mcp_server()` as in-process MCP tools.

4. **Permission boundary**

   SDK `tools=[]`, SDK MCP configuration, SDK `can_use_tool`, and SDK
   `PreToolUse` hooks enforce a least-privilege surface: the agent can only call
   SmartHRBI BI tools and cannot access shell, filesystem, browser, or arbitrary
   network tools.

5. **PreToolUse/PostToolUse hook semantics**

   The SDK hook lifecycle is used around every tool invocation:

   - pre-tool: validate the tool call, enforce budgets, emit `tool_use`, and
     audit `agent_pre_tool_use`;
   - post-tool: emit `tool_result` and audit `agent_post_tool_use`; the SDK
     owns appending the tool result back into the agent message stream.

   These hooks are SDK hook callbacks, not a hand-rolled hook simulation.

6. **Streaming/event surface**

   SDK agent stream and hook events are translated into the frontend SSE
   contract:

   - `planning`
   - `tool_use`
   - `tool_result`
   - `spec`
   - `final`
   - `error`

   Legacy consumers still receive `reasoning` and `tool` compatibility mirrors.

7. **MCP-compatible boundary**

   The current runtime uses an in-process SDK MCP server. The MCP tool handlers
   delegate to `ToolCallingService` so the existing secure BI data path remains
   the single execution implementation.

The `claude-agent-sdk` dependency and `CLAUDE_AGENT_SDK_ENABLED=true` setting
therefore mark the production agent architecture and integration boundary.

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
