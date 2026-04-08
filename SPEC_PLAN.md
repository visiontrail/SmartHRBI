# SmartHRBI 实施 Spec 计划（基于 Framework.md）

## 0. 文档元信息

| 字段 | 值 |
| --- | --- |
| 文档ID | `smarthrbi-spec-v1` |
| 基线来源 | `Framework.md` |
| 当前版本 | `v1.4` |
| 创建日期 | `2026-04-07` |
| 当前状态 | `DONE` |
| 总进度 | `100.0% (37/37)` |

## 1. 文档用途

本文件用于将 `Framework.md` 的架构愿景转为可执行工程计划，目标是让 Coding Agent 可以按步骤独立完成：

1. 从 0 到 1 实现 AI-Native HR/PM 智能 BI 系统。
2. 在本机环境稳定运行并通过自动化测试。
3. 在 Docker 环境一键启动并通过端到端冒烟验证。
4. 在开发过程中可持续记录任务状态、证据、风险和决策，支持后续 AI 接力更新。

## 2. 成品范围（In Scope）

1. 多 Excel 上传与自动合并（支持列名对齐和 Schema Drift）。
2. DuckDB 分析引擎接入与会话隔离。
3. 语义层（指标定义、查询编译、权限上下文下推）。
4. LLM 对话式查询与 Tool Calling。
5. GenUI 渲染（Catalog/Spec/Registry + 流式响应）。
6. 图表双轨渲染（Shadcn/Recharts + ECharts）。
7. AI State 持久化、分享链接与 Rehydration。
8. RBAC + RLS + SQL AST 安全护栏。
9. 单元、集成、端到端、安全、性能测试。
10. 本机运行脚本与 Docker Compose 交付。

## 3. 非目标（Out of Scope）

1. 本期不做移动端原生 App。
2. 本期不做多云部署编排（K8s Helm）。
3. 本期不做复杂企业审批流集成（只预留扩展点）。

## 4. 建议技术栈基线

| 层 | 选型 |
| --- | --- |
| Frontend | Next.js (App Router) + TypeScript + shadcn/ui + Recharts + ECharts |
| Backend | FastAPI + Pydantic + Uvicorn |
| 分析引擎 | DuckDB |
| 持久化 | PostgreSQL（JSONB） |
| 语义检索 | Qdrant（可选） |
| SQL 安全 | sqlglot |
| 鉴权 | Auth.js 或 Keycloak（二选一，本计划默认 Auth.js） |
| 测试 | pytest + vitest + playwright + k6 |
| 容器 | Docker + Docker Compose |

## 5. 进度记录机制（支持后续 AI 更新）

### 5.1 状态枚举

`TODO` | `IN_PROGRESS` | `BLOCKED` | `DONE`

### 5.2 更新规则

1. 每完成一个任务，必须更新任务台账状态与证据。
2. 证据必须可追踪，示例：测试命令输出摘要、PR 编号、关键截图路径。
3. 总进度计算公式：`DONE任务数 / 全部任务数 * 100%`。
4. 若任务阻塞，必须在风险日志登记阻塞原因与解除条件。

### 5.3 机器可读任务台账（请保留标记）

