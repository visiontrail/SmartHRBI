## Context

当前 `apps/api/auth.py` 仅实现了一个内存中的 demo 身份系统：单一 service token 通过 `/auth/login` 颁发 JWT，`AuthIdentity` 用预置常量构造，所有"用户"共用同一份 RBAC scope。`apps/api/workspaces.py` 的工作空间 RBAC 也基于这个内存身份；`/portal/*` 系列路由虽然声明可"按 user_id 过滤"，但前端从未携带真实 user_id。前端 `apps/web` 的 NextAuth 配置只是占位，登录界面缺失，UI 默认假设当前会话已登录。

这种状态阻碍了三类需求：
1. 团队中的非设计者（HR / PM / Team Leader 等）无法以真实身份访问 BI 看板；
2. 设计者无法将敏感看板限定给特定查看者；
3. 多个设计者无法在同一工作空间协作（当前没有协作者概念）。

**约束：**
- 项目仍处于 0→1 阶段，可以引入持久化用户表与新建 SQLite 文件，无须考虑历史用户数据迁移。
- 必须保留现有 `Authorization: Bearer <token>` 协议；不引入第三方 IdP（OAuth/SSO）。
- 后端是 FastAPI + SQLite + DuckDB；前端是 Next.js App Router + Zustand + TanStack Query。
- 现有发布快照管线与脱敏管线已稳定，不希望破坏其结构；可见性应作为 **manifest 读取层**的过滤，而不是修改快照写入。

**利益相关者：** BI 设计者（PM / 数据团队）、查看者（HR / Team Leader / 业务岗）、平台管理员。

## Goals / Non-Goals

**Goals:**
- 提供完整的注册/登录/登出 UI 与后端，支持邮箱+密码 + 岗位选择。
- 在前端 AppShell 暴露 designer / viewer 双模式切换；后端按模式 + 协作关系做权限决策。
- Canvas Publish 弹窗支持"对哪位用户可见"的搜索与多选；Portal 列表与详情按可见性过滤。
- Canvas Share 弹窗支持邀请协作者、移除协作者、复制邀请链接；邀请链接对未注册用户引导注册并自动加入。
- 邀请链接必须签名且支持过期与撤销，避免泄露后无限期可用。
- 现有未授权访问 `/portal` 行为切换为登录态访问，但保留 viewer 浏览发布页能力。

**Non-Goals:**
- 不实现 OAuth / SSO / 双因素认证 / 邮箱验证邮件发送（注册即激活，邮箱验证留作后续）。
- 不实现密码找回与重置邮件流程（先用管理员后台手动重置）。
- 不实现工作空间级别的"评论 / 历史协作活动"feed。
- 不修改已发布快照的脱敏与数据上限策略。
- 不为 viewer 模式提供新的 BI 设计能力；viewer 只能浏览被授权的 portal 页面与嵌入聊天。

## Decisions

### Decision 1：用户表与岗位独立成表，岗位为受控枚举但可扩展

新增 SQLite 表 `users(id, email_lower, password_hash, display_name, job_id, created_at, last_login_at)` 与 `user_jobs(id, code, label_zh, label_en, sort_order)`。岗位先种入：开发者 / 项目经理 / Team Leader / 产品经理 / 人力资源 / 数据分析师 / 其他，可由管理员追加。

**Why this over alternatives：**
- 用枚举常量硬编码岗位 → 拒绝：用户提到岗位"等等"，未来需追加；硬编码会污染代码与 i18n。
- 用单字段 free-text → 拒绝：会出现"PM" / "项目经理" / "Project Manager" 等同义噪声，搜索与统计失效。
- 取舍：表驱动 + i18n 标签 + sort_order，前端从 `GET /jobs` 拉取列表渲染下拉。

### Decision 2：应用模式 designer / viewer 是 UI 层切换，不是数据库角色

`users` 表本身**不存** designer/viewer 字段；任意用户既可以以 designer 进入自己拥有/被邀请协作的工作空间，也可以以 viewer 进入 portal 浏览。模式切换仅影响：
- AppShell 顶栏 UI（显示 Canvas / 工作空间面板 vs 仅 Portal）；
- `Authorization` header 之外附带的 `X-App-Mode: designer|viewer`，后端用以快速拒绝越权（例如 viewer 模式下打到 `POST /workspaces/.../publish` 直接 403）。

