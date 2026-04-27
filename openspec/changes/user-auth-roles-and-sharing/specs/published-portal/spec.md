## ADDED Requirements

### Requirement: Portal 路由要求登录态
`/portal` 路由 SHALL 要求用户已登录。未登录访问 `/portal` 或其子路径 MUST 重定向到 `/login?next=<原始路径>`。登录后系统 MUST 跳回原始 portal 路径（含 page_id 等参数）。

#### Scenario: 未登录访问 portal
- **WHEN** 未登录用户访问 `/portal/pages/abc`
- **THEN** 浏览器重定向到 `/login?next=%2Fportal%2Fpages%2Fabc`

#### Scenario: 登录后跳回
- **WHEN** 用户在 `/login?next=...` 完成登录
- **THEN** 自动跳转回 `next` 参数指定的路径

### Requirement: Portal 列表按当前用户可见性过滤
`GET /portal/workspaces` MUST 始终基于当前登录用户身份过滤可见的发布页：
- 包含该用户作为 owner 或 editor 的所有工作空间最新发布；
- 包含 `visibility_mode = registered` 的所有工作空间最新发布；
- 包含 `visibility_mode = allowlist` 且 `current_user.id ∈ visibility_user_ids` 的发布；
- 排除 `visibility_mode = private` 且当前用户不是 owner/editor 的发布。

设计者本人始终可见自己发布的页面（无论 visibility_mode），通过 owner/editor 分支保证。

#### Scenario: viewer 用户看到允许列表内的页
- **WHEN** 用户 A 不是工作空间 W 的成员，但被加入 W 最新发布的 allowlist
- **THEN** A 调用 `GET /portal/workspaces` 时返回结果包含 W

#### Scenario: 私密发布不外泄
- **WHEN** 用户 A 不是工作空间 W 的成员，且 W 最新发布是 private
- **THEN** A 的 `GET /portal/workspaces` 结果不包含 W

#### Scenario: 设计者总能看到自己的发布
- **WHEN** owner 把自己工作空间发布为 private 后访问 portal
- **THEN** 列表仍包含该工作空间

### Requirement: Portal 详情接口校验可见性
`GET /portal/pages/{page_id}/manifest` 与 `GET /portal/pages/{page_id}/charts/{chart_id}/data` MUST 在返回快照前校验当前用户对该 published version 的可见性。不可见时 MUST 返回 HTTP 403 `{"error": "page_not_visible"}`，不返回 404 以避免与"snapshot 不存在"语义混淆。

#### Scenario: 可见用户拉取 manifest
- **WHEN** 已授权用户 A 调用 `GET /portal/pages/{page_id}/manifest`
- **THEN** 后端返回 manifest JSON（依然来自快照文件）

#### Scenario: 不可见用户被拒
- **WHEN** 不在 allowlist 内的用户 A 直接访问 `GET /portal/pages/{page_id}/manifest`
- **THEN** 后端返回 HTTP 403 `{"error": "page_not_visible"}`

#### Scenario: 不存在的 page_id 仍返回 404
- **WHEN** `page_id` 在 `published_versions` 表中不存在
- **THEN** 后端返回 HTTP 404（与可见性 403 区分）

## MODIFIED Requirements

### Requirement: Portal entry page at /portal
A new route `app/portal/page.tsx` SHALL serve the published workspace browser. The left panel lists all published workspaces visible to the current user; the right panel renders the selected published page. The route MUST require authentication: unauthenticated visitors are redirected to `/login?next=<path>`. The layout MUST integrate with the application-level `viewer` mode (when the user is in viewer mode the portal becomes the only top-level surface).

#### Scenario: Portal page loads for authenticated user
- **WHEN** the authenticated user navigates to `/portal`
- **THEN** the page renders with a left sidebar listing workspaces visible to that user, and an empty right panel with a prompt to select a workspace

#### Scenario: Unauthenticated visit redirects
- **WHEN** an unauthenticated visitor opens `/portal`
- **THEN** the browser is redirected to `/login?next=%2Fportal`

#### Scenario: No visible published workspaces
- **WHEN** the user has no workspaces visible under the visibility rules
- **THEN** the left sidebar displays an empty-state message: "暂无可见的发布页。请联系设计者获取访问权限。"

### Requirement: Portal designed for future per-user workspace visibility
The portal's workspace list endpoint (`GET /portal/workspaces`) SHALL always derive the active user from the bearer token / session cookie. The legacy `user_id` query parameter is removed; passing it MUST be ignored. The endpoint MUST return only workspaces visible to that user as defined in the "Portal 列表按当前用户可见性过滤" requirement.

#### Scenario: Authenticated request returns filtered list
- **WHEN** an authenticated user calls `GET /portal/workspaces`
- **THEN** only workspaces matching that user's visibility rules are returned

#### Scenario: Legacy user_id parameter ignored
- **WHEN** the request URL contains `?user_id=<other>`
- **THEN** the parameter is ignored; the response still reflects the authenticated user's identity

#### Scenario: Unauthenticated request rejected
- **WHEN** `GET /portal/workspaces` is called without a valid session
- **THEN** the API returns HTTP 401 `{"error": "authentication_required"}`