<!-- TASK_BOARD_START -->
| ID | 任务名 | 状态 | 负责人 | 开始时间 | 完成时间 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| M0-01 | 项目骨架初始化 | DONE | AI-Agent | 2026-04-07 20:24 CST | 2026-04-07 20:46 CST | `make bootstrap`、`ONE_SHOT=1 make dev-web`、`ONE_SHOT=1 make dev-api` 通过；骨架目录与最小可运行 web/api 已落地 |
| M0-02 | 统一配置与环境变量模板 | DONE | AI-Agent | 2026-04-07 20:24 CST | 2026-04-07 20:46 CST | `apps/web/.env.example`、`apps/api/.env.example`、`scripts/env_check.py` 已实现；`make env-check` 通过；缺失变量用例返回明确错误 |
| M0-03 | Makefile 与脚本标准化 | DONE | AI-Agent | 2026-04-07 20:24 CST | 2026-04-07 20:47 CST | `Makefile + scripts/` 已覆盖 `lint/test/dev/build/smoke/docker-up/docker-down`；`make help/lint/test/build/smoke` 通过；`make docker-up/down` 在 Docker 缺失时返回清晰报错 |
| M1-01 | Excel 上传 API | DONE | AI-Agent | 2026-04-07 20:50 CST | 2026-04-07 21:16 CST | `POST /datasets/upload` 已支持多文件 Excel 上传、类型/大小/数量校验、批次元数据与失败原因记录；`pytest tests/api/test_upload.py -q` 通过 |
| M1-02 | DuckDB 会话库与隔离 | DONE | AI-Agent | 2026-04-07 20:50 CST | 2026-04-07 21:16 CST | 已实现 `user_id + project_id` 会话库标识、独立 DuckDB 文件、会话锁与回收接口；`pytest tests/integration/test_duckdb_isolation.py -q` 通过 |
| M1-03 | 多文件 Union By Name 合并 | DONE | AI-Agent | 2026-04-07 20:50 CST | 2026-04-07 21:16 CST | 已实现列名标准化 + Union By Name 对齐、缺失列 `NULL` 填充、来源文件标识与不可识别字段诊断；`pytest tests/integration/test_union_by_name.py -q` 通过 |
| M1-04 | 数据质量校验与入库报告 | DONE | AI-Agent | 2026-04-07 20:50 CST | 2026-04-07 21:16 CST | 已实现空值率/重复率/类型漂移校验与 `GET /datasets/{batch_id}/quality-report`；报告可追溯到文件和列级；`pytest tests/api/test_quality_report.py -q` 通过 |
| M2-01 | 语义模型 DSL 定义 | DONE | AI-Agent | 2026-04-07 21:18 CST | 2026-04-07 21:32 CST | 新增 `models/hr.yaml`、`models/pm.yaml` 与语义加载校验器；`pytest tests/unit/test_semantic_dsl.py -q`、`pytest tests/api/test_semantic_api.py -q` 通过 |
| M2-02 | 指标编译与查询生成器 | DONE | AI-Agent | 2026-04-07 21:18 CST | 2026-04-07 21:32 CST | 已实现 Query AST、意图解析与 SQL 编译器（含结构化错误与可解释来源）；`pytest tests/unit/test_metric_compiler.py -q`、`pytest tests/api/test_semantic_api.py -q` 通过 |
| M2-03 | AST 只读校验器 | DONE | AI-Agent | 2026-04-07 21:18 CST | 2026-04-07 21:32 CST | 基于 `sqlglot` 实现仅 SELECT 校验与敏感表/列拦截；`pytest tests/security/test_ast_guard.py -q` 通过 |
| M2-04 | 动态 RLS 注入器 | DONE | AI-Agent | 2026-04-07 21:18 CST | 2026-04-07 21:32 CST | 已实现 `role/department/clearance` 行级过滤注入并与 AST Guard 串联；`pytest tests/security/test_rls_enforcement.py -q` 通过 |
| M3-01 | LLM Tool Calling 协议 | DONE | AI-Agent | 2026-04-07 21:34 CST | 2026-04-07 21:45 CST | 已实现 `query_metrics/describe_dataset/save_view` 统一 Tool Calling schema、重试（最多 2 次）与幂等缓存；`POST /chat/tool-call` 打通；`.venv/bin/python -m pytest tests/integration/test_tool_calling.py -q` 通过 |
| M3-02 | 对话流式接口（SSE/RSC） | DONE | AI-Agent | 2026-04-07 21:34 CST | 2026-04-07 21:45 CST | 已实现 `POST /chat/stream` SSE 事件流（`reasoning/tool/spec/final`）与 `Last-Event-ID`/`last_event_id` 回放；`.venv/bin/python -m pytest tests/integration/test_chat_stream.py -q` 通过，首 chunk 延迟断言 `<2s` |
| M3-03 | 意图路由与图表策略器 | DONE | AI-Agent | 2026-04-07 21:34 CST | 2026-04-07 21:45 CST | 已实现复杂度打分与 Recharts/ECharts 自动路由，输出可解释原因与可直接渲染的 ECharts option；`.venv/bin/python -m pytest tests/unit/test_chart_strategy.py -q` 通过 |
| M4-01 | GenUI Catalog/Spec/Registry | DONE | AI-Agent | 2026-04-08 10:00 CST | 2026-04-08 10:13 CST | 已实现 `apps/web/lib/genui/catalog.ts` + `spec.ts` + `components/genui/registry.tsx`，基于白名单与 Zod 校验拦截非法 Spec；`npm --prefix apps/web run test:ui` 通过 |
| M4-02 | 流式聊天工作台 UI | DONE | AI-Agent | 2026-04-08 10:00 CST | 2026-04-08 10:13 CST | 已实现三栏工作台与 `/chat/stream` 事件消费（`reasoning/tool/spec/final`），并支持 `localStorage` 会话恢复；`npm --prefix apps/web run test:ui` 通过 |
| M4-03 | 双轨图表渲染器 | DONE | AI-Agent | 2026-04-08 10:00 CST | 2026-04-08 10:13 CST | 已实现 `ChartRenderer` 按 `engine` 切换 Recharts/ECharts，覆盖 `bar/line/pie/table/single_value/note`；`npm --prefix apps/web run test:charts` 通过 |
| M4-04 | 错误态/空态/骨架屏 | DONE | AI-Agent | 2026-04-08 10:00 CST | 2026-04-08 10:13 CST | 已统一错误态/空态/骨架屏并接入流式生命周期，避免白屏与未处理异常；`npm --prefix apps/web run test:states` 通过 |
| M5-01 | AI State 存储模型（JSONB） | DONE | AI-Agent | 2026-04-08 10:20 CST | 2026-04-08 10:48 CST | 已实现 `ai_views`、`ai_view_versions` 持久化模型与版本递增，支持 `ai_state` 序列化存储、版本历史查询与耗时统计；`.venv/bin/python -m pytest tests/integration/test_state_storage.py -q` 通过 |
| M5-02 | 保存分享页 API | DONE | AI-Agent | 2026-04-08 10:20 CST | 2026-04-08 10:48 CST | 已实现 `POST /views` + `GET /views/{view_id}` + `GET /share/{view_id}`，返回分享链接并校验登录用户；`.venv/bin/python -m pytest tests/api/test_save_view.py -q` 通过 |
| M5-03 | 分享页重水化（Rehydration） | DONE | AI-Agent | 2026-04-08 10:20 CST | 2026-04-08 10:48 CST | 已新增 Next.js `app/share/[viewId]` 重水化页，基于保存的 AI State 直接重建图表与对话上下文，无需再次调用 LLM；`.venv/bin/python -m pytest tests/e2e/test_share_rehydration.py -q`、`npm --prefix apps/web run build` 通过 |
| M5-04 | 版本快照与回滚 | DONE | AI-Agent | 2026-04-08 10:20 CST | 2026-04-08 10:48 CST | 已实现 `POST /views/{view_id}/rollback/{version}` 回滚与审计事件落盘（`view_events.log`）；`.venv/bin/python -m pytest tests/api/test_view_versioning.py -q` 通过 |
| M6-01 | 身份认证接入 | DONE | AI-Agent | 2026-04-08 10:56 CST | 2026-04-08 11:15 CST | 已新增 `POST /auth/login` Token 登录与过期校验，核心 API 与 `/share/{view_id}` 全部要求 Bearer 鉴权；`pytest tests/security/test_auth.py -q` 通过 |
| M6-02 | RBAC 页面与接口鉴权 | DONE | AI-Agent | 2026-04-08 10:56 CST | 2026-04-08 11:15 CST | 已落地 `Admin/HR/PM/Viewer` 权限矩阵、接口级权限依赖与角色变更覆盖（同 token 即时生效）；`pytest tests/security/test_rbac.py -q` 通过 |
| M6-03 | 敏感字段列级屏蔽 | DONE | AI-Agent | 2026-04-08 10:56 CST | 2026-04-08 11:15 CST | 已实现敏感字段策略字典，接入 SQL Guard + 响应层双重脱敏（查询/描述/分享视图）；`pytest tests/security/test_column_masking.py -q` 通过 |
| M6-04 | 审计日志与告警事件 | DONE | AI-Agent | 2026-04-08 10:56 CST | 2026-04-08 11:15 CST | 已新增结构化安全审计日志（登录/上传/查询/分享/拒绝）与检索接口 `GET /audit/events`；`pytest tests/security/test_audit_log.py -q` 通过 |
| M7-01 | 后端单元测试 | DONE | AI-Agent | 2026-04-08 11:20 CST | 2026-04-08 12:01 CST | 新增 `tests/unit/test_security_hardening.py`、`tests/unit/test_semantic_edge_cases.py`；`.venv/bin/python -m pytest tests/unit --cov=apps.api.semantic --cov=apps.api.security --cov-report=term-missing` 通过（`semantic=88%`、`security=95%`） |
| M7-02 | 前端单元测试 | DONE | AI-Agent | 2026-04-08 11:20 CST | 2026-04-08 12:01 CST | 新增 `apps/web/tests/lib/sse-parser.test.ts`、`apps/web/tests/lib/session-storage.test.ts` 与覆盖率配置；`npm --prefix apps/web run test:coverage` 通过（`lines=83.69%`、`functions=82.75%`、`branches=70.37%`） |
| M7-03 | 集成测试（API+DB） | DONE | AI-Agent | 2026-04-08 11:20 CST | 2026-04-08 12:01 CST | `.venv/bin/python -m pytest tests/integration -q` 通过（`8 passed`） |
| M7-04 | 端到端测试（Playwright） | DONE | AI-Agent | 2026-04-08 11:20 CST | 2026-04-08 12:01 CST | 新增 `apps/web/playwright.config.ts` 与 `apps/web/tests/e2e/upload-to-share.spec.ts`；`npm --prefix apps/web run test:e2e` 通过（Chromium/WebKit 双浏览器） |
| M7-05 | 安全测试（注入/越权） | DONE | AI-Agent | 2026-04-08 11:20 CST | 2026-04-08 12:01 CST | `.venv/bin/python -m pytest tests/security -q` 通过（`16 passed`） |
| M7-06 | 性能测试（k6） | DONE | AI-Agent | 2026-04-08 11:20 CST | 2026-04-08 12:01 CST | 新增 `tests/perf/chat_query.js`；本地启动 API 后执行 `k6 run tests/perf/chat_query.js` 通过（`query_50 p95=803.79ms <2.5s`，`query_100 http_req_failed=0.10% <1%`） |
| M8-01 | 本机运行脚本与文档 | DONE | AI-Agent | 2026-04-08 12:03 CST | 2026-04-08 12:19 CST | `make dev` 已改为启动前校验/拉起 PostgreSQL（`scripts/ensure_postgres.sh`）并并行启动 web/api；README 补齐本机一条龙流程与命令索引；`make help`、`make lint`、`make test`、`make build`、`SKIP_POSTGRES_BOOTSTRAP=1 bash scripts/dev_all.sh` 通过 |
| M8-02 | Frontend Dockerfile | DONE | AI-Agent | 2026-04-08 12:03 CST | 2026-04-08 12:19 CST | 新增 `apps/web/Dockerfile`（多阶段构建、生产启动、容器健康检查），并补充 `.dockerignore`；`bash -n scripts/*.sh`、`npm --prefix apps/web run lint` 通过 |
| M8-03 | Backend Dockerfile | DONE | AI-Agent | 2026-04-08 12:03 CST | 2026-04-08 12:19 CST | 新增 `apps/api/Dockerfile`（包含 DuckDB 依赖安装、`/healthz` 健康检查、Uvicorn 启动）并接入 CORS 配置；`.venv/bin/python -m py_compile apps/api/config.py apps/api/main.py` 通过 |
| M8-04 | docker-compose 编排 | DONE | AI-Agent | 2026-04-08 12:03 CST | 2026-04-08 12:19 CST | 新增根目录 `docker-compose.yml` 并同步 `infra/docker/docker-compose.yml`（web/api/postgres 三服务、健康检查、依赖顺序、数据卷）；`scripts/docker_up.sh`/`docker_down.sh` 已切换默认 compose |
| M8-05 | 本机与 Docker 冒烟验收 | DONE | AI-Agent | 2026-04-08 12:03 CST | 2026-04-08 13:25 CST | 已补齐本机 Docker 运行时（colima + docker compose）；`make smoke-local`、`make smoke-docker`、`make test-all` 全部通过，本机与容器链路均完成上传->问答->图表->保存->分享闭环 |
<!-- TASK_BOARD_END -->