**Why this over alternatives：**
- "在用户表里加 role 字段" → 拒绝：现实中 PM 可能既是设计者又是查看者，角色不应是用户的固有属性。
- "完全前端模式" → 拒绝：仅靠前端隐藏菜单不安全，必须有后端二次校验。
- 取舍：模式只是一个**视图意图**，后端真正的权限来源是 `workspace_members` 关系与 published page 可见性。

### Decision 3：工作空间协作者关系建模

新增 `workspace_members(workspace_id, user_id, role, added_by, added_at)`，`role ∈ {owner, editor, viewer}`：
- `owner`：唯一，创建者；可邀请、移除任何人；可删除工作空间。
- `editor`：可编辑画布、发布；可邀请新协作者但不可移除 owner。
- `viewer`：可浏览工作空间但不能编辑（用于"协作者"中的只读成员；与 portal viewer 不同）。

工作空间默认私有，只有 owner 与受邀 editor/viewer 可访问。`apps/api/workspaces.py` 现有内存 RBAC 改为基于此表查询。

### Decision 4：发布可见性策略三态

`published_versions` 表新增列：
- `visibility_mode TEXT NOT NULL CHECK(visibility_mode IN ('private','registered','allowlist'))`
- `visibility_user_ids JSON`（仅当 `allowlist` 时使用，存数组）

行为：
- `private`：只有发布者本人 + 工作空间 owner/editor 可见。
- `registered`：所有已注册登录用户可见。
- `allowlist`：发布者本人 + 工作空间 owner/editor + `visibility_user_ids` 中的用户可见。

设计者本人始终可见自己发布的所有页面是通过"发布者本人 + 工作空间 owner/editor"分支保证的，不依赖 allowlist 是否包含自己。

**Why this over alternatives：**
- 直接用"邀请用户列表"覆盖三态 → 拒绝："public to all registered" 与"private"是常见快捷选项，强制让用户每次都搜索一遍体验差。
- 把可见性写进快照 manifest → 拒绝：可见性是动态的（设计者发布后可能后悔，希望调整），写进只读快照导致需要重新发布；改为发布版本的元数据可单独编辑。

### Decision 5：邀请链接 = 签名 token + 服务端记录

`workspace_invites(id, workspace_id, token_hash, role, created_by, expires_at, revoked_at, used_count, max_uses)`。生成时：
- 用 `itsdangerous.URLSafeTimedSerializer` 对 `{invite_id, workspace_id, role}` 签名，secret 来自 `JWT_SECRET`。
- 数据库只存 token 的 sha256，链接本身只在生成时返回一次。
- 默认 `max_uses=NULL`（无限）`expires_at = now + INVITE_LINK_TTL_DAYS`。

消费时：
- `POST /invites/{token}/accept`：已登录用户直接加入工作空间（成为 editor）；未登录用户被前端引导到 `/register?invite=<token>`，注册成功后自动调用同一 endpoint。
- 服务端校验签名 + 未过期 + 未撤销 + 未超用次数，再写 `workspace_members`。

**Why this over alternatives：**
- 纯随机 UUID token，不签名 → 拒绝：每次都要查库才能判断有效性，且无法在签名层防伪。
- 签名 token 不入库 → 拒绝：无法撤销、无法限制使用次数。
- 取舍：签名 + 入库 hash 的组合让链接本身不命中数据库即可识别篡改，撤销与限流走数据库。

### Decision 6：用户搜索接口的最小暴露

新增 `GET /users/search?q=<email_or_name>&limit=20`，仅返回 `{id, email_masked, display_name, job_label}`，邮箱中段打码（`a***@example.com`）防止用户枚举。

**Why this over alternatives：**
- 直接返回完整邮箱 → 拒绝：会被滥用为邮箱采集接口。
- 不提供搜索接口，让设计者输入完整邮箱 → 拒绝：用户提到"通过邮箱等搜索注册用户"，体验诉求明确。
- 取舍：搜索接口要登录 + 限速；返回的 user_id 才是后端权限决策依据。

