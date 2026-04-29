# user-account Specification

## Purpose
TBD - created by archiving change user-auth-roles-and-sharing. Update Purpose after archive.
## Requirements
### Requirement: 用户注册接口与表单
系统 SHALL 提供 `POST /auth/register` 接口及前端 `/register` 页面。注册请求 MUST 包含 `email`、`password`、`display_name`、`job_id` 四个必填字段。`email` 必须是合法邮箱、唯一（大小写不敏感）；`password` 长度 SHALL 不小于 `PASSWORD_MIN_LENGTH`（默认 8）；`job_id` 必须存在于 `user_jobs` 表中。注册成功后系统 SHALL 自动登录该用户并下发 access_token + HttpOnly cookie。

#### Scenario: 注册成功
- **WHEN** 用户在 `/register` 页面填写合法的邮箱、密码、姓名并选择岗位"项目经理"，提交表单
- **THEN** 后端写入 `users` 表，密码以 bcrypt 哈希存储；响应 200，返回 `{user, access_token}`；前端写入 cookie 与内存 token 并跳转到 `/`

#### Scenario: 邮箱重复
- **WHEN** 用户使用已存在的邮箱（大小写不同）注册
- **THEN** 后端返回 HTTP 409 与 `{"error": "email_taken"}`；前端在表单上显示中文错误"该邮箱已被注册"

#### Scenario: 密码过短
- **WHEN** 用户提交密码长度小于 `PASSWORD_MIN_LENGTH`
- **THEN** 后端返回 HTTP 422 与字段级错误信息；前端表单标红密码字段并显示"密码至少 N 位"

#### Scenario: 岗位非法
- **WHEN** 请求体的 `job_id` 不在 `user_jobs` 表中
- **THEN** 后端返回 HTTP 422 与 `{"error": "invalid_job_id"}`

### Requirement: 用户登录与登出
系统 SHALL 提供 `POST /auth/login`（邮箱+密码）、`POST /auth/logout`、`GET /auth/me` 三个接口及前端 `/login` 页面。登录成功后下发 access_token（JWT，过期时间 `ACCESS_TOKEN_TTL_MIN` 分钟）与 HttpOnly cookie；登出时撤销 cookie 并使该用户的 token 黑名单生效到过期。`GET /auth/me` 返回当前登录用户的 `{id, email, display_name, job_label, available_workspaces, default_app_mode}`。

#### Scenario: 登录成功
- **WHEN** 用户在 `/login` 页提交正确的邮箱与密码
- **THEN** 后端校验密码哈希通过，更新 `last_login_at`，返回 access_token；前端跳转到 `/`

#### Scenario: 登录失败
- **WHEN** 邮箱不存在 或 密码错误
- **THEN** 后端返回 HTTP 401 与统一信息 `{"error": "invalid_credentials"}`（不区分两种情况以避免邮箱枚举）

#### Scenario: 拉取当前用户
- **WHEN** 已登录用户访问 `GET /auth/me`
- **THEN** 后端返回该用户的基本信息以及他作为 owner/editor/viewer 的工作空间列表

#### Scenario: 登出
- **WHEN** 用户点击登出
- **THEN** `POST /auth/logout` 撤销 session cookie；前端清空内存 token 并跳转到 `/login`

### Requirement: 岗位枚举表与下拉数据接口
系统 SHALL 在启动时 seed `user_jobs` 表，至少包含：开发者、项目经理、Team Leader、产品经理、人力资源、数据分析师、其他。系统 SHALL 提供 `GET /jobs` 返回 `[{id, code, label_zh, label_en, sort_order}]`，按 `sort_order` 升序排序。该接口 MUST 不要求登录态。

#### Scenario: 启动种子数据
- **WHEN** API 启动时 `user_jobs` 表为空
- **THEN** 启动钩子写入预置的岗位列表

#### Scenario: 注册页加载岗位
- **WHEN** 用户打开 `/register` 页
- **THEN** 前端调用 `GET /jobs` 并把返回项渲染为岗位下拉，按当前 locale 显示 `label_zh` 或 `label_en`

### Requirement: 注册用户搜索接口
系统 SHALL 提供 `GET /users/search?q=<term>&limit=<n>`，要求登录态。`q` 长度 MUST ≥ 2，`limit` 默认 20、最大 50。匹配规则：邮箱前缀匹配 OR 姓名包含匹配。返回字段 SHALL 仅包含 `{id, email_masked, display_name, job_label}`，邮箱以 `<前2位>***<@后段>` 形式打码。该接口 MUST 应用每用户每分钟 60 次的速率限制。

#### Scenario: 设计者搜索同事
- **WHEN** 已登录设计者在 Publish 弹窗的搜索框中输入 "li"
- **THEN** 前端调用 `GET /users/search?q=li`，后端返回 `[{id, email_masked: "li***@galaxyspace.ai", display_name: "李雷", job_label: "项目经理"}, ...]`

#### Scenario: 查询过短
- **WHEN** `q` 长度 < 2
- **THEN** 后端返回 HTTP 400 `{"error": "query_too_short"}`

#### Scenario: 速率限制触发
- **WHEN** 同一用户 1 分钟内调用搜索接口超过 60 次
- **THEN** 后端返回 HTTP 429 与 `Retry-After` 头

