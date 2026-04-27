## Why

当前 Cognitrix 平台仅有后端 JWT 单体登录，前端没有真正的用户注册/登录入口，所有人共用一份认证身份；Canvas 发布的页面在 `/portal` 中对任何人可见，无法限定查看人；工作空间也没有协作邀请机制，无法支持多人共同编辑。这导致两个问题：(1) BI 设计者无法将敏感看板只发布给特定查看者；(2) 团队无法在同一工作空间中协作建模与设计。本次变更引入完整的注册/登录、岗位画像、设计者/查看者双角色、发布粒度可见性控制、以及类似 Notion / Lovable 的工作空间协作分享。

## What Changes

- **新增**用户注册与登录界面：邮箱 + 密码注册、登录、登出；注册时除常规字段（邮箱、姓名、密码）外，**必须**选择岗位（开发者、项目经理、Team Leader、产品经理、人力资源等，可扩展）。
- **新增**应用级身份角色：`designer`（BI 设计者）、`viewer`（BI 察看者）。登录后用户可在两个界面之间切换（设计者拥有 Canvas/工作空间的全部能力；查看者只能浏览被授权的发布页 + 聊天）。
- **扩展** Canvas Web Page Design 模式下的 **Publish** 流程：弹出"可见人选择"对话框，支持按邮箱/姓名搜索已注册用户，选择具体可见用户列表（或勾选"所有已注册用户可见"，或保持私有）。发布快照记录可见性策略。
- **扩展** `/portal` 与 `GET /portal/workspaces`：依据当前登录用户身份过滤可见的发布页面；设计者本人始终可见自己发布的所有页面（即使不在被授权名单中）。
- **新增** Canvas 工具栏 **Share** 按钮（位于 Publish 旁）：弹出协作分享对话框，包含①搜索已注册用户邀请为协作者、②管理当前协作者及其角色、③"复制邀请链接"按钮（生成可分享给未注册用户的邀请链接，已注册用户点击直接获得工作空间编辑权限，未注册用户点击进入注册页，注册成功后自动加入工作空间）。
- **BREAKING**：现有 `apps/api/auth.py` 单体内存身份扩展为持久化用户表；现有匿名访问 `/portal` 需要登录后访问（保留 viewer 浏览发布页的能力，但不再允许未登录访问）。

## Capabilities

### New Capabilities
- `user-account`：用户注册、登录、登出、密码哈希、岗位选择、Token 颁发与刷新；提供按邮箱/姓名搜索注册用户的接口（用于 Publish 与 Share 的搜索框）。
- `app-role-mode`：应用层 designer / viewer 双模式切换；登录后默认进入设计者模式（如果用户拥有任何作为设计者的工作空间）；UI 顶栏暴露切换器；后端 RBAC 校验当前模式。
- `workspace-collaboration`：工作空间协作者关系（owner / editor / viewer），按邮箱搜索邀请、移除、变更角色；生成与消费一次性或长期邀请链接；未注册用户点击邀请链接走"注册即接受邀请"的流程。

### Modified Capabilities
- `workspace-publish`：发布动作扩展可见性策略字段（`public_to_registered`、`allowlist[user_id]`、`private`），设计者本人始终可见；发布历史记录可见性变更。
- `published-portal`：`/portal` 路由要求登录；`GET /portal/workspaces` 强制按当前用户身份过滤；列表与查看页接受设计者本人 vs 被授权查看者的差异化路由。

## Impact

- **后端**：新增 `apps/api/users.py`（用户与岗位 SQLite 表 + 路由）、`apps/api/collaboration.py`（协作者与邀请链接表 + 路由）、扩展 `apps/api/auth.py`（密码哈希、注册、登录、刷新、当前模式声明）、扩展 `apps/api/workspaces.py`（owner/editor/viewer 校验取代原内存 RBAC）、扩展 `apps/api/main.py` 路由挂载、扩展现有 `POST /workspaces/{workspace_id}/publish` 与 `GET /portal/*` 路由。
- **数据**：新增 SQLite 表 `users`、`user_jobs`（岗位枚举）、`workspace_members`、`workspace_invites`；扩展 `published_versions` 增加 `visibility_mode` 与 `visibility_user_ids` 字段；继续使用现有 `state/ai_views.sqlite3`。
- **前端**：新增 `apps/web/app/(auth)/login`、`(auth)/register` 路由与表单；新增 `lib/auth/session.ts` 客户端会话；扩展 `AppShell` 顶栏增加"设计者/查看者"切换器；扩展 Canvas 工具栏增加 Share 按钮 + Publish 可见性弹窗；新增 `components/sharing/*`（用户搜索器、协作者列表、邀请链接复制）。
- **依赖**：后端新增 `passlib[bcrypt]`（密码哈希）、`itsdangerous`（邀请 token 签名）；前端继续使用现有 NextAuth 占位，但实际改为调用后端 `/auth/*` 接口管理会话 cookie。
- **配置**：`apps/api/.env` 新增 `AUTH_REGISTRATION_ENABLED`（默认 `true`）、`INVITE_LINK_TTL_DAYS`（默认 `14`）、`PASSWORD_MIN_LENGTH`（默认 `8`）。
- **安全**：所有现有 RBAC 检查迁移到基于持久化用户与协作者关系；published 快照仍按发布时的脱敏管线执行，可见性仅在 manifest 拉取层强制；邀请 token 必须签名且支持撤销。
- **i18n**：`lib/i18n/dictionary.ts` 增加注册/登录/分享/可见性相关中文键；现有英文为 fallback。
