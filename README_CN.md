# Cognitrix 识枢

[English](README.md) | 简体中文

Cognitrix（识枢）是一个面向任意结构化数据场景的 AI-Native BI 平台。项目当前由 FastAPI 后端、Next.js 前端、DuckDB 会话数据层和本地 SQLite 状态存储组成，支持 Excel 数据上传、语义指标查询、Agentic Query 流式对话、图表生成、可视化画布、视图保存、版本回滚与分享重水化。

## 当前进展

- `SPEC_PLAN.md` 中 M0-M9 共 45 个任务已经全部完成，当前工程具备本地运行、Docker 交付、后端/安全/集成/smoke 测试与 Agentic Query 主链路。
- 前端主界面已经从单页联调台推进到产品化工作台：左侧全局侧栏管理 Conversations / Workspaces，中间支持 Chat、Canvas、Split 三种布局，并提供 `⌘/Ctrl + 1/2/3/B` 快捷切换。
- Chat 主入口调用后端 `POST /chat/stream`，消费 `planning/tool_use/tool_result/spec/final/error` SSE 事件，并把返回 spec 归档为 ECharts 图表资产；历史 `reasoning/tool` 兼容事件仍保留。
- Workspace 使用 React Flow 画布，支持图表节点、文本节点、拖拽布局、重命名、复制、删除与本地保存。
- Share 页面已接入后端保存的 view state，可通过 `/share/[viewId]` 重新渲染图表与保存时的对话上下文，无需再次调用模型。
- 后端已经具备上传、语义层、受控 BI 工具面、Claude Agent SDK Agentic Query、权限控制、审计、视图版本化、Agent 会话恢复等核心能力。
- 仍处于原型/内测阶段：前端 Conversations / Workspaces / Chart Assets 的列表与画布状态当前主要通过 mock API 和 localStorage 管理；后端已承担真实数据上传、查询、Agent 对话流和分享视图存储。

## 核心能力

### 把 Excel 变成可分析的数据资产

- 业务团队可以直接上传任意结构化表格（HR、销售、财务、运营等），无需先建数仓、写 SQL 或整理复杂模板。
- 系统会自动识别常见字段含义，合并多份表格，并产出可继续分析的数据集。
- 上传后会给出数据质量反馈，帮助团队判断这份数据是否完整、是否适合进一步分析。
- 内置可扩展的语义指标层（YAML 驱动），支持跨领域指标口径定义，让各类业务问题可以直接被理解和计算。

### 用对话完成即席分析

- 用户可以像问业务分析师一样提问，例如“按部门看离职率”“找出高风险项目”“展示入职年份分布”。
- Agent 会根据问题自动探索表结构、读取样例、选择语义指标或生成只读 SQL，减少人工反复试表和改口径。
- 对于标准指标，系统会优先使用稳定口径；对于临时问题，也能让 AI 分析助手完成更灵活的数据探索。
- 回答不仅给出结果，还会配套生成图表和简短结论，帮助用户快速判断下一步该看哪里。
- 多轮对话会保留 `agent_session_id` 和最近一次结构化结果，支持类似“改成折线图”“再按部门拆一下”的追问。

### 从洞察到可视化工作台

- 对话中生成的图表可以沉淀为图表资产，继续放入工作台里组合、拖拽和整理。
- 用户可以在对话、画布和分屏模式之间切换，把一次问答延展成可复用的分析看板。
- 当前支持柱状图、折线图、饼图、面积图、散点图、漏斗图、表格、单指标卡等常见业务图表。
- 分析过程可以保留上下文，让后续追问、补充筛选和图表调整更自然。

### 让视图按权限被看见

- 关键分析可以保存为视图，并进入独立的展示入口，登录用户可读取自己或有权限访问的内容。
- 分享入口同样要求 Bearer 鉴权，并按调用者角色对保存的 AI state 做响应层脱敏。
- 私有视图读取遵循 owner/admin 访问规则；分享视图通过 `views:share` 权限开放给已登录角色。
- 同一份视图支持版本更新和回滚，适合持续迭代周报、项目复盘和管理驾驶舱。
- 上传、查询、分析操作、权限调整和回滚都会留下记录，方便团队追踪数据使用与分析过程。

## 技术栈

- Backend：FastAPI、Pydantic Settings、DuckDB、Pandas、sqlglot、SQLite。
- Agent Runtime：Claude Agent SDK `ClaudeSDKClient`、in-process SDK MCP BI tools、SDK permission callback + hooks、SQLite 持久化 agent sessions、Guardrails、结构化输出、SSE tool trace。
- Frontend：Next.js App Router、React 18、TypeScript、Tailwind CSS、Zustand、TanStack Query、React Flow、ECharts。
- Testing：pytest、Vitest / Playwright 测试文件、k6 压测脚本、smoke flow。
- Delivery：Makefile、Dockerfile、Docker Compose。

## 目录结构

