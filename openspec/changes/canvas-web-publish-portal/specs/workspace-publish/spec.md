## ADDED Requirements

### Requirement: Publish action available on Web Page Design canvas
A **Publish** button SHALL be visible in the Web Page Design canvas toolbar. The button is disabled if any chart zone contains a chart with no loaded data.

#### Scenario: Publish button visible
- **WHEN** the workspace canvas is in Web Page Design mode
- **THEN** a "Publish" button is rendered in the toolbar

#### Scenario: Publish blocked with empty chart
- **WHEN** the workspace contains a chart zone whose chart has not yet been loaded with data
- **THEN** the Publish button is disabled and a tooltip reads "All charts must have data before publishing"

### Requirement: Publish creates an immutable versioned snapshot
When the user triggers Publish, the system SHALL call `POST /workspaces/{workspace_id}/publish`. The backend creates a new version record and writes the snapshot to `UPLOAD_DIR/published/{workspace_id}/{version}/` containing:
- `manifest.json` — sidebar config, grid layout, zone positions
- `charts/{chart_id}/spec.json` — ECharts or Recharts spec
- `charts/{chart_id}/data.json` — raw rows, capped at `AGENT_MAX_SQL_ROWS`

The raw data rows MUST pass through the same `redact_rows()` and `forbidden_sensitive_columns()` pipeline as the query runtime before being written.

#### Scenario: Successful publish
- **WHEN** the user clicks "Publish" and all zones have data
- **THEN** the frontend calls `POST /workspaces/{workspace_id}/publish`, receives a `published_page_id` and version number, and shows a success toast with a "View Published Page" link

#### Scenario: Sensitive column redaction
- **WHEN** a chart's underlying data contains columns flagged by `forbidden_sensitive_columns()` for the current user's role
- **THEN** those columns are excluded from `charts/{chart_id}/data.json`

#### Scenario: Data cap enforcement
- **WHEN** a chart's source query returns more rows than `AGENT_MAX_SQL_ROWS`
- **THEN** only the first `AGENT_MAX_SQL_ROWS` rows are written to `data.json`; the manifest records `data_truncated: true` for that chart

### Requirement: Publish history accessible per workspace
The backend SHALL maintain a publish history. `GET /workspaces/{workspace_id}/published` returns a list of published versions with `{ version, published_at, published_by, page_id }`. The portal always links to the latest version.

#### Scenario: Version list returned
- **WHEN** `GET /workspaces/{workspace_id}/published` is called
- **THEN** the response is an ordered list of published versions, newest first

#### Scenario: Latest version resolved
- **WHEN** the portal loads workspace `{workspace_id}` without specifying a version
- **THEN** the backend returns the manifest and chart data for the highest version number

### Requirement: Publish snapshot accessible without live DuckDB session
Published page assets SHALL be served from `GET /portal/pages/{page_id}/manifest` and `GET /portal/pages/{page_id}/charts/{chart_id}/data`. These endpoints read from the snapshot files, not from any live DuckDB session.

#### Scenario: Snapshot served independently
- **WHEN** the live DuckDB session for the workspace's source dataset is unavailable
- **THEN** the published portal page still loads and renders charts from snapshot data

#### Scenario: Missing snapshot returns 404
- **WHEN** `GET /portal/pages/{page_id}/manifest` is called for a non-existent page_id
- **THEN** the API returns HTTP 404
