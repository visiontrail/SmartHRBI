## ADDED Requirements

### Requirement: Portal entry page at /portal
A new route `app/portal/page.tsx` SHALL serve the published workspace browser. The left panel lists all published workspaces; the right panel renders the selected published page. The route MUST be accessible without authentication in the current phase; the layout MUST support a future per-user filter without structural changes.

#### Scenario: Portal page loads
- **WHEN** the user navigates to `/portal`
- **THEN** the page renders with a left sidebar listing all published workspaces and an empty right panel with a prompt to select a workspace

#### Scenario: No published workspaces
- **WHEN** no workspaces have been published yet
- **THEN** the left sidebar displays an empty-state message: "No published workspaces yet. Publish a workspace from the designer."

### Requirement: Left sidebar lists published workspaces
The portal sidebar SHALL display each published workspace as a card or list item showing workspace name, latest publish date, and a thumbnail (if available). Clicking a workspace loads its latest published page in the right panel.

#### Scenario: Workspace selected
- **WHEN** the user clicks a workspace in the sidebar
- **THEN** the right panel fetches and renders the latest published page for that workspace, including the page's own multi-level sidebar and chart grid

#### Scenario: Active workspace highlighted
- **WHEN** a workspace is selected
- **THEN** its sidebar entry is visually highlighted

### Requirement: Published page renders with page-level sidebar and chart grid
When a published page is loaded in the right panel, the system SHALL render:
- The page's multi-level sidebar (defined at design time) on the left of the right panel
- The chart grid filling the remaining area, with charts loaded from snapshot data
- Clicking a sidebar section smoothly scrolls to the linked grid row

#### Scenario: Page sidebar navigation
- **WHEN** the user clicks a section in the page's sidebar
- **THEN** the grid scrolls smoothly to the row anchored to that section

#### Scenario: Charts load from snapshot
- **WHEN** the published page is rendered
- **THEN** each chart zone fetches its spec and data from `GET /portal/pages/{page_id}/charts/{chart_id}/data` and renders using ECharts or Recharts consistent with the chart type

#### Scenario: Text zones render formatted text
- **WHEN** a zone contains a text block
- **THEN** the text is rendered as formatted markdown (bold, italic, headings supported)

### Requirement: AI chat window embedded in portal page view
The published page view in the right panel SHALL include an embedded AI chat window. The chat window MAY be collapsed or expanded. When expanded it appears as a panel overlay anchored to the right edge of the page, taking up at most 30% of the right panel width.

#### Scenario: Chat window collapsed by default
- **WHEN** a published page is first loaded
- **THEN** the AI chat window is collapsed, showing only a chat icon button

#### Scenario: Expand chat window
- **WHEN** the user clicks the chat icon
- **THEN** the chat window expands to its configured width with an input field and message history

#### Scenario: Chat window persists across sidebar navigation
- **WHEN** the user scrolls through the page using the sidebar
- **THEN** the chat window remains visible at its fixed position and retains the current conversation

### Requirement: Portal designed for future per-user workspace visibility
The portal's workspace list endpoint (`GET /portal/workspaces`) SHALL accept an optional `user_id` query parameter. When provided, the endpoint filters to workspaces the user has access to. When absent, all published workspaces are returned.

#### Scenario: All workspaces returned without user_id
- **WHEN** `GET /portal/workspaces` is called without `user_id`
- **THEN** all published workspaces are returned

#### Scenario: User-filtered workspaces
- **WHEN** `GET /portal/workspaces?user_id={uid}` is called
- **THEN** only workspaces visible to that user are returned (workspace RBAC enforced)