### 5.4 更新日志模板

<!-- CHANGELOG_START -->
| 时间 | 操作人 | 变更内容 | 影响任务ID | 证据 |
| --- | --- | --- | --- | --- |
| 2026-04-07 | AI-Agent | 初始化 Spec 文档 | ALL | `SPEC_PLAN.md` |
| 2026-04-07 20:47 CST | AI-Agent | 完成 M0 第一阶段：项目骨架、环境模板与 Makefile 标准化，补齐自动化脚本与基础测试 | M0-01,M0-02,M0-03 | `make bootstrap/env-check/help/lint/test/build/smoke`、`ONE_SHOT=1 make dev-api/dev-web`、`make docker-up/down`（Docker 缺失时明确报错）输出记录 |
| 2026-04-07 21:16 CST | AI-Agent | 完成 M1 数据摄取阶段：上传 API、DuckDB 会话隔离、Union By Name 合并、质量报告 API 与测试闭环 | M1-01,M1-02,M1-03,M1-04 | `pytest tests/api/test_upload.py -q`、`pytest tests/integration/test_duckdb_isolation.py -q`、`pytest tests/integration/test_union_by_name.py -q`、`pytest tests/api/test_quality_report.py -q`、`make test`、`make lint` 通过 |
| 2026-04-07 21:32 CST | AI-Agent | 完成 M2 语义层与安全编译阶段：语义 DSL、指标编译、AST 只读校验、动态 RLS 注入与 API 接口打通 | M2-01,M2-02,M2-03,M2-04 | `pytest tests/unit/test_semantic_dsl.py -q`、`pytest tests/unit/test_metric_compiler.py -q`、`pytest tests/security/test_ast_guard.py -q`、`pytest tests/security/test_rls_enforcement.py -q`、`pytest tests/api/test_semantic_api.py -q`、`make test`、`make lint` 通过 |
| 2026-04-07 21:45 CST | AI-Agent | 完成 M3 对话编排阶段：Tool Calling 协议、SSE 流式接口与图表策略器，补齐断线回放与复杂路由测试 | M3-01,M3-02,M3-03 | `.venv/bin/python -m pytest tests/integration/test_tool_calling.py -q`、`.venv/bin/python -m pytest tests/integration/test_chat_stream.py -q`、`.venv/bin/python -m pytest tests/unit/test_chart_strategy.py -q`、`make test`、`make lint` 通过 |
| 2026-04-08 10:13 CST | AI-Agent | 完成 M4 GenUI 前端渲染阶段：落地 Catalog/Spec/Registry、流式三栏工作台、Recharts/ECharts 双轨渲染与统一错误/空态/骨架屏，并新增分组前端测试 | M4-01,M4-02,M4-03,M4-04 | `npm --prefix apps/web run test`、`npm --prefix apps/web run test:ui`、`npm --prefix apps/web run test:charts`、`npm --prefix apps/web run test:states`、`npm --prefix apps/web run lint`、`npm --prefix apps/web run build` 通过 |
| 2026-04-08 10:48 CST | AI-Agent | 完成 M5 持久化与分享阶段：新增视图状态存储模型、分享 API、重水化页面与版本回滚能力，并将 Tool Calling `save_view` 接入真实持久化 | M5-01,M5-02,M5-03,M5-04 | `.venv/bin/python -m pytest tests/integration/test_state_storage.py -q`、`.venv/bin/python -m pytest tests/api/test_save_view.py -q`、`.venv/bin/python -m pytest tests/e2e/test_share_rehydration.py -q`、`.venv/bin/python -m pytest tests/api/test_view_versioning.py -q`、`.venv/bin/python -m pytest tests -q`、`npm --prefix apps/web run lint/test/build`、`make lint`、`make test` 通过 |
| 2026-04-08 11:15 CST | AI-Agent | 完成 M6 安全与合规阶段：接入 token 认证、RBAC 权限依赖、敏感字段双层屏蔽与结构化审计日志/检索；同步改造既有测试为鉴权流程并新增 M6 专项安全测试 | M6-01,M6-02,M6-03,M6-04 | `.venv/bin/python -m pytest tests/security/test_auth.py -q`、`.venv/bin/python -m pytest tests/security/test_rbac.py -q`、`.venv/bin/python -m pytest tests/security/test_column_masking.py -q`、`.venv/bin/python -m pytest tests/security/test_audit_log.py -q`、`.venv/bin/python -m pytest tests -q`、`npm --prefix apps/web run test`、`npm --prefix apps/web run build`、`make lint`、`make test` 通过 |
| 2026-04-08 12:01 CST | AI-Agent | 完成 M7 测试闭环阶段：补齐后端安全/语义覆盖率单测、前端覆盖率与 Playwright 双浏览器 E2E、并落地 k6 查询压测脚本及阈值校验 | M7-01,M7-02,M7-03,M7-04,M7-05,M7-06 | `.venv/bin/python -m pytest tests/unit --cov=apps.api.semantic --cov=apps.api.security --cov-report=term-missing`、`npm --prefix apps/web run test:coverage`、`.venv/bin/python -m pytest tests/integration -q`、`npm --prefix apps/web run test:e2e`、`.venv/bin/python -m pytest tests/security -q`、`k6 run tests/perf/chat_query.js` 通过 |
| 2026-04-08 12:19 CST | AI-Agent | 完成 M8 交付实现：补齐本机启动脚本、前后端 Dockerfile、三服务 compose 编排与端到端 smoke runner；本机 smoke 已通过，Docker smoke 在当前环境因 Docker 缺失阻塞 | M8-01,M8-02,M8-03,M8-04,M8-05 | `make help`、`make lint`、`make test`、`make build`、`make smoke-local`（环境阻塞报错）、`SKIP_POSTGRES_BOOTSTRAP=1 make smoke-local`、`make smoke-docker`（Docker 缺失报错）、`SKIP_POSTGRES_BOOTSTRAP=1 RUN_DOCKER_SMOKE=0 make test-all`；新增 `apps/web/Dockerfile`、`apps/api/Dockerfile`、`docker-compose.yml`、`tests/smoke/run_smoke_flow.py` |
| 2026-04-08 13:25 CST | AI-Agent | 完成 M8-05 最终验收：补齐 Docker/Compose 运行时并完成本机+容器双链路冒烟，所有自动化测试与交付验收达标 | M8-05 | `make smoke-local`、`make smoke-docker`、`make test-all` 全部通过；`docker info` 与 `docker compose version` 可用 |
<!-- CHANGELOG_END -->

