# workspace-publish Specification

## Purpose
TBD - created by archiving change canvas-web-publish-portal. Update Purpose after archive.
## Requirements
### Requirement: Publish action available on Web Page Design canvas
A **Publish** button SHALL be visible in the Web Page Design canvas toolbar to users whose role on the current workspace is `owner` or `editor`. The button is disabled if any chart zone contains a chart with no loaded data. For users whose role is `viewer` (collaborator-viewer) or who are not members of the workspace, the Publish button MUST NOT render. Clicking the button opens the visibility-aware publish dialog defined in this capability rather than triggering an immediate publish.

#### Scenario: Publish button visible to owner/editor
- **WHEN** 工作空间 owner 或 editor 进入 Web Page Design 模式
- **THEN** 工具栏渲染 Publish 按钮

#### Scenario: Publish button hidden for collaborator-viewer
- **WHEN** 工作空间 viewer 进入 Web Page Design 模式
- **THEN** Publish 按钮不渲染

#### Scenario: Publish blocked with empty chart
- **WHEN** the workspace contains a chart zone whose chart has not yet been loaded with data
- **THEN** the Publish button is disabled and a tooltip reads "All charts must have data before publishing"

#### Scenario: Publish opens dialog instead of direct publish
- **WHEN** owner/editor 点击启用状态的 Publish 按钮
- **THEN** 系统打开"发布设置"对话框（参见 ADDED 中的可见性策略需求），不立即发起发布请求

### Requirement: Publish creates an immutable versioned snapshot
When the user confirms publish in the visibility dialog, the system SHALL call `POST /workspaces/{workspace_id}/publish` with the chosen visibility payload. The backend creates a new version record and writes the snapshot to `UPLOAD_DIR/published/{workspace_id}/{version}/` containing:
- `manifest.json` — sidebar config, grid layout, zone positions
- `charts/{chart_id}/spec.json` — ECharts or Recharts spec
- `charts/{chart_id}/data.json` — raw rows, capped at `AGENT_MAX_SQL_ROWS`

The raw data rows MUST pass through the same `redact_rows()` and `forbidden_sensitive_columns()` pipeline as the query runtime before being written. Visibility metadata (`visibility_mode`, `visibility_user_ids`) MUST be persisted in the `published_versions` table, not in the on-disk snapshot files.

#### Scenario: Successful publish
- **WHEN** owner/editor 在弹窗中确认发布且所有 zone 都已加载数据
- **THEN** 前端调用 `POST /workspaces/{workspace_id}/publish` 携带 visibility 字段；后端返回 `published_page_id` 与版本号；前端展示成功 toast 与"查看发布页"链接

#### Scenario: Sensitive column redaction
- **WHEN** a chart's underlying data contains columns flagged by `forbidden_sensitive_columns()` for the publishing user's role
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

### Requirement: Publish 弹窗暴露可见性策略
点击 Publish 按钮时 SHALL 弹出"发布设置"对话框（替代直接发布）。对话框 MUST 包含：
1. 三选一可见性单选：`仅自己与协作者可见（私密）` / `所有已注册用户可见` / `指定用户可见`
2. 当选择"指定用户可见"时，渲染用户搜索框（调用 `GET /users/search`）与已选用户的 chip 列表，可移除单个用户。
3. 底部"取消"与"确认发布"按钮。

#### Scenario: 默认私密发布
- **WHEN** 设计者点击 Publish
- **THEN** 弹窗打开；可见性默认选中"仅自己与协作者可见"

#### Scenario: 选择已注册用户可见
- **WHEN** 设计者切换到"所有已注册用户可见"并点击"确认发布"
- **THEN** 前端调用 `POST /workspaces/{id}/publish` 携带 `{visibility_mode: "registered"}`；快照创建并记录 visibility_mode

#### Scenario: 指定用户列表
- **WHEN** 设计者切换到"指定用户可见"，搜索并加入"李雷"和"王梅"两位用户后点击"确认发布"
- **THEN** 请求体携带 `{visibility_mode: "allowlist", visibility_user_ids: [<李雷id>, <王梅id>]}`；后端将 `visibility_user_ids` 写入 `published_versions` 的 JSON 列

#### Scenario: 指定用户但未选任何用户
- **WHEN** 选择"指定用户可见"但 chip 列表为空
- **THEN** "确认发布"按钮禁用；提示"请至少选择一位用户"

### Requirement: Publish 接口接受可见性参数
`POST /workspaces/{workspace_id}/publish` 请求体 SHALL 接受 `{visibility_mode: "private"|"registered"|"allowlist", visibility_user_ids?: number[]}`。后端 MUST 校验：`visibility_mode = allowlist` 时 `visibility_user_ids` 长度 ≥ 1，且每个 id 都存在于 `users` 表中；其他模式下 `visibility_user_ids` MUST 为空或不传。校验通过后写入 `published_versions` 的 `visibility_mode` 与 `visibility_user_ids` 列；快照文件结构本身不改变。

#### Scenario: 合法 allowlist 发布
- **WHEN** 请求体 `{visibility_mode: "allowlist", visibility_user_ids: [1,2]}` 且两个 id 均合法
- **THEN** 后端创建快照并把可见性写入 `published_versions`

#### Scenario: allowlist 含无效 user_id
- **WHEN** 请求体含一个不存在的 user_id
- **THEN** 后端返回 HTTP 422 `{"error": "invalid_user_ids", "invalid": [<id>]}`，不创建快照

#### Scenario: 模式与列表冲突
- **WHEN** 请求体 `{visibility_mode: "registered", visibility_user_ids: [1]}`
- **THEN** 后端返回 HTTP 422 `{"error": "visibility_user_ids_only_allowed_in_allowlist"}`

### Requirement: 发布历史按版本记录可见性
`GET /workspaces/{workspace_id}/published` 返回的每个版本对象 SHALL 包含 `{version, published_at, published_by, page_id, visibility_mode, visibility_user_count}`。`visibility_user_count` 仅在 allowlist 模式下为数组长度，其它模式为 null。MUST NOT 直接返回 user_id 列表（避免在列表场景泄露被授权用户）。

#### Scenario: 列表展示可见性摘要
- **WHEN** 设计者打开发布历史面板
- **THEN** 每行显示版本号 + 时间 + 可见性摘要文案（"私密" / "所有注册用户" / "5 位指定用户"）

### Requirement: 调整已发布版本的可见性
系统 SHALL 提供 `PATCH /workspaces/{workspace_id}/published/{version}/visibility`，请求体同 publish 接口的 visibility 字段。仅工作空间 owner/editor 与原发布者可调用。修改 MUST 不影响快照文件，只更新 `published_versions` 元数据。

#### Scenario: 设计者撤销公开
- **WHEN** 设计者把某历史版本从"所有已注册用户可见"改为"私密"
- **THEN** `PATCH .../visibility` 写入新值；之后 viewer 列表/详情立即不再返回该页

#### Scenario: 非授权用户调用
- **WHEN** 非 owner/editor/原发布者调用 PATCH
- **THEN** 后端返回 HTTP 403

