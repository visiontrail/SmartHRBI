# ADR-0003 Workspace-Scoped Agentic Ingestion Bootstrap

## Context

SmartHRBI already has a stable Agentic Query runtime, but write ingestion still
runs through legacy `POST /datasets/upload` with direct parse-and-load behavior.
The new spec requires a workspace-scoped ingestion lifecycle with explicit
planning, approval, and execution boundaries.

Before implementing full milestones (M1+), we need a bootstrap stage (M0) that
introduces:

1. A dedicated backend module skeleton for write ingestion.
2. Initial database schema/migration artifacts for upcoming workspace and
   ingestion lifecycle entities.
3. Feature flags to control rollout and coexistence with the legacy upload path.

## Decision

1. Create a new backend package `apps/api/agentic_ingestion` to isolate
   write-ingestion runtime, models, and routing from existing query runtime code.
2. Add a new migration file
   `apps/api/migrations/0003_workspace_agentic_ingestion_init.sql` that defines
   initial workspace/catalog/ingestion tables.
3. Introduce two backend feature flags:
   - `AGENTIC_INGESTION_ENABLED`
   - `LEGACY_DATASET_UPLOAD_ENABLED`
4. Wire flags into API behavior:
   - `/ingestion/healthz` is available only when
     `AGENTIC_INGESTION_ENABLED=true`.
   - `/datasets/upload` is disabled when
     `LEGACY_DATASET_UPLOAD_ENABLED=false`.

## Consequences

1. M0 delivers a non-breaking scaffold: legacy upload stays enabled by default.
2. The project gains deterministic rollout control for migration/grey release.
3. M1+ milestones can iterate on workspace/catalog/agent runtime in isolated
   modules without refactoring the entire API surface at once.
