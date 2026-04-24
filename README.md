# Cognitrix

English | [简体中文](README_CN.md)

Cognitrix is an AI-native BI platform for structured data scenarios. The project currently consists of a FastAPI backend, a Next.js frontend, a DuckDB session data layer, and local SQLite state storage. It supports Excel uploads, semantic metric queries, agentic query streaming conversations, chart generation, visual workspaces, saved views, version rollback, and share-view rehydration.

## Current Status

- All 45 tasks across M0-M9 in `SPEC_PLAN.md` have been completed. The project now supports local development, Docker delivery, backend/security/integration/smoke tests, and the main Agentic Query workflow.
- The frontend has evolved from a single-page integration console into a product-style workspace: a global left sidebar manages Conversations / Workspaces, while the center area supports Chat, Canvas, and Split layouts with `Cmd/Ctrl + 1/2/3/B` shortcuts.
- The main Chat entry calls the backend `POST /chat/stream`, consumes `planning/tool_use/tool_result/spec/final/error` SSE events, and archives returned specs as ECharts chart assets. Legacy `reasoning/tool` compatibility events are still retained.
- Workspaces use a React Flow canvas with chart nodes, text nodes, draggable layouts, rename, duplicate, delete, and local persistence.
- The Share page reads backend-saved view state and can re-render charts plus saved conversation context through `/share/[viewId]` without calling the model again.
- The backend already includes upload handling, the semantic layer, a controlled BI tool surface, Claude Agent SDK powered Agentic Query, authorization, audit logging, view versioning, and agent session resume.
- The project is still in prototype/internal-testing stage: frontend Conversations / Workspaces / Chart Assets lists and canvas state are mostly managed through mock APIs and localStorage. The backend already handles real data uploads, queries, agent chat streams, and shared view storage.

## Core Capabilities

### Turn Excel into analyzable data assets

- Business teams can upload arbitrary structured spreadsheets, such as HR, sales, finance, or operations data, without first building a warehouse, writing SQL, or conforming to complex templates.
- The system automatically recognizes common field meanings, combines multiple spreadsheets, and produces datasets that can continue into analysis.
- After upload, it returns data quality feedback so teams can judge whether the data is complete and suitable for further analysis.
- A built-in extensible semantic metric layer, driven by YAML, supports cross-domain metric definitions so business questions can be understood and calculated directly.

### Analyze ad hoc questions through conversation

- Users can ask questions as if speaking with a business analyst, for example "show attrition by department", "find high-risk projects", or "show the distribution by hire year".
- The agent explores table structures, reads samples, chooses semantic metrics, or generates read-only SQL based on the question, reducing manual schema trial-and-error and metric refinement.
- For standard metrics, the system prioritizes stable definitions. For ad hoc questions, the AI analysis assistant can still perform flexible data exploration.
- Answers include results, generated charts, and short takeaways to help users decide what to inspect next.
- Multi-turn conversations retain `agent_session_id` and the latest structured result, supporting follow-ups like "change it to a line chart" or "break it down by department".

### Move from insight to visual workspace

- Charts generated in conversation can be saved as chart assets and then arranged in the workspace.
- Users can switch between conversation, canvas, and split modes, turning one-off Q&A into reusable analytical dashboards.
- Current chart support includes bar, line, pie, area, scatter, funnel, table, and single-metric cards.
- Analysis context is preserved so later follow-ups, filters, and chart adjustments feel natural.

### Make views visible with permissions

- Key analyses can be saved as views and opened through a dedicated presentation entry. Authenticated users can read content they own or are allowed to access.
- The share entry also requires Bearer authentication and redacts saved AI state in the response according to the caller role.
- Private view reads follow owner/admin access rules. Shared views are exposed to authenticated roles through the `views:share` permission.
- A view can be updated and rolled back by version, which is useful for weekly reports, project reviews, and management dashboards that evolve over time.
- Uploads, queries, analysis actions, permission changes, and rollbacks are audited for traceability.

## Tech Stack

- Backend: FastAPI, Pydantic Settings, DuckDB, Pandas, sqlglot, SQLite.
- Agent Runtime: Claude Agent SDK `ClaudeSDKClient`, in-process SDK MCP BI tools, SDK permission callback and hooks, SQLite-persisted agent sessions, guardrails, structured output, SSE tool traces.
- Frontend: Next.js App Router, React 18, TypeScript, Tailwind CSS, Zustand, TanStack Query, React Flow, ECharts.
- Testing: pytest, Vitest / Playwright test files, k6 load-test scripts, smoke flow.
- Delivery: Makefile, Dockerfile, Docker Compose.

## Repository Layout

