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

`dev-local` is intended for debug only. It requires local PostgreSQL to be already running and reachable from `DATABASE_URL`.

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
