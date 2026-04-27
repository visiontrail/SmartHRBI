## 1. 后端基础：数据库与依赖

- [ ] 1.1 在 `apps/api/pyproject.toml` 添加依赖：`passlib[bcrypt]`、`itsdangerous`，运行 `uv sync` 或同等命令
- [ ] 1.2 在 `apps/api/.env.example` 增加 `AUTH_REGISTRATION_ENABLED=true`、`PASSWORD_MIN_LENGTH=8`、`ACCESS_TOKEN_TTL_MIN=120`、`INVITE_LINK_TTL_DAYS=14`、`USER_ACCOUNTS_ENABLED=true`、`LEGACY_SERVICE_LOGIN_ENABLED=true`、`AUTH_BOOTSTRAP_ADMIN_EMAIL`、`AUTH_BOOTSTRAP_ADMIN_PASSWORD`、`APP_URL`
- [ ] 1.3 在 `apps/api/config.py` 的 `Settings` 中加入对应字段并通过 `get_settings()` 暴露
- [ ] 1.4 创建迁移脚本 `apps/api/migrations/0001_users_and_collab.sql` 在 `state/ai_views.sqlite3` 中建表：`users`、`user_jobs`、`workspace_members`、`workspace_invites`，并扩展 `published_versions` 增加 `visibility_mode` 与 `visibility_user_ids` 列（带默认值 `'private'` 与 `NULL`）
- [ ] 1.5 编写启动钩子，应用迁移并 seed `user_jobs`（开发者 / 项目经理 / Team Leader / 产品经理 / 人力资源 / 数据分析师 / 其他）；当 `AUTH_BOOTSTRAP_ADMIN_*` 存在且 `users` 为空时创建管理员

## 2. 后端用户账号能力（user-account capability）

- [ ] 2.1 新建 `apps/api/users.py`：定义 `UserRecord`、密码哈希工具（passlib bcrypt）、CRUD（create/by_email/by_id/search）
- [ ] 2.2 新建 `apps/api/jobs.py`：`GET /jobs` 返回岗位枚举（无需登录）
- [ ] 2.3 重写 `apps/api/auth.py`：保留 `AuthIdentity` 接口，增加邮箱+密码登录路径；签发 JWT + HttpOnly cookie；保留 `LEGACY_SERVICE_LOGIN_ENABLED` 控制下的旧 service-token 行为
- [ ] 2.4 实现路由：`POST /auth/register`、`POST /auth/login`、`POST /auth/logout`、`GET /auth/me`，挂载到 `main.py`
- [ ] 2.5 实现 `GET /users/search`：参数校验（q 长度 ≥2）、邮箱打码、每用户每分钟 60 次速率限制（基于 in-memory token bucket，按 user_id 维度）
- [ ] 2.6 单元测试 `tests/api/test_auth_routes.py`、`tests/api/test_users_search.py`、`tests/unit/test_password_hashing.py`：覆盖 `user-account/spec.md` 中的全部 Scenario

## 3. 后端工作空间协作能力（workspace-collaboration capability）

- [ ] 3.1 新建 `apps/api/collaboration.py`：`workspace_members` CRUD + `workspace_invites` CRUD；邀请 token 用 `itsdangerous.URLSafeTimedSerializer` 签名，DB 仅存 sha256
- [ ] 3.2 重构 `apps/api/workspaces.py`：所有 RBAC 调用改为查询 `workspace_members`；新建工作空间时自动写入 owner 行
- [ ] 3.3 实现路由：`POST /workspaces/{id}/members`、`PATCH /workspaces/{id}/members/{user_id}`、`DELETE /workspaces/{id}/members/{user_id}`、`GET /workspaces/{id}/members`
- [ ] 3.4 实现路由：`POST /workspaces/{id}/invites`、`GET /workspaces/{id}/invites`、`DELETE /workspaces/{id}/invites/{invite_id}`、`POST /invites/{token}/accept`
- [ ] 3.5 编写迁移工具 `scripts/migrate_workspaces_to_members.py`：将现有 in-memory 工作空间在第一次 owner 登录时落表（在 `auth.py` login 钩子中触发）
- [ ] 3.6 集成测试 `tests/integration/test_collaboration_flow.py`：覆盖搜索→邀请→接受→撤销→过期等 Scenario；安全测试 `tests/security/test_invite_tampering.py`

## 4. 后端发布可见性（workspace-publish 修改）