```text
.
├── apps/api              # FastAPI 后端
├── apps/web              # Next.js 前端
├── models                # HR / PM 语义模型
├── sample_data           # 示例 Excel 数据
├── tests                 # 后端、集成、安全、smoke 测试
├── scripts               # 本地开发、构建、测试、重置脚本
├── docs/adr              # 架构决策记录
├── infra/docker          # 备用 Docker Compose 文件
└── packages/shared       # 共享包占位
```

## 环境要求

- Python 3.11+
- Node.js 20+
- npm 10+
- GNU Make
- Docker Desktop，可选，仅容器交付和 Docker smoke 需要

## 快速开始

安装依赖并生成本地环境文件：

```bash
make bootstrap
```

校验环境变量：

```bash
make env-check
```

启动本地 API 与 Web：

```bash
make dev
```

默认访问地址：

- Web：http://127.0.0.1:3000
- API：http://127.0.0.1:8000
- Health Check：http://127.0.0.1:8000/healthz

`make dev` 会启动本地 web/api 进程，不会安装或启动 PostgreSQL；当前默认状态存储使用本地 SQLite，上传数据、DuckDB 文件、AI view state 和 Agent session state 都位于 `apps/api/data/uploads` 下。

## 常用命令

```bash
make help              # 查看命令
make bootstrap         # 安装 Python / Web 依赖并初始化 .env
make env-check         # 校验 apps/api/.env 与 apps/web/.env
make dev               # 同时启动 API 和 Web
make dev-api           # 仅启动 FastAPI
make dev-web           # 仅启动 Next.js
make dev-local         # 调试模式启动，日志写入 logs/dev-local
make lint              # 后端 compileall + 前端 lint
make test              # 后端 pytest，设置 RUN_WEB_TESTS=1 后追加前端测试
make build             # 后端编译检查 + 前端生产构建
make smoke-local       # 本地端到端 smoke flow
make smoke-docker      # Docker 端到端 smoke flow
make test-all          # lint + test + build + smoke-local + 可选 smoke-docker
make reset-local-data  # 清理本地运行数据
make docker-up         # 构建并启动 Docker Compose
make docker-down       # 停止 Docker Compose
```

注意：`scripts/test.sh` 默认只跑后端 pytest。设置 `RUN_WEB_TESTS=1` 时会执行 `npm run --prefix apps/web test`，但当前 `apps/web/package.json` 尚未挂载 `test` 脚本；如需运行前端测试，可先补齐 package script，或直接按 Vitest / Playwright 配置运行对应测试。

## 本地配置

`make bootstrap` 会在缺失时从模板生成：

- `apps/api/.env`
- `apps/web/.env`

后端关键变量：

```env
DATABASE_URL=sqlite:///./data/uploads/state/ai_views.sqlite3
MODEL_PROVIDER_URL=https://api.deepseek.com
AI_API_KEY=
AI_MODEL=deepseek-chat
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_AUTH_TOKEN=
ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-chat
API_TIMEOUT_MS=600000
CLAUDE_AGENT_SDK_ENABLED=true
AGENTIC_INGESTION_ENABLED=true
AUTH_SECRET=replace-with-a-strong-secret
UPLOAD_DIR=./data/uploads
CORS_ALLOW_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
```

Excel 上传始终走 Agentic ingestion；`AGENTIC_INGESTION_ENABLED` 仅保留为兼容旧环境文件的配置项，不再关闭 `/ingestion/*`。

前端关键变量：

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXTAUTH_URL=http://127.0.0.1:3000
NEXTAUTH_SECRET=replace-with-a-strong-secret
```

前端对话默认上下文可通过这些可选变量调整：

```env
NEXT_PUBLIC_DEFAULT_USER_ID=demo-user
NEXT_PUBLIC_DEFAULT_PROJECT_ID=demo-project
NEXT_PUBLIC_DEFAULT_ROLE=hr
NEXT_PUBLIC_DEFAULT_DEPARTMENT=HR
NEXT_PUBLIC_DEFAULT_CLEARANCE=1
NEXT_PUBLIC_DEFAULT_DATASET_TABLE=employees_wide
```

Agentic Query 通过 Claude Agent SDK 运行，但默认接入 DeepSeek 的 Anthropic 兼容接口；`AI_API_KEY` 会传给 SDK CLI 作为 `ANTHROPIC_API_KEY` 与 `ANTHROPIC_AUTH_TOKEN`，`ANTHROPIC_BASE_URL` 默认指向 `https://api.deepseek.com/anthropic`，`AI_MODEL` 默认使用 `deepseek-chat`。如果需要单独覆盖 Claude Code CLI 的 token，可填写 `ANTHROPIC_AUTH_TOKEN`。

## Agentic Query

对话入口统一走 Agent 编排主路径，旧的规则式聊天链路不再作为运行时分支。

Agent 相关配置：

```env
CLAUDE_AGENT_SDK_ENABLED=true
AGENTIC_INGESTION_ENABLED=true
AGENT_MAX_TOOL_STEPS=20
AGENT_MAX_SQL_ROWS=2000
AGENT_MAX_SQL_SCAN_ROWS=10000
AGENT_TIMEOUT_SECONDS=120
```