### 5.5 风险日志模板

<!-- RISK_LOG_START -->
| 风险ID | 描述 | 级别 | 状态 | 缓解措施 | 责任人 |
| --- | --- | --- | --- | --- | --- |
| R-001 | LLM 输出不稳定导致图表 Spec 不合法 | 高 | OPEN | 增加 Zod 强校验 + 自动纠错重试 | AI-Agent |
| R-002 | Excel 列定义差异过大导致合并失败 | 中 | OPEN | 入库前标准化映射 + 缺失列填充策略 | AI-Agent |
| R-003 | 越权查询风险 | 高 | OPEN | RBAC + RLS + AST 三层拦截 | AI-Agent |
| R-004 | 当前执行环境缺少 Docker 与本地 PostgreSQL，导致 M8 Docker 验收无法在本机完成 | 中 | CLOSED | 已安装并启动 Docker 运行时（colima + docker compose），并复验 `make smoke-docker` 与 `make test-all` 通过 | AI-Agent |
<!-- RISK_LOG_END -->

## 6. 分阶段实施计划（一步一步）

## 6.1 M0 基础工程与约束（先打地基）

### M0-01 项目骨架初始化

目标：建立 monorepo 结构和最小可运行骨架。  
实施步骤：
1. 创建 `apps/web`、`apps/api`、`packages/shared`、`infra/docker`、`tests`。
2. 初始化前后端依赖与基础启动命令。
3. 提供统一目录规范与命名规则。

