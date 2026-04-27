## ADDED Requirements

### Requirement: Canvas 工具栏 Share 按钮
在 Canvas Web Page Design 模式工具栏中，**Publish** 按钮旁 SHALL 渲染 **Share** 按钮。该按钮仅当当前登录用户是当前工作空间的 owner 或 editor 时可见可用；其他角色（viewer、未登录）MUST 不显示。

#### Scenario: Owner 可见 Share
- **WHEN** 工作空间 owner 进入 Canvas Web Page Design 模式
- **THEN** 工具栏显示 Publish 与 Share 两个按钮

#### Scenario: Editor 可见 Share
- **WHEN** 工作空间 editor 进入 Canvas
- **THEN** 工具栏同时显示 Publish 与 Share

#### Scenario: Viewer 角色不可见
- **WHEN** 工作空间 viewer（被邀请的只读协作者）进入 Canvas
- **THEN** Share 按钮隐藏；Publish 按钮也隐藏

### Requirement: Share 弹窗结构
点击 Share 按钮 SHALL 打开一个对话框，必须包含三块内容：
1. **协作者搜索框**：输入邮箱或姓名后展示匹配的已注册用户，每条结果带"邀请为编辑者"按钮（默认角色 editor，可下拉切换为 viewer）。
2. **当前协作者列表**：展示当前 `workspace_members` 中 owner/editor/viewer 的 `display_name + email_masked + role + 加入时间`，每条带"修改角色"与"移除"操作（owner 不可被移除/降级，需先转移所有权——v1 不支持转移则禁用）。
3. **复制邀请链接区**：展示当前激活的邀请链接（如有），带"复制"、"撤销"、"生成新链接"三个动作；可选下拉选择角色（默认 editor）与有效期。

#### Scenario: 弹窗打开
- **WHEN** owner 点击 Share
- **THEN** 弹窗打开，三个区块依次渲染；顶部展示工作空间名称

#### Scenario: 搜索后邀请
- **WHEN** owner 在搜索框输入"@hr"，下拉选中"王梅"，点击"邀请为编辑者"
- **THEN** 前端调用 `POST /workspaces/{id}/members` 写入关系；列表区刷新展示王梅；toast "已邀请王梅为编辑者"

#### Scenario: 修改协作者角色
- **WHEN** owner 在协作者列表对某人点击"改为查看者"
- **THEN** `PATCH /workspaces/{id}/members/{user_id}` 更新 role 为 viewer

#### Scenario: 移除协作者
- **WHEN** owner 点击某协作者的"移除"
- **THEN** 弹出二次确认；确认后 `DELETE /workspaces/{id}/members/{user_id}`；该用户失去访问权

### Requirement: 邀请链接生成与复制
后端 SHALL 提供 `POST /workspaces/{id}/invites`，请求体 `{role, expires_in_days?, max_uses?}`。返回的 `invite_url` 形如 `<APP_URL>/invites/<signed_token>`。系统 SHALL 用 `itsdangerous.URLSafeTimedSerializer` 对 `{invite_id, workspace_id, role}` 签名（secret = `JWT_SECRET`）；数据库 SHALL 仅存 token 的 sha256，原始 token 仅在创建响应中返回一次。默认 `expires_in_days = INVITE_LINK_TTL_DAYS`（14）；`max_uses` 默认 NULL（无上限）。

#### Scenario: 生成邀请链接
- **WHEN** owner 在 Share 弹窗点击"生成新链接"，角色保留默认 editor
- **THEN** 后端写入 `workspace_invites` 行，返回完整 URL；前端展示 URL 与"复制"按钮

#### Scenario: 复制链接
- **WHEN** 用户点击"复制"
- **THEN** URL 写入剪贴板；toast "邀请链接已复制"

#### Scenario: 撤销链接
- **WHEN** 用户点击"撤销"
- **THEN** `DELETE /workspaces/{id}/invites/{invite_id}` 将 `revoked_at` 设为当前时间；该 URL 之后接受时返回 HTTP 410

### Requirement: 邀请链接接受流程
系统 SHALL 提供 `POST /invites/{token}/accept`：
- 已登录用户：直接校验 token（签名、未过期、未撤销、未超用次数），通过则将其加入 `workspace_members`（role 取自 token），返回工作空间信息。
- 未登录用户：前端路由 `/invites/<token>` 检测到无登录态时 SHALL 重定向到 `/register?invite=<token>`；注册成功后前端 MUST 立即调用同一 accept endpoint。

#### Scenario: 已登录用户接受
- **WHEN** 已登录用户访问 `/invites/abc123`
- **THEN** 前端调用 accept API，成功则跳转到对应工作空间画布；toast "已加入工作空间『XXX』"

#### Scenario: 未登录用户接受
- **WHEN** 未登录用户访问 `/invites/abc123`
- **THEN** 重定向到 `/register?invite=abc123`；用户完成注册后自动接受邀请并跳转工作空间

#### Scenario: 已经是协作者
- **WHEN** 用户已是 `workspace_members` 中的成员，再次接受同一链接
- **THEN** 后端返回 200 与 `{"already_member": true}`；前端跳转到工作空间但不显示 toast

#### Scenario: 链接过期
- **WHEN** 接受时 `expires_at < now()`
- **THEN** 后端返回 HTTP 410 `{"error": "invite_expired"}`；前端显示"邀请链接已过期，请联系工作空间所有者"

#### Scenario: 链接已被撤销
- **WHEN** 接受时 `revoked_at IS NOT NULL`
- **THEN** 后端返回 HTTP 410 `{"error": "invite_revoked"}`

#### Scenario: 链接超过使用次数
- **WHEN** 接受时 `max_uses IS NOT NULL AND used_count >= max_uses`
- **THEN** 后端返回 HTTP 410 `{"error": "invite_exhausted"}`

### Requirement: 工作空间成员关系即权威 RBAC
工作空间所有数据访问与编辑权限 SHALL 来源于 `workspace_members(workspace_id, user_id, role)` 表。`apps/api/workspaces.py` 中现有的内存 RBAC 检查 MUST 替换为基于此表的查询；编辑（保存画布、发布）需要 `role IN (owner, editor)`；浏览（含 portal 详情）需要 `role IN (owner, editor, viewer)`，或符合发布页可见性策略。

#### Scenario: 非成员尝试编辑
- **WHEN** 不在 `workspace_members` 中的用户调用 `POST /workspaces/{id}/canvas`
- **THEN** 后端返回 HTTP 403 `{"error": "workspace_role_required"}`

#### Scenario: viewer 协作者尝试发布
- **WHEN** `role = viewer` 的协作者调用 `POST /workspaces/{id}/publish`
- **THEN** 后端返回 HTTP 403

#### Scenario: Owner 删除工作空间
- **WHEN** owner 调用 `DELETE /workspaces/{id}`
- **THEN** 后端级联删除 `workspace_members`、`workspace_invites`、相关 published 历史的可见性元数据
