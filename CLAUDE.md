# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Cognitrix (识枢) is an AI-Native BI platform for any structured data domain. It combines a FastAPI backend, Next.js frontend, DuckDB session data layer, and local SQLite state store. Users upload Excel data and query it via conversational AI through the Claude Agent SDK.

## Commands

### Setup
```bash
make bootstrap        # Install Python/web deps and generate .env files from templates
make env-check        # Validate apps/api/.env and apps/web/.env
```

### Development
```bash
make dev              # Start API (port 8000) and Web (port 3000) together
make dev-api          # FastAPI only (uvicorn, hot-reload)
make dev-web          # Next.js only (turbopack)
make dev-local        # Debug mode with logs written to logs/dev-local
```

### Testing
```bash
# Backend tests (pytest)
make test
.venv/bin/python -m pytest tests -q
.venv/bin/python -m pytest tests/unit/test_agent_runtime.py -q   # single test file
.venv/bin/python -m pytest tests/security -q
.venv/bin/python -m pytest tests/integration -q

# Frontend unit tests (Vitest, jsdom)
cd apps/web && npx vitest run
cd apps/web && npx vitest run tests/ui/global-sidebar.test.tsx   # single test

# Frontend e2e tests (Playwright)
cd apps/web && npx playwright test

# Full gate: lint + test + build + smoke
make test-all
```

### Lint & Build
```bash
make lint             # Backend: python -m compileall; Frontend: next lint
make build            # Frontend production build + backend compile check
```

### Smoke & Docker
```bash
make smoke-local      # End-to-end: healthz → login → upload → query → chat → save → share
make docker-up        # Build and start Docker Compose stack
make docker-down      # Stop Docker Compose
make smoke-docker     # Smoke flow against the Docker stack
make reset-local-data # Clear uploads, DuckDB/SQLite state, logs, test artifacts
```

## Architecture

### Backend (`apps/api/`)

FastAPI app defined in `main.py`. All routes (except `/healthz` and `/auth/login`) require `Authorization: Bearer <token>`.

**Key modules:**
- `auth.py` — JWT-based token issuance, `AuthIdentity`, RBAC permission scopes (`require_permission`), role overrides stored in-process
- `security.py` — `SQLReadOnlyValidator`, `RLSInjector`, `AccessContext`; combined through `secure_query_sql()`
- `data_policy.py` — `redact_rows()`, `redact_structure()`, `forbidden_sensitive_columns()` based on role
- `agent_runtime.py` — thin host around Claude Agent SDK `ClaudeSDKClient`; exposes BI tools as an in-process SDK MCP server named `cognitrix`; maps SDK stream/hook events to frontend SSE format
- `chat.py` — `ChatStreamService` routes `POST /chat/stream` into `AgentRuntime.run_turn()`
- `agent_guardrails.py` — blocks jailbreak attempts, validates tool names and SQL before execution
- `tool_calling.py` — `ToolCallingService`; executes the 8 BI tools (list_tables, describe_table, sample_rows, get_metric_catalog, run_semantic_query, execute_readonly_sql, get_distinct_values, save_view)
- `semantic.py` — metric registry, `IntentParser`, `MetricCompiler`; semantic layer lives in `models/` YAML files
- `datasets.py` — DuckDB session manager, per-user/project connection isolation
- `views.py` — SQLite-backed view persistence with versioning and rollback
- `workspaces.py` — workspace RBAC enforcement; router mounted at `/workspaces`
- `agentic_ingestion/` — isolated write-ingestion lifecycle (plan → approve → execute); uses Claude Agent SDK separately from query runtime
- `audit.py` — structured audit logger; every significant action emits an audit event

**Data flow for a chat turn:**
1. `POST /chat/stream` → `ChatStreamService` → `AgentRuntime.run_turn()`
2. `AgentGuardrails` validates the user message
3. SDK system prompt assembled from: static BI prompt + dataset hints + user role/RLS context + previous structured result
4. `ClaudeSDKClient` runs with in-process MCP server; `PreToolUse`/`PostToolUse`/`PostToolUseFailure` hooks emit SSE events and write audit entries
5. Each MCP tool handler calls `ToolCallingService` → `secure_query_sql()` → DuckDB
6. SDK returns structured final answer (JSON schema); normalized to ECharts/Recharts spec and emitted as `spec` + `final` SSE events
7. Session state persisted to `UPLOAD_DIR/state/agent_sessions.sqlite3`

**SSE event types:** `planning`, `tool_use`, `tool_result`, `spec`, `final`, `error` (plus legacy mirrors `reasoning`, `tool`)

**Session model:** `conversation_id → agent_session_id → AgentSessionState` persisted in SQLite; hot in-memory cache avoids DB reads on consecutive turns

### Frontend (`apps/web/`)

Next.js App Router. Single entry page renders `<AppShell />`.