- [ ] 4.1 扩展 `POST /workspaces/{workspace_id}/publish` 请求模型加入 `visibility_mode` 与 `visibility_user_ids`，并按 spec 校验
- [ ] 4.2 写入 `published_versions.visibility_mode` 与 `visibility_user_ids` JSON 列；快照文件结构不变
- [ ] 4.3 调整 `GET /workspaces/{id}/published`：返回 `visibility_mode` 与 `visibility_user_count`（不返回 user_id 列表）
- [ ] 4.4 新增 `PATCH /workspaces/{id}/published/{version}/visibility` 路由，复用同一 visibility 校验
- [ ] 4.5 测试 `tests/api/test_publish_visibility.py` 覆盖 ADDED/MODIFIED 中的所有 Scenario，含 `invalid_user_ids`、`visibility_user_ids_only_allowed_in_allowlist`、PATCH 的 RBAC

## 5. 后端 Portal 可见性（published-portal 修改）

- [ ] 5.1 在 `apps/api/main.py` 或 `portal.py` 路由中加入 `require_session` 依赖；未登录返回 401
- [ ] 5.2 重写 `GET /portal/workspaces`：忽略 `user_id` query；从 token/cookie 取当前用户；按 owner/editor + visibility_mode 三态过滤
- [ ] 5.3 在 `GET /portal/pages/{page_id}/manifest` 与 `/charts/{chart_id}/data` 入口处加可见性校验：不可见返回 403 `page_not_visible`，page_id 不存在返回 404
- [ ] 5.4 测试 `tests/api/test_portal_visibility.py`：覆盖 ADDED Scenario（含设计者本人 private 仍可见、allowlist 外被 403、不存在的 page_id 仍 404）

## 6. 后端代码迁移与下线 legacy

- [ ] 6.1 替换 `apps/api/agentic_ingestion/` 与 `apps/api/views.py` 中所有依赖旧 `AuthIdentity` 内存 RBAC 的位置，改用 `workspace_members` 查询
- [ ] 6.2 在 `tests/smoke/run_smoke_flow.py` 中改为：注册一个测试用户 → 登录 → 创建工作空间 → 上传 → 查询 → 发布（private） → 查看
- [ ] 6.3 全部测试通过后，将 `.env.example` 的 `LEGACY_SERVICE_LOGIN_ENABLED` 默认改为 `false`，添加 README 说明 dev token 已下线

## 7. 前端：依赖、会话与拦截

- [ ] 7.1 在 `apps/web/lib/auth/` 下新建 `session.ts`（内存 token + cookie 同步）、`auth-client.ts`（封装 register/login/logout/me 调用）、`use-session.ts`（TanStack Query 包装 `GET /auth/me`）
- [ ] 7.2 修改 `apps/web/lib/api-client.ts`（或当前统一 fetch 包装）：自动附加 `Authorization: Bearer <token>` 与 `X-App-Mode: <mode>`；401 时引导到 `/login?next=<当前路径>`
- [ ] 7.3 在 `apps/web/middleware.ts` 添加路由保护：`/`、`/workspace/*`、`/portal/*` 未登录跳转 `/login?next=...`；`/login`、`/register`、`/invites/*`、`/jobs` 不要求登录
- [ ] 7.4 i18n：在 `apps/web/lib/i18n/dictionary.ts` 中新增"注册 / 登录 / 登出 / 岗位 / 设计者 / 查看者 / 私密 / 所有已注册用户可见 / 指定用户可见 / 协作者 / 邀请链接 / 复制 / 撤销"等键

## 8. 前端：注册/登录页面（user-account UI）

- [ ] 8.1 新增路由 `apps/web/app/(auth)/login/page.tsx` 与 `apps/web/app/(auth)/register/page.tsx`；使用现有 UI 组件（shadcn/ui form）
- [ ] 8.2 注册表单字段：邮箱、姓名、密码、岗位下拉（异步加载 `GET /jobs`）、提交按钮；前端校验密码长度
- [ ] 8.3 登录表单字段：邮箱、密码、提交；登录失败统一显示"邮箱或密码错误"
- [ ] 8.4 注册 / 登录成功后：写入会话，按 `next` 参数跳回，否则跳到 `/`
- [ ] 8.5 顶栏（`AppShell`）增加用户头像菜单：当前用户邮箱、岗位、登出按钮
- [ ] 8.6 Vitest 单测 `apps/web/tests/auth/login-form.test.tsx`、`register-form.test.tsx`

## 9. 前端：设计者/查看者模式切换（app-role-mode UI）