### Decision 7：前端会话管理依赖后端 cookie + Bearer 双轨

注册/登录后后端同时写 HttpOnly cookie `cognitrix_session`（用于浏览器导航 SSR）和返回 `access_token`（前端缓存到内存供 fetch 使用）。AppShell mount 时通过 `GET /auth/me` 拉取当前用户 + 可用工作空间。

**Why this over alternatives：**
- 单纯 localStorage Bearer → 拒绝：不能在 Next.js Server Component 里识别身份，portal SSR 体验差。
- 单纯 cookie → 拒绝：现有 API 已统一 Bearer，迁移成本高。
- 取舍：cookie 用于 SSR + 路由保护，Bearer 用于现有 fetch 路径，登录接口同时签发。

## Risks / Trade-offs

- **风险：邀请链接泄露被陌生人接受** → Mitigation：默认 14 天过期；owner 可在 Share 弹窗一键撤销；可设置 `max_uses` 限制（默认无限但建议团队邀请设为 1 次）；接受时记录日志到 `audit.py`。
- **风险：用户枚举攻击通过 `/users/search`** → Mitigation：要求登录态 + 简单速率限制（每用户每分钟 60 次）；返回邮箱打码；查询长度下限 2 字符。
- **风险：viewer 模式被绕过直接调用 `POST /workspaces/.../publish`** → Mitigation：发布权限不依赖 `X-App-Mode`，依赖 `workspace_members.role IN (owner, editor)`；`X-App-Mode` 只是 UX 信号，不是安全边界。
- **风险：发布可见性元数据与快照不一致** → Mitigation：可见性存于 `published_versions` 元数据表而非快照内；查询路径在 `GET /portal/pages/{page_id}` 入口处先查 `published_versions` 再决定是否返回 manifest。
- **风险：现有 demo `/auth/login`（service token → JWT）被破坏** → Mitigation：保留旧 endpoint 作为 `feature_flag = LEGACY_SERVICE_LOGIN_ENABLED` 的开发辅助路径，默认关闭；测试与 smoke 脚本切换为真实账号。
- **取舍：未实现邮箱验证** → Mitigation：注册即可用，但所有 audit log 标记 `email_verified=false`，后续上线邮箱验证时可强制升级。
- **取舍：viewer 模式下不能编辑共享工作空间** → 用户提到"viewer 只能浏览发布页"，本设计严格按此约束；如果用户想要 viewer 能编辑，需要进入 designer 模式并消费协作邀请。

## Migration Plan

1. **后端先上：** 部署新 `users`、`user_jobs`、`workspace_members`、`workspace_invites` 表与路由；保留旧 `/auth/login` service-token 路径用于 smoke 测试（开关默认开）。
2. **种子数据：** 启动时若 `users` 为空且 `AUTH_BOOTSTRAP_ADMIN_EMAIL/PASSWORD` 存在，自动创建管理员账号；岗位表预置中文标签。
3. **前端切换：** 注册/登录页上线，AppShell 增加身份切换器；老 demo token 通过 `?legacy_token=...` 兼容（仅 dev 环境）。
4. **数据回填：** 现有 in-memory 工作空间在第一次 owner 登录后自动写入 `workspace_members` 作为 owner（迁移脚本 `scripts/migrate_workspaces_to_members.py`）。
5. **关闭 legacy：** 一周内将 `LEGACY_SERVICE_LOGIN_ENABLED=false`，删除 `?legacy_token` 兼容代码。

**Rollback：** 关闭新路由的 feature flag（`USER_ACCOUNTS_ENABLED=false`），AppShell 回退到 demo 登录；新表保留不删，避免数据丢失。

## Open Questions

- 邀请链接的二维码版本是否需要？（当前先做"复制链接"，二维码后置）
- 工作空间协作的"editor"是否允许重新发布并替换 `published_by`？建议是：发布历史里每个版本都记录实际发布者，editor 可发布但版本归属于 editor 自己，不会顶替 owner。需要在 `tasks.md` 实施前与产品确认。
- 岗位表是否需要按部门 / 职级二级分类？当前 MVP 只做扁平列表，留 `parent_id` 字段为后续扩展占位但不暴露。