验收标准：
1. 执行 `make bootstrap` 不报错。
2. 前端和后端可分别输出健康检查接口或页面。
3. 目录结构与文档一致。

自测命令：
```bash
make bootstrap
make dev-web
make dev-api
```

### M0-02 统一配置与环境变量模板

目标：保证本机和 Docker 环境一致性。  
实施步骤：
1. 提供 `.env.example`（web/api 各一份）。
2. 定义必要变量：数据库、模型服务、鉴权、日志级别、上传目录。
3. 增加启动前配置检查脚本。

验收标准：
1. 缺失关键变量时启动失败且报错清晰。
2. 补齐变量后服务可正常启动。

自测命令：
```bash
make env-check
```

### M0-03 Makefile 与脚本标准化

目标：统一执行入口，便于 Coding Agent 自动化。  
实施步骤：
1. 实现 `make lint/test/dev/build/smoke/docker-up/docker-down`。
2. 将核心命令收敛到 `Makefile` 与 `scripts/`。

验收标准：
1. 各命令均可执行且输出明确。
2. 新人按 README 可在 15 分钟内跑通本机环境。

自测命令：
```bash
make help
```

## 6.2 M1 数据摄取与 DuckDB 分析底座

### M1-01 Excel 上传 API

目标：支持单次上传多个 Excel。  
实施步骤：
1. FastAPI 实现 `POST /datasets/upload`。
2. 限制文件类型、大小、数量并返回批次 ID。
3. 保存原始文件元数据。