```text
.
├── apps/api              # FastAPI backend
├── apps/web              # Next.js frontend
├── models                # HR / PM semantic models
├── sample_data           # Example Excel data
├── tests                 # Backend, integration, security, and smoke tests
├── scripts               # Local development, build, test, and reset scripts
├── docs/adr              # Architecture decision records
├── infra/docker          # Alternative Docker Compose files
└── packages/shared       # Shared package placeholder
```

## Requirements

- Python 3.11+
- Node.js 20+
- npm 10+
- GNU Make
- Docker Desktop, optional and only required for container delivery and Docker smoke tests

## Quick Start

Install dependencies and generate local environment files:

```bash
make bootstrap
```

Validate environment variables:

```bash
make env-check
```

Start the local API and Web app:

```bash
make dev
```

Default URLs:

- Web: http://127.0.0.1:3000
- API: http://127.0.0.1:8000
- Health Check: http://127.0.0.1:8000/healthz

`make dev` starts local web/api processes. It does not install or start PostgreSQL. The default state store currently uses local SQLite, and uploaded data, DuckDB files, AI view state, and agent session state all live under `apps/api/data/uploads`.

## Common Commands

```bash
make help              # Show available commands
make bootstrap         # Install Python / Web dependencies and initialize .env files
make env-check         # Validate apps/api/.env and apps/web/.env
make dev               # Start API and Web together
make dev-api           # Start only FastAPI
make dev-web           # Start only Next.js
make dev-local         # Start in debug mode, writing logs to logs/dev-local
make lint              # Backend compileall + frontend lint
make test              # Backend pytest; add frontend tests when RUN_WEB_TESTS=1
make build             # Backend compile check + frontend production build
make smoke-local       # Local end-to-end smoke flow
make smoke-docker      # Docker end-to-end smoke flow
make test-all          # lint + test + build + smoke-local + optional smoke-docker
make reset-local-data  # Clear local runtime data
make docker-up         # Build and start Docker Compose
make docker-down       # Stop Docker Compose
```

Note: `scripts/test.sh` runs backend pytest by default. When `RUN_WEB_TESTS=1` is set, it executes `npm run --prefix apps/web test`, but `apps/web/package.json` does not currently define a `test` script. To run frontend tests, add the package script first or run the corresponding Vitest / Playwright commands directly.

## Local Configuration

`make bootstrap` generates the following files from templates when they are missing:

- `apps/api/.env`
- `apps/web/.env`

Key backend variables:

```env
DATABASE_URL=sqlite:///./data/uploads/state/ai_views.sqlite3
MODEL_PROVIDER_URL=https://api.deepseek.com
AI_API_KEY=
AI_MODEL=deepseek-chat
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_AUTH_TOKEN=
ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-chat
API_TIMEOUT_MS=600000
CLAUDE_AGENT_SDK_ENABLED=true
AGENTIC_INGESTION_ENABLED=true
AUTH_SECRET=replace-with-a-strong-secret
UPLOAD_DIR=./data/uploads
CORS_ALLOW_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
```

Excel uploads always use Agentic ingestion. `AGENTIC_INGESTION_ENABLED` is kept only for compatibility with older environment files and no longer disables `/ingestion/*`.

Key frontend variables:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXTAUTH_URL=http://127.0.0.1:3000
NEXTAUTH_SECRET=replace-with-a-strong-secret
```

The default frontend conversation context can be adjusted through these optional variables:

```env
NEXT_PUBLIC_DEFAULT_USER_ID=demo-user
NEXT_PUBLIC_DEFAULT_PROJECT_ID=demo-project
NEXT_PUBLIC_DEFAULT_ROLE=hr
NEXT_PUBLIC_DEFAULT_DEPARTMENT=HR
NEXT_PUBLIC_DEFAULT_CLEARANCE=1
NEXT_PUBLIC_DEFAULT_DATASET_TABLE=employees_wide
```

Agentic Query runs through the Claude Agent SDK, but defaults to DeepSeek's Anthropic-compatible endpoint. `AI_API_KEY` is passed to the SDK CLI as `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN`; `ANTHROPIC_BASE_URL` defaults to `https://api.deepseek.com/anthropic`; `AI_MODEL` defaults to `deepseek-chat`. If you need to override the Claude Code CLI token separately, set `ANTHROPIC_AUTH_TOKEN`.

## Agentic Query

The conversation entry always uses the agent orchestration path. The older rule-based chat path is no longer a runtime branch.

Agent configuration:

```env
CLAUDE_AGENT_SDK_ENABLED=true
AGENTIC_INGESTION_ENABLED=true
AGENT_MAX_TOOL_STEPS=20
AGENT_MAX_SQL_ROWS=2000
AGENT_MAX_SQL_SCAN_ROWS=10000
AGENT_TIMEOUT_SECONDS=120
```

