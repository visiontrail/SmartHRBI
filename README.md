# SmartHRBI

SmartHRBI is an AI-Native HR/PM BI system scaffold with FastAPI + DuckDB backend and Next.js frontend.

## Prerequisites

- Python 3.11+
- Node.js 20+
- npm 10+
- GNU Make
- Docker Desktop (recommended, used for PostgreSQL auto-start and full container delivery)

## Quick Start (Local)

1. Install dependencies and generate local env files:

```bash
make bootstrap
```

2. Validate environment variables:

```bash
make env-check
```

3. Start local stack (web + api + postgres):

```bash
make dev
```

`make dev` starts web/api processes locally and ensures PostgreSQL is reachable.
If local PostgreSQL is not running, it attempts to start `postgres` via Docker Compose.

## Local Debug Start (No Docker)

If you only want local debug startup and do not want any Docker auto-bootstrap:

```bash
make dev-local
```

Equivalent direct script:

```bash
bash scripts/dev_local_debug.sh
```

`dev-local` is intended for debug only. It skips PostgreSQL bootstrap and reachability checks, so API startup does not depend on a local PostgreSQL process.

## Local Smoke Validation

Run complete smoke flow:

```bash
make smoke-local
```

Smoke flow covers: `upload -> semantic query -> chat stream -> save view -> share view`.

## Docker Delivery

Build and run full stack:

```bash
docker compose up -d --build
docker compose ps
```

Stop stack:

```bash
docker compose down --remove-orphans
```

Or use wrappers:

```bash
make docker-up
make docker-down
```

Run Docker smoke flow:

```bash
make smoke-docker
```

## Reset Local Runtime/Test Data

To clear local runtime state, uploaded datasets, persisted chat/view session state, DuckDB/SQLite files under `UPLOAD_DIR`, and local test artifacts:

```bash
.venv/bin/python scripts/reset_local_data.py
```

One-command shell wrapper:

```bash
bash scripts/reset_local_data.sh
```

Preview what would be deleted without changing anything:

```bash
.venv/bin/python scripts/reset_local_data.py --dry-run
```

If you explicitly also want to reset the database referenced by `apps/api/.env`:

```bash
.venv/bin/python scripts/reset_local_data.py --with-db-reset
```

If you also want to remove Docker Compose named volumes for the local stack:

```bash
.venv/bin/python scripts/reset_local_data.py --include-docker-volumes
```

Equivalent Make target:

```bash
make reset-local-data
```

## Full Test Gate

Run lint, backend/frontend tests, build, and local smoke in one command:

```bash
make test-all
```

If Docker is available, `make test-all` also executes Docker smoke by default.

## Repository Layout

- `apps/web`: Next.js App Router frontend
- `apps/api`: FastAPI backend
- `packages/shared`: Shared contracts and helper modules
- `infra/docker`: Alternative compose file location
- `tests`: Backend tests + smoke scripts
- `scripts`: Build/test/dev automation scripts

## Standard Commands

```bash
make help
make bootstrap
make env-check
make lint
make test
make build
make dev
make dev-local
make smoke-local
make smoke-docker
make test-all
make docker-up
make docker-down
```

## OpenAI Compatible LLM Setup

`apps/api` now supports OpenAI-compatible chat completion endpoints for tool routing.

Set these in `apps/api/.env`:

- `MODEL_PROVIDER_URL`: provider base URL (for example `https://api.openai.com`)
- `AI_API_KEY`: API key used in `Authorization: Bearer ...`
- `AI_MODEL`: model name (for example `gpt-4o-mini`, `qwen-plus`, etc.)
- `AI_TIMEOUT_SECONDS`: HTTP timeout for LLM routing calls

When `AI_API_KEY` is empty, chat falls back to deterministic rule routing.

## Agentic Query Mode

M9 adds an Agentic Query runtime behind the same `POST /chat/stream` API.

Set these in `apps/api/.env` to control rollout:

- `CHAT_ENGINE`: `deterministic`, `agent_shadow`, or `agent_primary`
- `CHAT_ENGINE_USERS`: optional comma-separated allowlist; non-listed users fall back to `deterministic`
- `CLAUDE_AGENT_SDK_ENABLED`: must be `true` for `agent_primary`/`agent_shadow`; startup rejects agent mode otherwise
- `AGENT_MAX_TOOL_STEPS`: maximum tool steps per query
- `AGENT_MAX_SQL_ROWS`: maximum rows returned by `execute_readonly_sql`
- `AGENT_MAX_SQL_SCAN_ROWS`: hard cap for SQL scan-oriented limits
- `AGENT_TIMEOUT_SECONDS`: end-to-end agent timeout budget

Agent mode uses a BI-only tool surface:

- `list_tables`
- `describe_table`
- `sample_rows`
- `get_metric_catalog`
- `run_semantic_query`
- `execute_readonly_sql`
- `get_distinct_values`
- `save_view`

All agent SQL still goes through the existing readonly guard, RLS injection, sensitive-column filtering, response redaction, and audit logging.

## M9 Verification

Key M9 verification commands:

```bash
.venv/bin/python -m pytest tests/integration/test_agent_runtime.py tests/integration/test_agent_tools.py tests/integration/test_agent_chat_stream.py tests/integration/test_chat_engine_switch.py tests/security/test_agent_guardrails.py tests/evals/test_agent_prompting.py -q
.venv/bin/python -m pytest tests -q
npm --prefix apps/web run test
npm --prefix apps/web run build
```

An ADR for the runtime design is available at [`docs/adr/0001-agentic-query-runtime.md`](/Users/guoliang/Desktop/workspace/code/GalaxySpace/GalaxySpaceAI/SmartHRBI/docs/adr/0001-agentic-query-runtime.md).