Agent 工具面限制在 BI 相关操作：

- `list_tables`
- `describe_table`
- `sample_rows`
- `get_metric_catalog`
- `run_semantic_query`
- `execute_readonly_sql`
- `get_distinct_values`
- `save_view`

运行时会将 `conversation_id` 映射到可恢复的 `agent_session_id`，并把会话状态持久化到 `UPLOAD_DIR/state/agent_sessions.sqlite3`。所有工具调用仍复用现有 SQL 只读校验、RLS 注入、敏感字段过滤、响应脱敏和审计日志。

`POST /chat/stream` 当前主要事件：

- `planning`
- `tool_use`
- `tool_result`
- `spec`
- `final`
- `error`

兼容事件：

- `reasoning`
- `tool`

设计细节见 `docs/adr/0001-agentic-query-runtime.md`。

## API 概览

所有业务 API 除 `/healthz` 和 `/auth/login` 外都需要 `Authorization: Bearer <token>`。前端会自动调用 `/auth/login` 获取并缓存 token。

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/healthz` | 服务健康检查 |
| `POST` | `/auth/login` | 签发访问 token |
| `POST` | `/auth/roles/{user_id}` | 管理用户角色覆盖 |
| `GET` | `/audit/events` | 查询审计事件 |
| `POST` | `/ingestion/uploads` | 上传 Excel 并创建 Agentic ingestion job |
| `POST` | `/ingestion/plan` | 由 Write Ingestion Agent 生成写入方案 |
| `POST` | `/ingestion/approve` | 审批 Agent 写入方案 |
| `POST` | `/ingestion/execute` | 执行已审批写入方案 |
| `GET` | `/semantic/metrics` | 获取语义指标目录 |
| `POST` | `/semantic/query` | 执行语义查询 |
| `POST` | `/chat/tool-call` | 直接调用 BI 工具 |
| `POST` | `/chat/stream` | 流式 AI 对话与图表生成 |
| `POST` | `/views` | 保存 AI view |
| `GET` | `/views/{view_id}` | 读取私有 view |
| `GET` | `/share/{view_id}` | 读取分享 view |
| `POST` | `/views/{view_id}/rollback/{version}` | 回滚 view 版本 |

## 端到端验证

本地 smoke flow：

```bash
make smoke-local
```

覆盖链路：

```text
healthz -> auth/login -> upload Excel -> semantic query -> chat stream -> save view -> share view
```

完整测试门禁：

```bash
make test-all
```

也可以按需运行更细的测试：

```bash
.venv/bin/python -m pytest tests -q
.venv/bin/python -m pytest tests/security -q
.venv/bin/python -m pytest tests/integration -q
npm run --prefix apps/web build
```

## Docker 交付

构建并启动：

```bash
docker compose up -d --build
docker compose ps
```

停止：

```bash
docker compose down --remove-orphans
```

Make 包装命令：

```bash
make docker-up
make docker-down
make smoke-docker
```

默认 Compose 暴露：

- Web：`127.0.0.1:3000`
- API：`127.0.0.1:8000`

上传与状态数据保存在 Docker named volume `cognitrix_upload_data`。

## 数据重置

清理本地运行数据、上传文件、DuckDB / SQLite 状态、日志和测试产物：

```bash
make reset-local-data
```

预览将删除的内容：

```bash
.venv/bin/python scripts/reset_local_data.py --dry-run
```

同时重置 `apps/api/.env` 指向的数据库：

```bash
.venv/bin/python scripts/reset_local_data.py --with-db-reset
```

同时移除 Docker Compose named volumes：

```bash
.venv/bin/python scripts/reset_local_data.py --include-docker-volumes
```

## 示例数据

可用于本地上传验证的 Excel 样例：

- `sample_data/galaxyspace-hr-sample.xlsx`
- `sample_data/hr_workforce_upload_sample.xlsx`
- `sample_data/hr_workforce_upload_sample_zh.xlsx`

上传后，API 会返回 `batch_id`、`dataset_table`、`quality_report`、`diagnostics` 等信息。后续语义查询和对话请求需要使用返回的 `dataset_table`。

## 已知边界

- 前端主界面的 session、workspace、chart asset 列表仍是 mock/localStorage 形态，不等同于后端持久化对象；刷新浏览器可恢复本地状态，但换设备/清缓存后不会自动同步。
- `ChatWorkbench` 组件仍保留为测试/联调用途，但当前主路由渲染的是 `AppShell`。
- 默认 `NEXT_PUBLIC_DEFAULT_DATASET_TABLE=employees_wide` 需要和实际 DuckDB 会话表对齐；上传新文件后应使用返回的 `dataset_table`。
- Agent 模式已具备运行时和测试覆盖，但生产级模型接入、评测集扩展、成本控制和长会话体验还需要继续打磨。
- 前端测试文件和配置已存在，但当前 `package.json` 未提供统一 `npm test` / `test:ui` / `test:e2e` 脚本入口，需要后续整理后再接入 `make test`。
