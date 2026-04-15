# SmartHRBI

SmartHRBI 是一个面向 HR / PM 场景的 AI-Native BI 原型系统。项目当前由 FastAPI 后端、Next.js 前端、DuckDB 会话数据层和本地 SQLite 状态存储组成，支持 Excel 数据上传、语义指标查询、流式 AI 对话、图表生成、可视化画布、视图保存与分享。

## 当前进展

- 前端主界面已经从单页联调台推进到产品化工作台：左侧全局侧栏管理 Conversations / Workspaces，中间支持 Chat、Canvas、Split 三种布局。
- Chat 入口会调用后端 `POST /chat/stream`，消费 SSE 事件并把图表 spec 转成 ECharts 图表资产。
- Workspace 使用 React Flow 画布，支持添加图表节点、文本节点、拖拽布局、重命名、复制、删除与本地保存。
- Share 页面已接入后端保存的 view state，可通过 `/share/[viewId]` 重新渲染图表与保存时的对话上下文。
- 后端已经具备上传、语义层、工具调用、Agentic Query、权限控制、审计、视图版本化等核心能力。
- 仍处于原型/内测阶段：前端 Conversations / Workspaces / Chart Assets 的列表与画布状态当前主要通过 mock API 和 localStorage 管理，后端已承担真实数据上传、查询、对话流和分享视图存储。

## 核心能力

### 把 Excel 变成可分析的数据资产

- 业务团队可以直接上传 HR 或项目管理表格，无需先建数仓、写 SQL 或整理复杂模板。
- 系统会自动识别常见字段含义，合并多份表格，并产出可继续分析的数据集。
- 上传后会给出数据质量反馈，帮助团队判断这份数据是否完整、是否适合进一步分析。
- 内置 HR 与 PM 常用指标口径，让人数、离职率、薪资、项目延期、高风险项目等问题可以直接被理解和计算。

### 用对话完成即席分析

- 用户可以像问业务分析师一样提问，例如“按部门看离职率”“找出高风险项目”“展示入职年份分布”。
- 系统会根据问题自动探索数据、选择合适指标，并在需要时补充读取样例，减少人工反复试表和改口径。
- 对于标准指标，系统会优先使用稳定口径；对于临时问题，也能让 AI 分析助手完成更灵活的数据探索。
- 回答不仅给出结果，还会配套生成图表和简短结论，帮助用户快速判断下一步该看哪里。

### 从洞察到可视化工作台

- 对话中生成的图表可以沉淀为图表资产，继续放入工作台里组合、拖拽和整理。
- 用户可以在对话、画布和分屏模式之间切换，把一次问答延展成可复用的分析看板。
- 当前支持柱状图、折线图、饼图、面积图、散点图、漏斗图、表格、单指标卡等常见业务图表。
- 分析过程可以保留上下文，让后续追问、补充筛选和图表调整更自然。

### 让视图按权限被看见

- 关键分析可以保存为视图，并进入独立的展示入口，登录用户在统一入口查看自己有权访问的内容。
- 视图拥有者可以编辑可视权限，按用户、角色或项目控制哪些人能看到哪些视图。
- 视图内的图表也可以按权限呈现，让不同用户在同一分析资产中看到与自己相关的内容。
- 同一份视图支持版本更新和回滚，适合持续迭代周报、项目复盘和管理驾驶舱。
- 上传、查询、分析操作、权限调整和回滚都会留下记录，方便团队追踪数据使用与分析过程。

## 技术栈

- Backend：FastAPI、Pydantic Settings、DuckDB、Pandas、sqlglot、SQLite。
- Agent Runtime：Claude Agent SDK `ClaudeSDKClient`、in-process SDK MCP BI tools、SDK permission callback + hooks、SQLite 持久化 agent sessions、Guardrails、SSE tool trace。
- Frontend：Next.js App Router、React 18、TypeScript、Tailwind CSS、Zustand、TanStack Query、React Flow、ECharts。
- Testing：pytest、Vitest、Playwright、smoke flow。
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

`make dev` 会启动本地 web/api 进程，不会安装或启动 PostgreSQL；当前默认状态存储使用本地 SQLite，上传数据和 DuckDB 文件位于 `apps/api/data/uploads`。

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

注意：`scripts/test.sh` 在 `RUN_WEB_TESTS=1` 时会执行 `npm run --prefix apps/web test`。如果前端测试脚本尚未补齐，可直接运行 Vitest/Playwright 对应命令，或先只执行默认的 `make test`。

## 本地配置

`make bootstrap` 会在缺失时从模板生成：

- `apps/api/.env`
- `apps/web/.env`

后端关键变量：

```env
DATABASE_URL=sqlite:///./data/uploads/state/ai_views.sqlite3
MODEL_PROVIDER_URL=http://localhost:11434
AI_API_KEY=
AI_MODEL=claude-sonnet-4-5
CLAUDE_AGENT_SDK_ENABLED=true
AUTH_SECRET=replace-with-a-strong-secret
UPLOAD_DIR=./data/uploads
CORS_ALLOW_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
```

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

Agentic Query 通过 Claude Agent SDK 运行；`AI_API_KEY` 会传给 SDK CLI 作为 `ANTHROPIC_API_KEY`，`AI_MODEL` 建议使用 Claude 模型名。`MODEL_PROVIDER_URL` 仍保留给非 Agent 的 schema inference 等兼容路径。

## Agentic Query

对话入口统一走 Agent 编排主路径。

Agent 相关配置：

```env
CLAUDE_AGENT_SDK_ENABLED=true
AGENT_MAX_TOOL_STEPS=6
AGENT_MAX_SQL_ROWS=200
AGENT_MAX_SQL_SCAN_ROWS=10000
AGENT_TIMEOUT_SECONDS=25
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

设计细节见 `docs/adr/0001-agentic-query-runtime.md`。

## API 概览

所有业务 API 除 `/healthz` 外都需要 `Authorization: Bearer <token>`。前端会自动调用 `/auth/login` 获取并缓存 token。

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/healthz` | 服务健康检查 |
| `POST` | `/auth/login` | 签发访问 token |
| `POST` | `/auth/roles/{user_id}` | 管理用户角色覆盖 |
| `GET` | `/audit/events` | 查询审计事件 |
| `POST` | `/datasets/upload` | 上传 Excel 数据集 |
| `GET` | `/datasets/{batch_id}/quality-report` | 获取上传质量报告 |
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

上传与状态数据保存在 Docker named volume `smarthrbi_upload_data`。

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

- 前端主界面的 session、workspace、chart asset 列表仍是 mock/localStorage 形态，不等同于后端持久化对象。
- `ChatWorkbench` 组件仍保留为测试/联调用途，但当前主路由渲染的是 `AppShell`。
- 默认 `NEXT_PUBLIC_DEFAULT_DATASET_TABLE=employees_wide` 需要和实际 DuckDB 会话表对齐；上传新文件后应使用返回的 `dataset_table`。
- Agent 模式已具备运行时和测试覆盖，但生产级模型接入、评测集扩展和长会话体验还需要继续打磨。