**Layout:**
- `AppShell` — top-level shell with `GlobalSidebar` + panel switching (`chat` / `workspace` / `both`)
- Keyboard shortcuts: `⌘/Ctrl+1` (chat), `+2` (workspace), `+3` (split), `+B` (toggle sidebar)
- `ChatPanel` — calls `POST /chat/stream`, consumes SSE events, archives returned specs as chart assets
- `WorkspacePanel` — React Flow canvas with chart nodes, text nodes, drag-layout, local save

**State management:**
- `ui-store.ts` (Zustand) — active panel, sidebar open state
- `chat-store.ts` (Zustand) — chat sessions and messages
- `workspace-store.ts` (Zustand) — workspaces and active workspace; session/workspace/chart-asset lists are currently mock/localStorage backed (not synced to backend)
- `asset-store.ts` (Zustand) — chart assets
- TanStack Query — API calls in `hooks/use-chat.ts`, `hooks/use-workspace.ts`, `hooks/use-chart-assets.ts`

**API client lives in `lib/`:** `lib/auth/`, `lib/chat/`, `lib/workspace/`, `lib/ingestion/`

**Chart rendering:** ECharts for advanced types (heatmap, gauge, sankey, sunburst, boxplot, graph, map, multi-series line); Recharts for common types (bar, line, pie, area, scatter, funnel, table, single_value)

**Auth:** Next.js calls `/auth/login` at session start and caches the Bearer token; all API requests attach it automatically.

### Ingestion Pipeline (`apps/api/agentic_ingestion/`)

Three-phase lifecycle, isolated from query runtime:
1. `POST /ingestion/uploads` — upload Excel, trigger planning Agent
2. `POST /ingestion/plan` — Write Ingestion Agent generates a schema proposal
3. `POST /ingestion/approve` — human approves/overrides the plan
4. `POST /ingestion/execute` — approved plan written to DuckDB

The ingestion Agent also uses Claude Agent SDK in-process MCP tools, with DuckDB write access restricted to approved schema only. SQL identifiers and DuckDB type names are validated against strict regexes (`SAFE_IDENTIFIER_RE`, `SAFE_DUCKDB_TYPE_RE`) before any DDL executes.

### Data Storage

All runtime data lives under `UPLOAD_DIR` (`apps/api/data/uploads/` locally):
- `*.duckdb` — per-user/project DuckDB session files
- `state/ai_views.sqlite3` — saved views and versions
- `state/agent_sessions.sqlite3` — resumable agent session state

### Models / Semantic Layer (`models/`)

HR and PM metric definitions in YAML, loaded by `SemanticRegistry`. Metrics map business intent strings to parameterized SQL templates with RLS-aware group-by and filter support.

### Tests (`tests/`)

- `tests/api/` — FastAPI route tests (httpx `TestClient`)
- `tests/unit/` — pure unit tests for runtime modules, security, semantic DSL
- `tests/integration/` — DuckDB isolation, agent runtime, full tool-calling chain
- `tests/security/` — SQL injection, RLS bypass, sensitive column access
- `tests/e2e/` — Playwright browser tests (run against built Next.js)
- `tests/agentic_ingestion_fakes.py` — shared fakes for ingestion tests

Frontend tests in `apps/web/tests/` use Vitest (unit, jsdom) and Playwright (e2e).

## Key Configuration

Backend `.env` (generated by `make bootstrap`):
- `AI_API_KEY` / `ANTHROPIC_AUTH_TOKEN` — provider auth (DeepSeek by default)
- `ANTHROPIC_BASE_URL` — defaults to DeepSeek's Anthropic-compatible endpoint
- `AI_MODEL` — defaults to `deepseek-chat`; the Agent SDK routes through this provider
- `CLAUDE_AGENT_SDK_ENABLED=true` — required; Agent runtime is the only chat path
- `AGENT_MAX_TOOL_STEPS`, `AGENT_MAX_SQL_ROWS`, `AGENT_TIMEOUT_SECONDS` — Agent loop limits
- `DATABASE_URL` — SQLite for view state (not DuckDB)

Frontend `.env`:
- `NEXT_PUBLIC_DEFAULT_DATASET_TABLE` — must match the DuckDB table from the last upload; update after uploading new data
- `NEXT_PUBLIC_API_BASE_URL`, `NEXTAUTH_URL`, `NEXTAUTH_SECRET`

## Sample Data

Upload these files via the ingestion UI or `POST /ingestion/uploads` to create a working DuckDB session:
- `sample_data/galaxyspace-hr-sample.xlsx`
- `sample_data/hr_workforce_upload_sample.xlsx`

After upload, use the returned `dataset_table` for subsequent chat and semantic queries.

## Architecture Decision Records

- `docs/adr/0001-agentic-query-runtime.md` — why Claude Agent SDK is the sole chat engine; session model; guardrails; output normalization; SSE contract
- `docs/adr/0002-excel-upload-ingestion-current-state.md` — legacy upload context
- `docs/adr/0003-workspace-scoped-agentic-ingestion.md` — why ingestion has its own module and lifecycle phases
