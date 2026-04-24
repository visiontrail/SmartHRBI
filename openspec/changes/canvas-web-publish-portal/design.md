## Context

The current workspace panel renders a React Flow canvas in two modes: free-layout (drag anything anywhere) and fixed-size (constrained artboard). Chart nodes are positioned freely. There is no concept of a "publishable" output, no consumer-facing portal, and no per-page AI agent. The only AI interaction is the sidebar chat that targets the live DuckDB session.

This change introduces a third canvas mode — **Web Page Design** — plus a publish snapshot pipeline and a new portal route served by a dedicated Chart Query Agent.

## Goals / Non-Goals

**Goals:**
- Third canvas mode that renders a structured, presentation-grade layout with a multi-level sidebar and constrained chart zones.
- Publish action that captures an immutable snapshot (layout + chart specs + raw data) and persists it to the backend.
- `/portal` route as a unified published-workspace browser with embedded AI chat.
- Chart Query Agent isolated from the live query runtime, operating only on snapshot data.
- Design entry points so that future per-user login filtering requires only minor additions (workspace visibility predicate).

**Non-Goals:**
- Real-time collaborative editing of published pages.
- Live data refresh on the published page (snapshots are point-in-time).
- Login / authentication system (future phase).
- Embedding the published page in a third-party iframe or external URL routing.
- Chart zone animations or advanced CSS transitions.

## Decisions

### 1. Web Page Design canvas implemented as a structured section grid, not a free-drag surface

**Decision:** Web Design mode uses a multi-column/multi-row section grid where each "zone" is a grid cell. Zones snap to cell boundaries and can only be resized by adjusting their column/row span, not by pixel-dragging.

**Rationale:** Free-drag (React Flow style) produces visually inconsistent output when rendered in a browser without the editor. A grid guarantees the published page looks exactly like the preview. Users get meaningful resize handles (span +/- columns or rows) rather than arbitrary pixel manipulation.

**Alternatives considered:** Absolute-positioned drag-and-drop with bounding-box constraint — rejected because exported HTML still requires absolute positioning and breaks on different viewport sizes.

### 2. Published page snapshot stored as JSON files, not SQLite BLOBs

**Decision:** Each publish action writes `UPLOAD_DIR/published/<workspace_id>/<version>/` containing `manifest.json` (layout + sidebar config), `charts/<chart_id>/spec.json` (ECharts/Recharts spec), and `charts/<chart_id>/data.json` (raw rows used to render the chart). A SQLite record in `state/published_pages.sqlite3` holds metadata and the path.

**Rationale:** Chart data can be tens of thousands of rows. SQLite BLOBs do not compress and make row-level queries slow. File-based storage allows future CDN offload or pre-signed URL serving without schema changes.

**Alternatives considered:** PostgreSQL JSONB — not in the current stack (SQLite + DuckDB only). Single large SQLite BLOB — rejected due to size concerns and inability to serve individual chart data files efficiently.

### 3. Chart Query Agent as a second AgentRuntime variant with snapshot DuckDB

**Decision:** On publish, the backend loads the raw chart data rows into a new ephemeral in-memory DuckDB database keyed by the published page ID. The `ChartQueryAgent` runtime wraps a `ClaudeSDKClient` the same way as `AgentRuntime`, but its MCP tool set is restricted to: `list_snapshot_tables`, `describe_snapshot_table`, `query_snapshot_table`. No write tools, no live dataset access.

**Rationale:** Reusing `AgentRuntime` with different tools is simpler than building a separate agent stack. The snapshot DuckDB instance is constructed lazily (first chat request) and cached for a configurable TTL. This avoids loading all snapshots into memory at startup.

**Alternatives considered:** Pass chart data to Claude directly via context window — rejected because large datasets exceed context limits and cannot support ad-hoc SQL. Pointing the agent at the live DuckDB — rejected because it breaks snapshot immutability and exposes unrelated tables.

### 4. Portal route as a standalone Next.js App Router page, auth-neutral for now

**Decision:** `app/portal/page.tsx` lists all published workspaces from `GET /portal/workspaces`. `app/portal/[pageId]/page.tsx` renders the selected page with the chart layout and AI chat overlay. No auth guard on these routes in this phase; a session check middleware can be added later.

**Rationale:** Shipping the portal without auth unblocks UX validation. The route structure (top-level `/portal`) keeps it separate from the authoring routes (`/workspace`, `/chat`) and makes the future login gate a single middleware insertion.

### 5. Chart context selection sends `chart_id` to the Chat Query Agent

**Decision:** When the user clicks a chart on the published portal page, the chat panel sets `active_chart_id`. Every chat message sent while a chart is selected includes `{ chart_id, table_name }` in the request body. The backend resolves this to snapshot table name and adds a system prompt prefix scoping the agent to that table.

**Rationale:** This is simpler than embedding chart data in the message (which could be large) and lets the agent run fresh SQL against the snapshot rather than re-interpreting static rows.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Snapshot DuckDB instances accumulate in memory if many pages are published | LRU cache with configurable max entries (default 10); evict on TTL or capacity breach |
| Grid-based canvas is less flexible than free-layout; power users may push back | Keep the existing free-layout mode; Web Design mode is opt-in per workspace |
| Raw chart data in snapshots may contain PII / sensitive columns | Apply the same `redact_rows()` and `forbidden_sensitive_columns()` pipeline used in the query runtime before writing snapshot data |
| Published page versioning strategy not defined | First publish creates v1; subsequent publishes create new versions; portal always shows the latest; version history UI is a future enhancement |
| Portal performance with many large chart data files | Lazy-load chart data JSON per chart on first render; charts render with cached spec first, fetch data asynchronously |

## Migration Plan

1. Deploy backend changes first (new routes, published pages store, ChartQueryAgent runtime). All new endpoints; no existing routes change.
2. Deploy frontend changes (new canvas mode, publish button, portal route). Guarded behind the canvas mode selector — existing workspaces are unaffected.
3. No data migrations needed (new storage only).
4. Rollback: remove the new routes from the FastAPI router and the portal page from Next.js routing. No destructive schema changes.

## Open Questions

- Should the multi-level sidebar in the published page support page-to-page navigation within a workspace, or only section anchoring within a single page? (Assumed: anchor-based navigation within one page for this phase.)
- Max chart data rows to include in a snapshot (to bound storage and context size)? (Proposed: respect existing `AGENT_MAX_SQL_ROWS` setting.)
- Should published pages be accessible without login even after the auth system is added? (Deferred to auth phase.)