验收标准：
1. 支持至少 10 个 Excel 同批上传。
2. 非法文件被拒绝并给出可读错误码。
3. 上传耗时、失败原因被记录。

自测命令：
```bash
pytest tests/api/test_upload.py -q
```

### M1-02 DuckDB 会话库与隔离

目标：每个用户会话绑定独立 DuckDB 文件或 schema。  
实施步骤：
1. 按 `user_id + project_id` 生成会话库标识。
2. 读写生命周期管理（创建、回收、锁控制）。

验收标准：
1. 不同用户请求不会互相读到对方数据。
2. 并发上传与查询下无会话串扰。

自测命令：
```bash
pytest tests/integration/test_duckdb_isolation.py -q
```

### M1-03 多文件 Union By Name 合并

目标：处理列顺序变化、缺失列、重命名场景。  
实施步骤：
1. 建立列名标准化字典。
2. 通过 DuckDB `union_by_name` 或等效逻辑合并。
3. 对不可识别字段产出诊断报告。

验收标准：
1. 乱序列可自动对齐。
2. 缺失列以 `NULL` 补齐并保留来源标识。
3. 输出统一宽表供后续查询。

自测命令：
```bash
pytest tests/integration/test_union_by_name.py -q
```

### M1-04 数据质量校验与入库报告

目标：入库时可解释质量状态。  
实施步骤：
1. 校验空值率、重复率、字段类型漂移。
2. 生成质量报告 API：`GET /datasets/{batch_id}/quality-report`。

验收标准：
1. 质量报告可追溯到文件与列级别。
2. 严重错误可阻断发布到语义层。

自测命令：
```bash
pytest tests/api/test_quality_report.py -q
```

## 6.3 M2 语义层与安全查询编译

### M2-01 语义模型 DSL 定义

目标：将 HR/PM 指标固化为声明式配置。  
实施步骤：
1. 定义 `models/hr.yaml`、`models/pm.yaml`。
2. 约束实体、维度、指标、Join、权限标签。

验收标准：
1. DSL 可通过 schema 校验。
2. 指标可被 API 列举与查询。

自测命令：
```bash
pytest tests/unit/test_semantic_dsl.py -q
```

### M2-02 指标编译与查询生成器

目标：自然语言意图映射到语义指标查询。  
实施步骤：
1. 先将意图解析为内部 Query AST。
2. 将 Query AST 编译成 DuckDB SQL。
3. 编译失败时返回结构化错误便于重试。

验收标准：
1. 至少覆盖 15 个核心 HR/PM 指标。
2. 编译结果可解释（含指标来源和过滤条件）。

自测命令：
```bash
pytest tests/unit/test_metric_compiler.py -q
```

### M2-03 AST 只读校验器

目标：禁止危险 SQL 和非白名单访问。  
实施步骤：
1. 使用 `sqlglot` 解析 SQL。
2. 限制仅允许 `SELECT`。
3. 阻断敏感表和敏感列直读。

验收标准：
1. `DROP/DELETE/UPDATE` 全部被拦截。
2. 非授权列访问返回权限错误。

自测命令：
```bash
pytest tests/security/test_ast_guard.py -q
```

### M2-04 动态 RLS 注入器

目标：任何查询自动携带用户可见范围。  
实施步骤：
1. 从 JWT 提取 `department/role/clearance`。
2. 在编译后的 SQL 注入行级过滤条件。
3. 与 AST 校验串联执行。

验收标准：
1. 同一查询在不同角色下返回不同结果且符合预期。
2. 越权提示语可读，不暴露内部结构。

自测命令：
```bash
pytest tests/security/test_rls_enforcement.py -q
```

## 6.4 M3 LLM 编排与对话引擎

### M3-01 LLM Tool Calling 协议

目标：定义模型与后端工具通信契约。  
实施步骤：
1. 定义工具：`query_metrics`、`describe_dataset`、`save_view`。
2. 统一请求/响应 JSON schema。
3. 工具调用失败重试与幂等保护。

验收标准：
1. 模型可稳定触发工具并返回结构化结果。
2. 工具异常可恢复，最多重试 2 次后优雅失败。

自测命令：
```bash
pytest tests/integration/test_tool_calling.py -q
```

### M3-02 对话流式接口（SSE/RSC）

目标：支持实时输出文本和图表 Spec。  
实施步骤：
1. 实现 `POST /chat/stream`。
2. 按 chunk 推送 reasoning、tool、spec、final 四类事件。

验收标准：
1. 首 token 延迟 < 2 秒（本机开发环境）。
2. 断线重连可恢复会话上下文。

自测命令：
```bash
pytest tests/integration/test_chat_stream.py -q
```

### M3-03 意图路由与图表策略器