- [ ] 9.1 在 `apps/web/stores/ui-store.ts` 增加 `appMode: 'designer'|'viewer'` 与 `setAppMode`，持久化到 localStorage
- [ ] 9.2 在 `AppShell` 顶栏渲染 Segmented Control 切换器；`use-session.ts` 提供默认 mode 推断逻辑
- [ ] 9.3 viewer 模式下：隐藏面板切换器、Catalog、Workspace 入口；进入 viewer 模式自动跳转到 `/portal`
- [ ] 9.4 viewer 模式下尝试访问 `/workspace/*` 时在 middleware 中重定向到 `/portal`
- [ ] 9.5 确保所有 fetch 自动带 `X-App-Mode`（在 7.2 已完成可在此验证）
- [ ] 9.6 Vitest 单测 `apps/web/tests/ui/app-mode-switcher.test.tsx`

## 10. 前端：Canvas Publish 弹窗扩展（workspace-publish UI）

- [ ] 10.1 新增组件 `apps/web/components/workspace/publish-dialog.tsx`：三态可见性单选 + 用户搜索器 + 已选用户 chip
- [ ] 10.2 新增组件 `apps/web/components/sharing/user-search-input.tsx`（debounce 调用 `GET /users/search`，渲染下拉、键盘导航、加入选择）
- [ ] 10.3 修改 `WebDesignCanvas` 工具栏：Publish 按钮 onClick 改为打开 publish-dialog；按 owner/editor 角色控制可见性；保留空 chart 校验逻辑
- [ ] 10.4 `lib/workspace/publish.ts` 增加 `visibility_mode` 与 `visibility_user_ids` 参数；新增 `updateVersionVisibility(workspaceId, version, payload)`
- [ ] 10.5 发布历史面板（如已有）展示 `visibility_mode` 摘要文案；增加"修改可见性"入口（调用 PATCH 接口）
- [ ] 10.6 Vitest 单测 `apps/web/tests/ui/publish-dialog.test.tsx` 与 `apps/web/tests/ui/user-search-input.test.tsx`

## 11. 前端：Share 按钮与协作弹窗（workspace-collaboration UI）

- [ ] 11.1 新增组件 `apps/web/components/sharing/share-dialog.tsx`：三块结构（搜索器 / 协作者列表 / 邀请链接区）
- [ ] 11.2 新增 `apps/web/components/sharing/members-list.tsx`：渲染当前协作者，支持改角色与移除（带二次确认）
- [ ] 11.3 新增 `apps/web/components/sharing/invite-link-section.tsx`：复制、撤销、生成新链接；支持选择角色与有效期
- [ ] 11.4 修改 Canvas 工具栏：在 Publish 旁加 Share 按钮（仅 owner/editor 可见）；onClick 打开 share-dialog
- [ ] 11.5 `lib/workspace/collaboration.ts` 封装：`listMembers`、`addMember`、`updateMemberRole`、`removeMember`、`listInvites`、`createInvite`、`revokeInvite`
- [ ] 11.6 新增路由 `apps/web/app/invites/[token]/page.tsx`：登录态直接调用 accept；未登录跳转 `/register?invite=<token>`
- [ ] 11.7 修改 `/register` 页：检测到 `invite` query 参数，注册成功后调用 accept 并跳转工作空间
- [ ] 11.8 Playwright e2e `apps/web/tests/e2e/share-flow.spec.ts`：覆盖 owner 邀请→已注册用户接受→未注册用户先注册再接受→撤销链接

## 12. 前端：Portal 可见性 UI（published-portal UI）

- [ ] 12.1 修改 `app/portal/page.tsx` 与子页：使用 `useSession` 校验登录态；列表与详情接口 401/403 时友好提示
- [ ] 12.2 列表空状态文案改为中文"暂无可见的发布页。请联系设计者获取访问权限。"
- [ ] 12.3 详情页 403 `page_not_visible` 渲染独立的"无访问权限"页（区别于 404）
- [ ] 12.4 Vitest 单测 `apps/web/tests/ui/portal-visibility.test.tsx`

## 13. 端到端验证与文档

- [ ] 13.1 更新 `tests/smoke/run_smoke_flow.py`：注册→登录→创建工作空间→邀请协作者→发布（allowlist）→另一用户接受邀请并访问 portal→撤销链接→预期 410
- [ ] 13.2 跑 `make lint && make test && cd apps/web && npx vitest run && npx playwright test`，全部通过
- [ ] 13.3 在 `CLAUDE.md` 与 `README` 中增加"用户账号 / 协作 / 可见性"章节，说明 env 配置、首次启动管理员引导、邀请链接 TTL
- [ ] 13.4 在 `CONTRIBUTING.md` 中补充本地开发的注册/登录流程，替换原 demo token 说明
- [ ] 13.5 验证 docker compose 栈：`make docker-up && make smoke-docker` 通过；如有新增 env 已写入 `docker-compose.yml`
