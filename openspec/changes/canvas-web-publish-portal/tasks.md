## 1. Backend — Data Models & Storage

- [ ] 1.1 Create `state/published_pages.sqlite3` schema: tables `published_pages (id, workspace_id, version, published_at, published_by, manifest_path)` and init migration in `apps/api/`
- [ ] 1.2 Add `PublishedPage` Pydantic model and `PublishedPageStore` repository class with `create`, `get_latest`, `list_by_workspace` methods
- [ ] 1.3 Implement snapshot file writer: `SnapshotWriter` class that accepts workspace layout JSON + chart specs + raw rows and writes to `UPLOAD_DIR/published/{workspace_id}/{version}/`
- [ ] 1.4 Wire `redact_rows()` and `forbidden_sensitive_columns()` into `SnapshotWriter` before writing `charts/{chart_id}/data.json`
- [ ] 1.5 Add `data_truncated` flag in manifest when chart data rows are capped at `AGENT_MAX_SQL_ROWS`

## 2. Backend — Publish API

- [ ] 2.1 Add `POST /workspaces/{workspace_id}/publish` endpoint in `workspaces.py`: validate all chart zones have data, call `SnapshotWriter`, create `PublishedPage` record, return `{ published_page_id, version }`
- [ ] 2.2 Add `GET /workspaces/{workspace_id}/published` endpoint returning publish history list
- [ ] 2.3 Add `GET /portal/workspaces` endpoint (optional `user_id` filter via workspace RBAC) in new `portal.py` router
- [ ] 2.4 Add `GET /portal/pages/{page_id}/manifest` endpoint reading from snapshot files
- [ ] 2.5 Add `GET /portal/pages/{page_id}/charts/{chart_id}/data` endpoint reading snapshot chart data JSON
- [ ] 2.6 Mount portal router in `main.py`; add route-level unit tests in `tests/api/test_portal.py`

## 3. Backend — Chart Query Agent

- [ ] 3.1 Create `apps/api/chart_query_agent.py`: `SnapshotDuckDBCache` LRU cache (max 10, 30-min TTL) that loads `data.json` files into an in-memory DuckDB per `page_id`
- [ ] 3.2 Implement MCP tools `list_snapshot_tables`, `describe_snapshot_table`, `query_snapshot_table` routed through `SnapshotDuckDBCache`
- [ ] 3.3 Implement `ChartQueryAgent` class wrapping `ClaudeSDKClient` with the snapshot MCP server; apply `SQLReadOnlyValidator` on all SQL tool calls
- [ ] 3.4 Add `POST /portal/pages/{page_id}/chat` endpoint in `portal.py`: resolve snapshot, build system prompt (with optional `chart_id` context), run `ChartQueryAgent`, stream SSE response
- [ ] 3.5 Write unit tests in `tests/unit/test_chart_query_agent.py` covering cache eviction, chart context injection, and SQL read-only guard

## 4. Frontend — Canvas Web Design Mode

- [ ] 4.1 Add "Web Page Design" option to the canvas mode selector component in `apps/web/`; update mode type union and `workspace-store.ts`
- [ ] 4.2 Create `WebDesignCanvas` component: renders a CSS grid with configurable columns (2–6) and rows; grid config stored in workspace store
- [ ] 4.3 Implement `GridZone` component: drag-to-place from unplaced tray, column/row span resize handles clamped to grid bounds, min 1×1 cell
- [ ] 4.4 Build unplaced items tray: lists charts not yet dropped into a zone, supports drag-out to place
- [ ] 4.5 Create `SidebarEditor` panel: add/remove/reorder top-level sections and sub-sections (max 2 levels), link each to a grid row anchor, editable labels
- [ ] 4.6 Add Edit/Preview toggle: Preview hides all editor controls and renders the layout as the published page will appear
- [ ] 4.7 Write Vitest tests in `apps/web/tests/ui/web-design-canvas.test.tsx` covering grid resize constraints, sidebar nesting depth limit, mode switch

## 5. Frontend — Publish Flow

- [ ] 5.1 Add "Publish" button to `WebDesignCanvas` toolbar; disable with tooltip when any zone has no chart data
- [ ] 5.2 Implement publish API call in `lib/workspace/publish.ts`: `POST /workspaces/{id}/publish`, return `{ published_page_id, version }`
- [ ] 5.3 Show success toast on publish with "View Published Page" link pointing to `/portal?page={published_page_id}`
- [ ] 5.4 Add publish history panel (collapsible) in workspace settings: calls `GET /workspaces/{id}/published` and lists versions

## 6. Frontend — Published Portal

- [ ] 6.1 Create `app/portal/page.tsx`: two-panel layout (left sidebar = workspace list, right = page viewer); fetch workspace list from `GET /portal/workspaces`
- [ ] 6.2 Build `PortalWorkspaceSidebar` component: workspace cards with name, publish date; highlight active; empty state message
- [ ] 6.3 Create `app/portal/[pageId]/page.tsx` (or inline in portal page): fetch manifest from `GET /portal/pages/{page_id}/manifest` and render layout
- [ ] 6.4 Implement `PublishedPageGrid` component: CSS grid matching manifest layout, render `PublishedChartZone` and `PublishedTextZone` per manifest
- [ ] 6.5 Implement `PublishedChartZone`: fetch `GET /portal/pages/{page_id}/charts/{chart_id}/data` lazily; render with ECharts or Recharts per `spec.json` chart type; support chart selection (click → sets `active_chart_id` in local state)
- [ ] 6.6 Implement `PublishedPageSidebar` component: renders multi-level nav from manifest; clicking section smooth-scrolls to row anchor
- [ ] 6.7 Write Vitest tests for `PublishedPageGrid` and `PortalWorkspaceSidebar` components

## 7. Frontend — Portal AI Chat Window

- [ ] 7.1 Create `PortalChatWindow` component: collapsible overlay anchored to right edge, max 30% panel width, chat icon toggle button
- [ ] 7.2 Implement SSE client in `lib/portal/chat.ts`: `POST /portal/pages/{page_id}/chat` with optional `chart_id`, consume `planning`/`tool_use`/`tool_result`/`final`/`error` events
- [ ] 7.3 Wire `active_chart_id` from `PublishedChartZone` selection into chat request body; display "Asking about: [chart title]" label in chat window when chart is selected
- [ ] 7.4 Render chart deselection button in chat window header; clear `active_chart_id` on click
- [ ] 7.5 Write Vitest tests for `PortalChatWindow` covering chart context display, collapse/expand, and message rendering

## 8. Integration & Smoke Tests

- [ ] 8.1 Add integration test `tests/integration/test_publish_flow.py`: upload sample data → design web page → publish → verify snapshot files written and redaction applied
- [ ] 8.2 Add integration test `tests/integration/test_chart_query_agent.py`: load snapshot into DuckDB cache → send chat message with chart_id → verify scoped SQL executed
- [ ] 8.3 Add Playwright e2e test in `apps/web/tests/e2e/portal.spec.ts`: navigate to `/portal`, select published workspace, expand chat, ask a question about a chart, verify response appears
- [ ] 8.4 Update `make smoke-local` to include: publish workspace → view portal page → send portal chat message