The agent tool surface is limited to BI-related operations:

- `list_tables`
- `describe_table`
- `sample_rows`
- `get_metric_catalog`
- `run_semantic_query`
- `execute_readonly_sql`
- `get_distinct_values`
- `save_view`

At runtime, `conversation_id` maps to a resumable `agent_session_id`, and session state is persisted to `UPLOAD_DIR/state/agent_sessions.sqlite3`. All tool calls continue to reuse the existing SQL read-only validation, RLS injection, sensitive-field filtering, response redaction, and audit logging.

Current major events from `POST /chat/stream`:

- `planning`
- `tool_use`
- `tool_result`
- `spec`
- `final`
- `error`

Compatibility events:

- `reasoning`
- `tool`

Design details are available in `docs/adr/0001-agentic-query-runtime.md`.

## API Overview

All business APIs except `/healthz` and `/auth/login` require `Authorization: Bearer <token>`. The frontend automatically calls `/auth/login` and caches the token.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/healthz` | Service health check |
| `POST` | `/auth/login` | Issue access token |
| `POST` | `/auth/roles/{user_id}` | Manage user role overrides |
| `GET` | `/audit/events` | Query audit events |
| `POST` | `/ingestion/uploads` | Upload Excel and create an Agentic ingestion job |
| `POST` | `/ingestion/plan` | Generate a write plan through the Write Ingestion Agent |
| `POST` | `/ingestion/approve` | Approve an agent write plan |
| `POST` | `/ingestion/execute` | Execute an approved write plan |
| `GET` | `/semantic/metrics` | Fetch semantic metric catalog |
| `POST` | `/semantic/query` | Run semantic query |
| `POST` | `/chat/tool-call` | Call BI tools directly |
| `POST` | `/chat/stream` | Stream AI conversation and chart generation |
| `POST` | `/views` | Save AI view |
| `GET` | `/views/{view_id}` | Read private view |
| `GET` | `/share/{view_id}` | Read shared view |
| `POST` | `/views/{view_id}/rollback/{version}` | Roll back a view version |

## End-to-End Validation

Local smoke flow:

```bash
make smoke-local
```

Covered workflow:

```text
healthz -> auth/login -> upload Excel -> semantic query -> chat stream -> save view -> share view
```

Full quality gate:

```bash
make test-all
```

You can also run more focused checks as needed:

```bash
.venv/bin/python -m pytest tests -q
.venv/bin/python -m pytest tests/security -q
.venv/bin/python -m pytest tests/integration -q
npm run --prefix apps/web build
```

## Docker Delivery

Build and start:

```bash
docker compose up -d --build
docker compose ps
```

Stop:

```bash
docker compose down --remove-orphans
```

Make wrappers:

```bash
make docker-up
make docker-down
make smoke-docker
```

Default Compose exposure:

- Web: `127.0.0.1:3000`
- API: `127.0.0.1:8000`

Uploads and state data are stored in the Docker named volume `cognitrix_upload_data`.

## Data Reset

Clear local runtime data, uploads, DuckDB / SQLite state, logs, and test artifacts:

```bash
make reset-local-data
```

Preview what will be deleted:

```bash
.venv/bin/python scripts/reset_local_data.py --dry-run
```

Also reset the database referenced by `apps/api/.env`:

```bash
.venv/bin/python scripts/reset_local_data.py --with-db-reset
```

Also remove Docker Compose named volumes:

```bash
.venv/bin/python scripts/reset_local_data.py --include-docker-volumes
```

## Sample Data

Excel samples available for local upload validation:

- `sample_data/galaxyspace-hr-sample.xlsx`
- `sample_data/hr_workforce_upload_sample.xlsx`
- `sample_data/hr_workforce_upload_sample_zh.xlsx`

After upload, the API returns `batch_id`, `dataset_table`, `quality_report`, `diagnostics`, and other fields. Later semantic query and chat requests should use the returned `dataset_table`.

## Known Boundaries

- Frontend session, workspace, and chart asset lists are still mock/localStorage based, and are not equivalent to backend-persisted objects. Browser refresh can restore local state, but switching devices or clearing cache will not sync it automatically.
- `ChatWorkbench` is still kept for testing/integration purposes, while the current main route renders `AppShell`.
- The default `NEXT_PUBLIC_DEFAULT_DATASET_TABLE=employees_wide` must align with the actual DuckDB session table. After uploading a new file, use the returned `dataset_table`.
- Agent mode has runtime and test coverage, but production model integration, evaluation set expansion, cost control, and long-session UX still need more iteration.
- Frontend test files and configuration exist, but `package.json` does not currently provide unified `npm test` / `test:ui` / `test:e2e` script entries. These should be organized before wiring them into `make test`.
