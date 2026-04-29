## ADDED Requirements

### Requirement: 顶栏暴露设计者/查看者模式切换
登录后，AppShell 顶栏 SHALL 渲染一个模式切换器（Segmented Control），包含"设计者"和"查看者"两个选项。当前选中模式 SHALL 通过 `localStorage.cognitrix_app_mode` 持久化，并在每次 fetch 调用上自动附加 `X-App-Mode: designer|viewer` 请求头。模式切换 MUST 立即生效，不需要刷新页面。

#### Scenario: 默认模式选择
- **WHEN** 已登录用户首次进入 `/`
- **THEN** 若用户作为 owner/editor 至少属于一个工作空间，默认 mode = `designer`；否则默认 mode = `viewer`

#### Scenario: 模式持久化
- **WHEN** 用户在顶栏切换到"查看者"模式后刷新页面
- **THEN** 页面恢复时仍然是查看者模式

#### Scenario: 请求头注入
- **WHEN** 前端发起任何对后端 `/api/*` 的请求
- **THEN** 请求头自动附加当前 `X-App-Mode`

### Requirement: 设计者模式 UI 范围
当 mode = `designer` 时，AppShell SHALL 显示完整的面板切换器（chat / workspace / both / catalog），允许用户进入 Canvas 编辑、聊天、目录等所有现有面板，并显示 Publish / Share 按钮。

#### Scenario: 设计者进入 Canvas
- **WHEN** 用户在设计者模式下点击 ⌘/Ctrl+2
- **THEN** 进入 workspace 面板，可编辑画布

### Requirement: 查看者模式 UI 范围
当 mode = `viewer` 时，AppShell SHALL 隐藏 workspace 面板与 catalog 面板，只暴露 portal 浏览界面与嵌入式聊天。所有编辑入口（Publish、Share、画布工具栏）MUST 不渲染。地址栏直接访问 `/workspace` 类路由 MUST 重定向到 `/portal`。

#### Scenario: 查看者打开 portal
- **WHEN** 用户在查看者模式下访问 `/`
- **THEN** 直接渲染 `/portal` 内容；顶栏面板切换器隐藏；侧边栏只显示已发布工作空间列表

#### Scenario: 查看者直达 workspace 路径
- **WHEN** 用户在查看者模式下访问 `/workspace/new` 或类似路径
- **THEN** 前端拦截并重定向到 `/portal`

### Requirement: 后端按模式 + 协作关系做权限校验
后端路由 SHALL 在 viewer 模式下拒绝以下行为，返回 HTTP 403：`POST /workspaces/*`、`POST /workspaces/{id}/publish`、`POST /workspaces/{id}/invites`、`PATCH /workspaces/{id}/members/*`。**但** `X-App-Mode` MUST NOT 被视为安全边界 —— 真正的发布与编辑权限始终基于 `workspace_members.role` 与 published page visibility 校验，模式头只用作快速失败信号。

#### Scenario: viewer 模式调用发布接口
- **WHEN** 请求头 `X-App-Mode: viewer` 调用 `POST /workspaces/{id}/publish`
- **THEN** 后端立即返回 HTTP 403 `{"error": "viewer_mode_forbidden"}`，不查数据库

#### Scenario: 模式头被伪造但无权限
- **WHEN** 请求头 `X-App-Mode: designer` 但用户在 `workspace_members` 中不是 owner/editor
- **THEN** 后端仍然返回 HTTP 403 `{"error": "workspace_role_required"}`