目标：在普通图和复杂图之间自动切换。  
实施步骤：
1. 请求复杂度打分。
2. 默认走 Recharts 规范，复杂场景切 ECharts option。

验收标准：
1. 给定同一查询，策略器输出可解释路由原因。
2. 复杂图配置可被前端直接渲染。

自测命令：
```bash
pytest tests/unit/test_chart_strategy.py -q
```

## 6.5 M4 GenUI 前端渲染

### M4-01 GenUI Catalog/Spec/Registry

目标：实现可控生成渲染闭环。  
实施步骤：
1. Catalog 定义可用组件白名单。
2. Zod 定义每类组件 Spec。
3. Registry 将 Spec 安全映射到 React 组件。

验收标准：
1. 非法 Spec 无法渲染。
2. 合法 Spec 可 100% 映射并显示。

自测命令：
```bash
pnpm -C apps/web test
```

### M4-02 流式聊天工作台 UI

目标：用户可边问边看生成过程。  
实施步骤：
1. 聊天区、图表区、数据概览区三栏布局。
2. 事件流消费与状态同步。

验收标准：
1. 文本和图表可增量出现。
2. 页面刷新后可恢复最近会话。

自测命令：
```bash
pnpm -C apps/web test:ui
```

### M4-03 双轨图表渲染器

目标：支持 Recharts 与 ECharts 混合。  
实施步骤：
1. 实现 `ChartRenderer`。
2. 根据 Spec 中 `engine` 字段切换引擎。

验收标准：
1. 常规柱状图/折线图/饼图正常渲染。
2. 海量点位图在 ECharts 下无明显卡顿。

自测命令：
```bash
pnpm -C apps/web test:charts
```

### M4-04 错误态/空态/骨架屏

目标：提升容错与可用性。  
实施步骤：
1. 对工具失败、空数据、权限不足定义统一 UI。
2. 流式阶段展示骨架屏占位。

验收标准：
1. 所有错误分支均有明确用户提示。
2. 不出现白屏或未处理异常。

自测命令：
```bash
pnpm -C apps/web test:states
```

## 6.6 M5 持久化与分享

### M5-01 AI State 存储模型（JSONB）

目标：可存储可重建 UI 的最小状态。  
实施步骤：
1. PostgreSQL 建表：`ai_views`、`ai_view_versions`。
2. 存储字段含 UUID、owner、rbac_scope、ai_state、version。

验收标准：
1. 单次保存可在 200ms 内完成（不含大模型时延）。
2. 同一视图支持版本递增。

自测命令：
```bash
pytest tests/integration/test_state_storage.py -q
```

### M5-02 保存分享页 API

目标：将当前工作台保存为可分享链接。  
实施步骤：
1. 实现 `POST /views`。
2. 返回 `/share/{uuid}`。

验收标准：
1. 仅登录用户可创建分享。
2. 返回链接可在新会话打开。

自测命令：
```bash
pytest tests/api/test_save_view.py -q
```

### M5-03 分享页重水化（Rehydration）

目标：无需再次调用 LLM 即可重建页面。  
实施步骤：
1. 分享页按 UUID 拉取 AI State。
2. 通过 Registry 重建组件树。

验收标准：
1. 分享页首屏可见时间 < 1.5 秒（本机）。
2. 渲染结果与保存时一致。

自测命令：
```bash
pytest tests/e2e/test_share_rehydration.py -q
```

### M5-04 版本快照与回滚

目标：保留历史视图，支持回滚。  
实施步骤：
1. 每次保存生成新版本。
2. 实现 `POST /views/{uuid}/rollback/{version}`。

验收标准：
1. 任意历史版本可恢复并可再次分享。
2. 回滚过程记录审计日志。

自测命令：
```bash
pytest tests/api/test_view_versioning.py -q
```

## 6.7 M6 安全与合规

### M6-01 身份认证接入

目标：实现统一登录与会话管理。  
实施步骤：
1. 接入 Auth.js（或替换 Keycloak）。
2. JWT 中加入角色和部门声明。

验收标准：
1. 未登录无法访问核心 API 与分享页。
2. 令牌过期后自动退出并提示。

自测命令：
```bash
pytest tests/security/test_auth.py -q
```

### M6-02 RBAC 页面与接口鉴权

目标：控制页面级与接口级访问。  
实施步骤：
1. 定义角色矩阵：`Admin/HR/PM/Viewer`。
2. API 中间件强制校验权限。

验收标准：
1. 无权限访问返回 403。
2. 权限变化可即时生效。

自测命令：
```bash
pytest tests/security/test_rbac.py -q
```

### M6-03 敏感字段列级屏蔽

目标：防止模型输出敏感字段。  
实施步骤：
1. 建立敏感字段字典。
2. 在 SQL AST 和响应层双重屏蔽。

验收标准：
1. 非授权角色查询薪资字段时被拦截。
2. 错误信息不泄露真实字段名。

自测命令：
```bash
pytest tests/security/test_column_masking.py -q
```

### M6-04 审计日志与告警事件

目标：实现关键行为可追踪。  
实施步骤：
1. 记录登录、上传、查询、分享、拒绝事件。
2. 输出结构化日志并支持检索。

