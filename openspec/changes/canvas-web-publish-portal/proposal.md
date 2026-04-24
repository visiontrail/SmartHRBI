## Why

The current workspace canvas is limited to free-layout and fixed-dimension drawing surfaces — it cannot produce a structured, shareable presentation page. Users need to design polished, publishable BI dashboards that non-technical stakeholders can browse and query without accessing the authoring interface.

## What Changes

- Add a **Web Page Design** canvas mode to the workspace panel alongside the existing free-canvas and fixed-size-canvas modes.
- Inside that mode, allow users to configure a **multi-level sidebar** and place charts into **constrained layout zones** (resizable within limits to preserve visual integrity).
- Add a **Publish** action that snapshots the workspace — including chart specs and raw source data — into a persistent, shareable published page.
- Introduce a **Published Portal** as a unified entry page: left sidebar lists all published workspaces, right area renders the selected published page with an embedded AI conversation window.
- The embedded **Chart Query Agent** on the published page can answer questions about the page's data; users can select a specific chart to anchor the conversation context.

## Capabilities

### New Capabilities

- `canvas-web-design-mode`: Web-page canvas mode with multi-level sidebar editor and constrained chart zones; extends the existing workspace panel canvas mode selector.
- `workspace-publish`: Publish action that snapshots workspace layout, chart specs, and raw chart data into an immutable published page record.
- `published-portal`: Unified portal page listing published workspaces on the left and rendering the selected page on the right; serves as the eventual login-aware entry point.
- `chart-query-agent`: New AI agent embedded in the published portal that queries original source data, supports chart-scoped context selection, and streams answers inline.

### Modified Capabilities

<!-- None — no existing spec-level requirements are changing. -->

## Impact

- **Frontend**: New canvas mode component, sidebar editor UI, publish button + flow, new portal route (`/portal`), chart zone components with resize constraints, AI chat overlay on portal.
- **Backend**: New `published_pages` table/model, `POST /workspaces/{id}/publish` endpoint, published page data API, `ChartQueryAgent` runtime (new `AgentRuntime` variant with read-only DuckDB access scoped to snapshot data).
- **Data storage**: Published page snapshots stored under `UPLOAD_DIR/published/` containing layout JSON and chart data blobs.
- **Agent SDK**: A second in-process MCP server for the Chart Query Agent, isolated from the query runtime, with read access to snapshot data only.
- **Auth**: Portal entry point will need to be login-aware in a future phase; design must accommodate per-user workspace visibility hooks.