验收标准：
1. 任意查询可追踪到用户、时间、结果状态。
2. 越权尝试会生成安全告警事件。

自测命令：
```bash
pytest tests/security/test_audit_log.py -q
```

## 6.8 M7 测试闭环（Coding Agent 可自测）

### M7-01 后端单元测试

验收标准：
1. 语义编译、SQL 安全、RLS 注入覆盖率 >= 85%。
2. 关键安全模块覆盖率 >= 95%。

自测命令：
```bash
pytest tests/unit --cov=apps.api.semantic --cov=apps.api.security --cov-report=term-missing
```

### M7-02 前端单元测试

验收标准：
1. GenUI 解析和渲染逻辑覆盖率 >= 80%。
2. 图表策略与状态管理核心路径全覆盖。

自测命令：
```bash
npm --prefix apps/web run test:coverage
```

### M7-03 集成测试（API+DB）

验收标准：
1. 上传 -> 合并 -> 查询 -> 渲染链路可打通。
2. 数据隔离与权限控制在集成层通过。

自测命令：
```bash
pytest tests/integration -q
```

### M7-04 端到端测试（Playwright）

验收标准：
1. 用户从上传数据到分享页面全流程通过。
2. 至少覆盖 Chrome 与 WebKit。

自测命令：
```bash
npm --prefix apps/web run test:e2e
```

### M7-05 安全测试（注入/越权）

验收标准：
1. Prompt Injection 场景下无法获得越权数据。
2. SQL 注入样例全部失败并被记录。

自测命令：
```bash
pytest tests/security -q
```

### M7-06 性能测试（k6）

验收标准：
1. 50 并发下 `p95` 查询响应 < 2.5s。
2. 100 并发下系统无崩溃且错误率 < 1%。

自测命令：
```bash
# 需先启动本地 API（例如：uvicorn apps.api.main:app --host 127.0.0.1 --port 8000）
k6 run tests/perf/chat_query.js
```

## 6.9 M8 交付与运行（本机 + Docker）

### M8-01 本机运行脚本与文档

目标：一条命令本机启动。  
验收标准：
1. `make dev` 同时启动 web/api/postgres。
2. README 包含完整操作流程。

自测命令：
```bash
make dev
make smoke-local
```

### M8-02 Frontend Dockerfile

目标：可构建可运行的前端镜像。  
验收标准：
1. 镜像构建成功，容器健康检查通过。
2. 启动后可访问前端首页。

自测命令：
```bash
docker build -f apps/web/Dockerfile -t smarthrbi-web:local .
```

### M8-03 Backend Dockerfile

目标：可构建可运行的后端镜像。  
验收标准：
1. 镜像构建成功，`/healthz` 返回 200。
2. 包含 DuckDB 运行依赖。

自测命令：
```bash
docker build -f apps/api/Dockerfile -t smarthrbi-api:local .
```

### M8-04 docker-compose 编排

目标：容器环境一键启动。  
验收标准：
1. `docker compose up --build` 可启动完整系统。
2. web -> api -> db 网络连通，关键接口可调用。

自测命令：
```bash
docker compose up --build -d
docker compose ps
```

### M8-05 本机与 Docker 冒烟验收

目标：完成最终成品交付判定。  
验收标准：
1. 本机完成一次完整业务流：上传 -> 问答 -> 图表 -> 保存 -> 分享。
2. Docker 环境完成同样业务流且结果一致。
3. 所有自动化测试绿灯。

自测命令：
```bash
make smoke-local
make smoke-docker
make test-all
```

## 7. 全局完成定义（Definition of Done）

1. `TASK_BOARD` 中全部任务状态为 `DONE`。
2. 本机与 Docker 两套环境冒烟测试通过。
3. 安全测试和性能基线满足 M7 指标。
4. README、部署文档、故障排查文档齐全。
5. 关键功能均有自动化测试和可追踪证据。

## 8. Coding Agent 执行顺序建议

1. 先做 M0 与 M1，确保数据可上传、可查询。
2. 再做 M2 与 M3，打通语义编译和 LLM 查询。
3. 然后做 M4 与 M5，完成 GenUI 和分享持久化。
4. 最后做 M6、M7、M8，完成安全、测试、运行交付。

## 9. 里程碑通过闸门（Gate）

| Gate | 通过条件 |
| --- | --- |
| G1 | M0-M1 全部 `DONE`，上传与查询链路可用 |
| G2 | M2-M3 全部 `DONE`，对话驱动查询可稳定返回 |
| G3 | M4-M5 全部 `DONE`，可保存并重建分享页 |
| G4 | M6-M7 全部 `DONE`，安全与测试指标达标 |
| G5 | M8 全部 `DONE`，本机和 Docker 均可运行成品 |

## 10. 附录：首批核心验收用例（建议）

1. 上传 3 份结构不同的员工表，系统正确合并并返回统一宽表。
2. 以 HR 角色查询“本季度离职率”，结果可计算且可追溯公式。
3. 以 PM 角色尝试查询薪资字段，被拒绝并有审计记录。
4. 生成预算消耗柱状图并保存分享链接，另一个同权限用户可正确打开。
5. Docker 启动后执行完整业务流，结果与本机环境一致。
