# SPEC: Workspace-Scoped Agentic Data Ingestion for SmartHRBI

## 0. 文档信息

- **名称**：Workspace-Scoped Agentic Data Ingestion
- **适用项目**：SmartHRBI
- **目标版本**：V1
- **优先级**：High
- **实施方式**：增量重构，新增 Agentic ingestion 主链路，保留 legacy upload 作为迁移期 fallback
- **主要受众**：后端开发、前端开发、Agent Runtime 开发、测试、产品

---

## 1. 背景与问题定义

SmartHRBI 当前已经具备一条较完整的 **Agentic Query** 主链路：前端通过 `POST /chat/stream` 发起对话，后端由 Claude Agent SDK 驱动 Agent 进行 schema 探索、受限 BI 工具调用、结构化输出与图表生成；会话通过 `conversation_id -> agent_session_id` 做持久化恢复。与此同时，当前 Excel 上传链路仍然是传统后端摄入流程：`POST /datasets/upload` 接收 `.xlsx`，用 `pandas/openpyxl` 解析，做 union-by-name 合并，可选触发 OpenAI-compatible schema inference，然后写入 DuckDB 的 `dataset_{batch_id}` 表。

当前的问题不是“能不能上传 Excel”，而是：**写入链路没有被统一纳入 Agentic runtime 的治理模型**。这会带来四个直接问题：

1. 查询和写入走的是两套心智模型，产品体验不统一。
2. 上传后的业务决策仍然主要靠硬编码，缺少 Agent 主导的“识别数据意图 → 规划写入方式 → 解释差异 → 人工确认 → 执行”的闭环。
3. HITL（Human in the Loop）无法在写入场景中以结构化审批卡片的形式稳定落地。
4. 现有上传流程缺少“面向业务的 proposal / receipt / execution trace”，更像文件摄入，而不是可治理的数据写入。

Claude Agent SDK 官方支持 **自定义工具、MCP、hooks、structured outputs、权限控制、subagents、用户输入/审批回调** 等能力；但 `AskUserQuestion` 更适合 Agent 在运行时向用户发起澄清或审批，而不适合作为业务产品层稳定可控的审批 UI，因此本项目将采用 **“Agent 输出结构化 proposal + 前端审批卡片 + 后端确定性执行”** 的方式，而不是直接把业务审批托管给 SDK。

---

## 2. 目标

### 2.1 总目标

将 SmartHRBI 的“Excel / 结构化数据写入”能力统一改造为一条 **Workspace 级、Agentic、可审批、可审计、可回执** 的数据摄入链路。

### 2.2 V1 必须达成

1. 用户登录后必须先进入 **Workspace 选择 / 创建** 流程。
2. 写入规则不再是用户级，而是 **Workspace 级持久化**。
3. 前端聊天窗口上传 Excel 后，系统能够路由到 **Write Ingestion Agent**。
4. Agent 可以读取：
    - 当前 Workspace 的 writable table catalog
    - 当前数据库内现有表结构与样例
    - 当前上传 Excel 的结构摘要、样例数据、统计信息
5. Agent 输出 **结构化 ingestion proposal**。
6. 前端展示固定审批模式：
    - 更新现有表
    - 按时间维度新建表（月 / 季 / 年）
    - 创建独立新表
    - 取消
7. 用户确认后，由后端确定性执行写入，并返回 execution receipt。
8. 整个过程具备：
    - 审计日志
    - proposal 持久化
    - execution 持久化
    - 失败可定位
9. 保留 Query Agent，不与 Write Agent 混成一个全能 Agent。
10. V1 不做“自然语言行级写回”，只做 **数据集摄入**。

---

## 3. 非目标

以下内容不属于本次 Feature 范围：

1. 不实现完整企业级 IAM / SSO / 组织架构系统。
2. 不实现复杂的“逻辑数据集 + 多版本管理平台”。
3. 不实现行级自然语言增删改。
4. 不实现跨 Workspace 的表共享治理。
5. 不强求一次性替换掉 legacy `/datasets/upload`。
6. 不将业务审批建立在 Claude SDK 的 `AskUserQuestion` 机制上。
7. 不引入通用“任意数据库写入平台”，本次仅覆盖 SmartHRBI 的受控数据摄入。

---

## 4. 核心决策

### 4.1 Workspace 优先

登录后先让用户创建或选择 Workspace。

Workspace 是数据写入规则、catalog、权限、ingestion jobs 的归属容器。

### 4.2 Project 不是顶层容器

当前系统已有 `project_id` 概念，但 V1 中：

- **Workspace** 是顶层归属
- **Project** 可作为二级业务维度保留，但不作为写入规则的唯一归属单位

### 4.3 不做重型逻辑数据集层，改做轻量 catalog

V1 不引入复杂“logical dataset/version”体系，但必须引入 **Workspace-scoped writable table catalog**，用于告诉 Agent：

- 哪些表可写
- 这些表属于什么业务类型
- 默认写入模式是什么
- 主键 / 匹配列是什么
- 是否是当前有效目标表

### 4.4 单独的 Write Ingestion Agent

不要把 Query Agent 和 Write Agent 混在一起。

采用**确定性路由**：

- 有文件附件，或文本表现为导入/更新/写入意图 → Write Ingestion Agent
- 其他分析问题 → Query Agent

Claude Agent SDK 支持 subagents，但本 Feature V1 不依赖自动子代理委派；优先采用应用层显式路由，这样更稳定、可测、易审计。

### 4.5 HITL 由前端产品层实现

Agent 只输出结构化 proposal。

前端将 proposal 渲染为固定模式审批卡片。

用户审批后，再由后端执行。

### 4.6 可以保留“任意写 SQL”，但只能作为受控执行层能力

Agent 可以生成候选 SQL / 写入方案，但不能直接自由执行任意写 SQL。

必须经过：

1. proposal 生成
2. validator / dry-run
3. approval 绑定
4. transaction execution
5. receipt & audit

### 4.7 新增 Agentic ingestion API，而不是强行改旧上传接口

前端仍可保持一个聊天入口，但后端新增独立 ingestion API 族，以支撑 proposal / approval / execution 生命周期。

---

## 5. 用户故事

### 5.1 Workspace 创建

作为首次进入系统的用户，我希望先创建一个 Workspace，后续所有数据摄入规则都归属于这个 Workspace。

### 5.2 首次写入初始化

作为 Workspace 的管理员或可写成员，我第一次上传一份花名册时，希望系统识别当前 Workspace 还没有 catalog，并引导我用自然语言或表单方式完成初始化规则。

### 5.3 Agentic proposal

作为上传 Excel 的用户，我希望系统能分析这份文件是花名册、项目进度表还是其他表，并告诉我推荐的写入方式，而不是直接静默入库。

### 5.4 人工审批

作为业务用户，我希望在真正写库前看到：

- 推荐目标表
- 推荐动作
- 预估新增/更新/冲突数量
- 风险提示
并由我决定是否执行。

### 5.5 可回执

作为操作者，我希望写入完成后能看到 execution receipt，知道最终写到了哪张表、影响多少行、是否成功。

---

## 6. 目标用户流程

### 6.1 登录与 Workspace

1. 用户登录
2. 若无 Workspace，进入创建流程
3. 若有多个 Workspace，先选择
4. 进入主界面

### 6.2 首次 ingestion

1. 用户在聊天窗口上传 Excel
2. 后端上传原始文件并创建 `upload_id`
3. 路由到 Write Ingestion Agent
4. 若当前 Workspace 没有匹配的 catalog，触发 setup flow
5. setup flow 产出 catalog entry
6. Agent 基于 catalog + workbook + existing tables 生成 proposal
7. 前端渲染审批卡片
8. 用户确认
9. 后端执行
10. 返回 execution receipt

### 6.3 非首次 ingestion

1. 用户上传 Excel
2. 系统读取 Workspace catalog
3. Agent 生成 proposal
4. 用户确认
5. 执行写入
6. 返回 receipt

---

## 7. 目标架构

## 7.1 总体架构分层

### A. 应用路由层

负责判断：

- 当前请求是 Query 还是 Write Ingestion
- 当前是否需要进入 catalog setup flow
- 当前是否进入 proposal/approval/execution 的哪个阶段

### B. Workspace & Catalog 层

负责：

- Workspace 生命周期
- 成员与角色
- Writable table catalog
- 规则持久化

### C. Write Ingestion Agent 层

负责：

- 识别文件类型 / 业务类型
- 读取已有表信息
- 比较 Excel 与目标表
- 产出结构化 proposal

### D. Execution 层

负责：

- staging
- SQL 生成
- SQL 校验
- dry-run
- 事务执行
- receipt
- audit

### E. Legacy Upload 兼容层

在迁移期保留旧 `/datasets/upload` 能力，不作为主入口，但可用于：

- 回退
- 对比测试
- 迁移验证

---

## 8. 数据模型

## 8.1 新增表：users

最小用户表。

建议字段：

- `id`
- `email`
- `display_name`
- `created_at`
- `updated_at`
- `status`

> 说明：V1 只需要最小用户概念，不需要完整企业 IAM。
> 

---

## 8.2 新增表：workspaces

Workspace 顶层容器。

建议字段：

- `id`
- `name`
- `slug`
- `owner_user_id`
- `created_at`
- `updated_at`
- `status`

---

## 8.3 新增表：workspace_members

Workspace 成员关系。

建议字段：

- `id`
- `workspace_id`
- `user_id`
- `role`
    - `owner`
    - `admin`
    - `editor`
    - `viewer`
- `created_at`

---

## 8.4 新增表：table_catalog

Workspace 级写入目录。

建议字段：

- `id`
- `workspace_id`
- `table_name`
- `human_label`
- `business_type`
    - `roster`
    - `project_progress`
    - `attendance`
    - `other`
- `write_mode`
    - `update_existing`
    - `time_partitioned_new_table`
    - `new_table`
    - `append_only`
- `time_grain`
    - `none`
    - `month`
    - `quarter`
    - `year`
- `primary_keys` (JSON array)
- `match_columns` (JSON array)
- `is_active_target`
- `description`
- `created_by`
- `updated_by`
- `created_at`
- `updated_at`

> 说明：这不是重型逻辑数据集层，而是一张给 Agent 用的“写入规则地图”。
> 

---

## 8.5 新增表：ingestion_uploads

原始上传记录。

建议字段：

- `id`
- `workspace_id`
- `uploaded_by`
- `file_name`
- `storage_path`
- `size_bytes`
- `file_hash`
- `sheet_summary` (JSON)
- `column_summary` (JSON)
- `sample_preview` (JSON)
- `created_at`
- `status`

---

## 8.6 新增表：ingestion_jobs

一次摄入任务的生命周期。

建议字段：

- `id`
- `workspace_id`
- `upload_id`
- `created_by`
- `agent_session_id`
- `status`
    - `uploaded`
    - `planning`
    - `awaiting_catalog_setup`
    - `awaiting_user_approval`
    - `approved`
    - `executing`
    - `succeeded`
    - `failed`
    - `cancelled`
- `business_type_guess`
- `created_at`
- `updated_at`

---

## 8.7 新增表：ingestion_proposals

Agent 输出的结构化 proposal。

建议字段：

- `id`
- `job_id`
- `workspace_id`
- `proposal_version`
- `proposal_json`
- `recommended_action`
- `target_table`
- `predicted_insert_count`
- `predicted_update_count`
- `predicted_conflict_count`
- `risk_summary`
- `generated_sql_draft`
- `created_at`

---

## 8.8 新增表：ingestion_executions

实际执行记录。

建议字段：

- `id`
- `job_id`
- `proposal_id`
- `workspace_id`
- `executed_by`
- `execution_mode`
- `validated_sql`
- `dry_run_summary`
- `execution_receipt`
- `status`
- `started_at`
- `finished_at`

---

## 8.9 新增表：ingestion_events

事件流 / 审计友好日志。

建议字段：

- `id`
- `job_id`
- `event_type`
- `payload`
- `created_at`

## 9. API 设计

## 9.1 Workspace API

### `POST /workspaces`

创建 Workspace。

请求：

- `name`

响应：

- `workspace_id`
- `name`
- `role=owner`

### `GET /workspaces`

列出当前用户可访问 Workspace。

### `POST /workspaces/{workspace_id}/members`

添加成员（V1 可选，如果当前没有完整用户管理，可以先只支持 owner/admin 管理）。

---

## 9.2 Catalog API

### `GET /workspaces/{workspace_id}/table-catalog`

获取 catalog 列表。

### `POST /workspaces/{workspace_id}/table-catalog`

创建 catalog entry。

### `PATCH /workspaces/{workspace_id}/table-catalog/{catalog_id}`

更新 catalog entry。

### `POST /workspaces/{workspace_id}/table-catalog/setup`

用于 setup flow 写入 catalog 初始化结果。

> 说明：此接口由前端 setup flow 或 Agent 生成的 setup result 调用。
> 

---

## 9.3 Ingestion Upload API

### `POST /ingestion/uploads`

职责：

- 接收 Excel
- 保存原始文件
- 提取 workbook 基础摘要
- 创建 `upload_id`

请求：

- `workspace_id`
- `files[]`

响应：

- `upload_id`
- `job_id`
- `file_summary`
- `sheet_summary`
- `column_summary`
- `sample_preview`

> 这里不负责最终入库，只负责把“上传”变成一个可规划对象。
> 

---

## 9.4 Ingestion Planning API

### `POST /ingestion/plan`

职责：

- 基于 upload + workspace catalog + existing tables 启动 Write Ingestion Agent
- 返回结构化 proposal
- 若 catalog 缺失，返回 setup required

请求：

- `workspace_id`
- `job_id`
- `conversation_id`（可选，用于与聊天 UI 绑定）

响应可能有两类：

### A. 需要 catalog setup

- `status = awaiting_catalog_setup`
- `setup_questions`
- `agent_guess`
- `suggested_catalog_seed`

### B. 成功生成 proposal

- `status = awaiting_user_approval`
- `proposal_id`
- `proposal_json`

---

## 9.5 Ingestion Approval API

### `POST /ingestion/approve`

职责：

- 用户确认 proposal
- 指定最终动作
- 进入 execution 阶段

请求：

- `workspace_id`
- `job_id`
- `proposal_id`
- `approved_action`
- `user_overrides`（可选）
    - 例如强制改成 `new_table`
    - 或修改表名、时间粒度

响应：

- `status = approved`

---

## 9.6 Ingestion Execution API

### `POST /ingestion/execute`

职责：

- 根据已审批 proposal 执行写入
- 返回 receipt

请求：

- `workspace_id`
- `job_id`
- `proposal_id`

响应：

- `execution_id`
- `status`
- `receipt`

---

## 9.7 Ingestion Job Query API

### `GET /ingestion/jobs/{job_id}`

职责：

- 查看任务当前状态
- proposal
- execution receipt
- event timeline

---

## 9.8 与聊天入口的关系

前端仍然保留一个聊天窗口。

但实现上：

- 文件上传先走 `/ingestion/uploads`
- 再由聊天 orchestrator 或前端调用 `/ingestion/plan`
- 审批后调用 `/ingestion/approve` + `/ingestion/execute`

即：**聊天是 UI 入口，ingestion API 是后端真实生命周期接口**。

---

## 10. Agent 设计

## 10.1 Agent 类型

### Query Agent

继续负责：

- 数据查询
- 指标解释
- 图表生成
- 分析对话

### Write Ingestion Agent

新增，负责：

- 识别上传文件业务类型
- 读取 workspace catalog
- 读取现有数据库表
- 形成写入 proposal
- 生成 SQL draft / write plan

---

## 10.2 路由规则

### 路由到 Write Ingestion Agent 的条件

满足任一条件：

1. 请求中有文件附件
2. 文本意图明显包含：
    - 上传
    - 导入
    - 更新花名册
    - 导入项目进度
    - 写入数据库
    - replace / append / merge
3. 当前会话正处于 ingestion lifecycle 中

### 否则走 Query Agent

> 这层由应用代码确定性判断，不依赖 Agent 自己决定。
> 

---

## 10.3 Write Ingestion Agent 的工具面

Claude Agent SDK 适合通过自定义工具 / SDK MCP server 暴露受限能力；本 Feature 中，Write Ingestion Agent 只允许访问 ingestion 相关工具，不允许访问 shell、filesystem、browser 等默认广义工具。官方文档说明 SDK 支持自定义工具、MCP server、hooks、权限模式、`allowed_tools` / `disallowed_tools` / `canUseTool` 等机制；同时在 `dontAsk` 模式下，不会再走运行时交互授权回调。

建议工具列表：

1. `get_workspace_catalog(workspace_id)`
2. `list_existing_tables(workspace_id)`
3. `describe_table_schema(workspace_id, table_name)`
4. `sample_table_rows(workspace_id, table_name, limit)`
5. `inspect_upload(upload_id)`
6. `inspect_workbook_sheet(upload_id, sheet_name)`
7. `infer_business_type(upload_id)`
    
    > 可做成代码工具，也可做成 Agent 自行推断
    > 
8. `build_diff_preview(upload_id, target_table, match_columns, action_mode)`
9. `generate_write_sql_draft(upload_id, target_table, action_mode, mapping)`
10. `validate_write_sql(sql, workspace_id, constraints)`
11. `save_ingestion_proposal(job_id, proposal_json)`
12. `save_catalog_setup_result(workspace_id, catalog_entries)`

---

## 10.4 Agent 输出格式

Write Ingestion Agent 必须使用 **structured output**，禁止仅返回自由文本。Claude Agent SDK 官方支持 JSON Schema / Pydantic 约束的 structured outputs，适合把结果直接交给应用逻辑和前端 UI。

建议输出结构：

```
{
  "business_type":"roster",
  "confidence":0.93,
  "recommended_action":"update_existing",
  "candidate_actions": [
"update_existing",
"time_partitioned_new_table",
"new_table",
"cancel"
  ],
  "target_table":"employee_roster",
  "time_grain":"none",
  "match_columns": ["employee_id"],
  "column_mapping": {
    "员工编号":"employee_id",
    "姓名":"employee_name",
    "部门":"department"
  },
  "diff_preview": {
    "predicted_insert_count":12,
    "predicted_update_count":84,
    "predicted_conflict_count":3
  },
  "risks": [
"salary column has mixed numeric/string values",
"3 rows cannot be matched by employee_id"
  ],
  "explanation":"This file looks like an employee roster and matches the active roster table in the workspace.",
  "sql_draft":"...",
  "requires_catalog_setup":false
}
```

---

## 10.5 为什么不用 `AskUserQuestion` 做审批

Claude SDK 的 `AskUserQuestion` 是 Agent 在运行时需要澄清问题时触发的交互机制，问题由 Claude 生成，并通过 `canUseTool` 回调返回用户选择；它更适合“运行时追问”，不适合本产品需要的固定审批卡片、固定动作按钮、可审计 proposal 版本流。

因此本项目明确规定：

- Agent 只生成 proposal
- 前端负责渲染审批 UI
- 后端只在用户显式确认后执行

---

## 11. Catalog Setup Flow 设计

## 11.1 触发条件

满足任一条件触发 setup：

1. 当前 Workspace 没有任何 catalog
2. 当前文件对应的业务类型在 Workspace 中没有匹配 catalog
3. Agent 无法高置信度定位目标表

---

## 11.2 Setup Flow 目标

通过少量对话式问题，为当前 Workspace 建立第一批可写表规则。

---

## 11.3 Setup Flow 输出

最终必须落成结构化 catalog entries，而不是只保存自然语言说明。

---

## 11.4 推荐的 setup 问题类型

最多 3~5 个，避免过长：

1. 这份表更像哪一类数据？
    - 花名册
    - 项目进度
    - 其他
2. 这类表通常应该：
    - 更新现有表
    - 每月新建
    - 每季度新建
    - 每年新建
    - 每次都新建独立表
3. 这类表通常用什么作为匹配键？
    - `employee_id`
    - `project_id`
    - 其他
4. 当前哪张表是这类数据的主表？
    - 列出候选表
    - 或允许新建

## 12. SQL 执行与安全模型

## 12.1 原则

允许内部使用任意写 SQL 作为表达形式，但不能让 Agent 直接自由执行。

---

## 12.2 执行前必须经过四步

### Step 1. SQL Draft

Agent 生成 `sql_draft` 或 write plan。

### Step 2. Validator

后端校验：

- 仅允许当前 workspace 的目标表
- 不允许越权表
- 不允许危险全库级写入
- 检查目标列存在
- 检查 mapping 合法
- 检查 action_mode 与 catalog 一致
- 检查 approval 绑定

### Step 3. Dry Run

生成：

- 预计受影响行数
- 预计新增/更新数量
- 冲突数量
- schema mismatch
- null/duplicate 风险

### Step 4. Transaction Execution

通过后端确定性执行器执行。

---

## 12.3 SQL 与 Proposal 绑定

`execute` 时必须校验：

- proposal 未过期
- proposal 已审批
- proposal 对应的 `sql_draft` 没有被篡改
- 若用户 override 了动作，需重新生成 / 重新校验 SQL

---

## 12.4 审计要求

必须记录：

- 谁触发了 proposal
- proposal 内容
- 谁批准
- 实际执行 SQL
- dry-run 结果
- 最终 receipt
- 失败原因

---

## 13. 前端改造

## 13.1 登录后新增 Workspace 流程

新增页面或弹窗：

- 若用户没有 Workspace，强制创建
- 若有多个，先选择

---

## 13.2 聊天窗口支持 ingestion lifecycle

聊天 UI 需要支持：

- 上传文件后的“处理中”状态
- setup 卡片
- proposal 审批卡片
- execution receipt 卡片

---

## 13.3 Proposal 卡片 UI

固定展示：

- 文件识别类型
- 推荐动作
- 目标表
- 匹配键
- 预计新增数
- 预计更新数
- 冲突数
- 风险
- 可选动作按钮

按钮：

- 更新现有表
- 按月新建
- 按季度新建
- 按年新建
- 创建独立新表
- 取消

---

## 13.4 Setup 卡片 UI

展示：

- Agent 猜测
- 当前缺少的规则
- 结构化选择项
- 可补充文本说明

---

## 13.5 Execution Receipt 卡片

展示：

- 执行动作
- 目标表
- 新增/更新/跳过数量
- 失败数量
- 关键 warning
- 是否成功

---

## 14. 后端改造

## 14.1 新增 Workspace 服务

实现：

- 创建 Workspace
- 获取用户 Workspace 列表
- 校验用户在 Workspace 中的角色

---

## 14.2 新增 Catalog 服务

实现：

- CRUD
- 查询 active target
- 按 `business_type` 匹配
- 按 `write_mode` 返回约束

---

## 14.3 新增 Upload Inspection 服务

职责：

- 保存原始文件
- 抽取 workbook 基础摘要
- 提供 sheet/column/sample 信息
- 生成 upload metadata

> 这里可以复用当前部分 Excel 解析能力，但不必继承 legacy API 形状。
> 

---

## 14.4 新增 Write Ingestion Agent Runtime

职责：

- 构造 system prompt
- 挂载工具
- structured output
- 保存 proposal
- 通过 hooks 记录 tool trace

---

## 14.5 新增 Execution 服务

职责：

- staging table
- mapping
- sql draft validation
- dry run
- transaction execute
- receipt persist

---

## 14.6 Legacy Upload 隔离

保留 `/datasets/upload` 与质量报告逻辑，但标记为 legacy。

V1 新前端不再直接依赖它作为主写入链路。

---

## 15. 实施任务拆分

## M0. 方案落地与骨架搭建

**目标**：完成基础目录、模型、接口骨架。

任务：

1. 新建 ADR：`workspace-scoped-agentic-ingestion.md`
2. 定义后端模块目录
3. 新增基础 migration / schema
4. 新增 feature flags：
    - `AGENTIC_INGESTION_ENABLED`
    - `LEGACY_DATASET_UPLOAD_ENABLED`

验收：

- 工程可启动
- 新模块空骨架存在
- feature flags 生效

---

## M1. Workspace 最小模型

**目标**：系统支持 Workspace 创建与选择。

任务：

1. 新增 `users / workspaces / workspace_members`
2. 登录后若无 Workspace，引导创建
3. 前端增加 Workspace 选择状态
4. API 鉴权增加 Workspace 校验

验收：

- 用户可创建 Workspace
- 聊天页能绑定当前 Workspace
- 非成员不可访问 Workspace 资源

---

## M2. Table Catalog 能力

**目标**：支持 Workspace 级 catalog 持久化。

任务：

1. 建表 `table_catalog`
2. CRUD API
3. catalog service
4. 后端 role 校验
5. 前端基础管理页或最小只读视图

验收：

- 能为 Workspace 创建至少一条 catalog entry
- 能按 `business_type` 查询 active target
- catalog 数据持久化可读

---

## M3. Upload Inspection 新链路

**目标**：上传文件只做 inspection，不直接入库。

任务：

1. `POST /ingestion/uploads`
2. 保存原始文件
3. 提取：
    - sheet 列表
    - 列名
    - sample rows
    - 文件 hash
4. 新建 `ingestion_uploads / ingestion_jobs`

验收：

- 上传后返回 `upload_id` 和 `job_id`
- 原始文件已落盘
- inspection 元数据已持久化

---

## M4. Write Ingestion Agent Runtime

**目标**：Agent 能读取 catalog / upload / existing tables 并生成 proposal。

任务：

1. 新建 `WriteIngestionAgentRuntime`
2. 定义 tools
3. 定义 structured output schema
4. 保存 `ingestion_proposals`
5. hooks 记录 tool_use / tool_result
6. route layer 实现 Query/Write 分流

验收：

- 上传 Excel 后能成功生成 proposal
- proposal 持久化成功
- route layer 能稳定命中 Write Agent

---

## M5. Setup Flow

**目标**：Workspace 首次写入时可完成 catalog 初始化。

任务：

1. setup trigger 逻辑
2. setup proposal schema
3. 前端 setup 卡片
4. setup confirm API
5. 生成 catalog entry

验收：

- 没有 catalog 的 Workspace 上传首个文件时，系统能引导 setup
- setup 后 catalog 生效
- 再次上传同类文件时不再重复 setup

---

## M6. Approval + Execution

**目标**：实现 proposal 审批与执行。

任务：

1. `POST /ingestion/approve`
2. `POST /ingestion/execute`
3. SQL validator
4. dry-run summary
5. transaction execution
6. `ingestion_executions`
7. receipt 生成

验收：

- proposal 审批后可执行
- receipt 返回正确
- 审计日志齐全
- 失败能正确回传

---

## M7. 前端完整体验

**目标**：聊天 UI 完整支持 ingestion lifecycle。

任务：

1. 上传后状态机
2. setup 卡片
3. proposal 卡片
4. receipt 卡片
5. Workspace 绑定展示
6. 错误态展示

验收：

- 用户可在一个聊天窗口内完整走通
- 视觉反馈清晰
- 出错态可理解

---

## M8. 测试、迁移与灰度

**目标**：保证新旧链路共存、可回退、可验证。

任务：

1. 单元测试
2. 集成测试
3. e2e 测试
4. legacy 对比测试
5. 灰度开关
6. 文档补充

验收：

- 新链路通过 smoke flow
- 旧链路可继续工作
- 可按 flag 开关切换

---

## 16. 测试策略

## 16.1 单元测试

覆盖：

- catalog service
- upload inspection
- SQL validator
- dry-run generator
- proposal persistence
- workspace permission checks

## 16.2 集成测试

覆盖：

1. 创建 Workspace
2. 上传 Excel
3. 首次 setup
4. 生成 proposal
5. 用户审批
6. 执行写入
7. receipt 查询

## 16.3 E2E

真实前端流程：

- 登录
- 建 Workspace
- 上传花名册
- 完成 setup
- 选择“更新现有表”
- 成功执行

---

## 17. 验收标准

以下全部满足才视为完成：

1. 用户无 Workspace 时必须先创建 Workspace。
2. 上传 Excel 后不会直接静默入库，而是先生成 proposal。
3. proposal 由 Write Ingestion Agent 产出，且为 structured output。
4. 前端审批卡片可以固定展示 4 类动作。
5. setup flow 可在缺少 catalog 时触发。
6. catalog 为 Workspace 级持久化。
7. 执行前必须有 validator 和 dry-run。
8. 执行后必须返回 receipt。
9. Query Agent 与 Write Agent 路由清晰分离。
10. legacy upload 仍可在 feature flag 下保留。

---

## 18. 风险与控制

### 风险 1：Agent 误判目标表

控制：

- catalog 约束
- fixed approval actions
- target table 必须可解释展示给用户

### 风险 2：任意写 SQL 过于危险

控制：

- validator
- dry-run
- proposal binding
- workspace scope guard

### 风险 3：setup 流程太长，影响首用体验

控制：

- 限制 3~5 个关键问题
- 优先给猜测结果，减少用户输入

### 风险 4：前端状态机复杂

控制：

- 把 lifecycle 显式建模为 job status
- UI 卡片与状态一一对应

### 风险 5：新旧链路冲突

控制：

- feature flag
- API 分离
- 灰度切换

---

## 19. 推荐实现顺序

Coding Agent 必须严格按以下顺序推进，不要一口气并行全部实现：

1. M0：骨架
2. M1：Workspace
3. M2：Catalog
4. M3：Upload Inspection
5. M4：Write Agent
6. M5：Setup Flow
7. M6：Approval + Execution
8. M7：前端整合
9. M8：测试与灰度

---

## 20. 对 Coding Agent 的执行要求

1. **不要跳 Milestone**。
2. 每完成一个 Milestone，输出：
    - 修改文件清单
    - 新增 API
    - 数据表变更
    - 测试结果
    - 下一步计划
3. 任何涉及写 SQL 的执行逻辑，必须先落 validator 和 dry-run，再做 execute。
4. 不要删除 legacy upload 链路，除非明确要求。
5. Write Agent 与 Query Agent 必须物理隔离，至少：
    - 不同 runtime
    - 不同 prompt
    - 不同 tools
6. 所有 proposal、approval、execution 都必须可持久化和可审计。
7. 前端审批 UI 必须是固定动作，不使用自由文本确认。
8. SDK 的 `AskUserQuestion` 仅可用于内部调试或极少数澄清，不作为正式产品审批机制。

---

## 21. 第一阶段默认实现约束

为避免范围失控，V1 默认采用以下约束：

- 仅支持 `.xlsx`
- 仅支持单 Workspace 内写入
- 仅支持单目标表 proposal
- 单次 proposal 只允许一个主动作
- setup flow 最多 5 个问题
- 不做跨表级联写入
- 不做自动回滚 UI
- 不做复杂版本管理

---

## 22. 结论

本 SPEC 的核心不是“把上传 Excel 改成让 LLM 更聪明”，而是把 SmartHRBI 的写入能力升级为：

**Workspace 级治理 + Agent 规划 + 前端审批 + 后端确定性执行**

这条链路与当前 Query Agent 的架构方向一致，但职责分离更清晰，也更适合企业产品落地。

如果你愿意，我下一步可以继续把这份 SPEC 再细化成 **给 Coding Agent 的分阶段 Prompt 模板**，按 M0、M1、M2… 一步一步发。

---

## 23. TODO List（CheckList 进度跟踪）

> 使用说明：
> 1. 每次开始 Milestone 前，将 `Status` 改为 `IN_PROGRESS`，并更新 `Start Date`。
> 2. 每完成一项 CheckList，将 `CheckList` 列中的 `[ ]` 改为 `[x]`。
> 3. Milestone 全部完成后，将 `Status` 改为 `DONE`，补全 `Done Date` 与 `Evidence/Links`。
> 4. 若受阻，将 `Status` 改为 `BLOCKED`，在 `Blockers` 记录具体阻塞信息和下一步动作。
>
> 状态建议：`TODO` / `IN_PROGRESS` / `BLOCKED` / `DONE`

| Milestone | Status | Owner | Start Date | Done Date | CheckList | Blockers | Evidence/Links |
|---|---|---|---|---|---|---|---|
| M0 方案落地与骨架搭建 | DONE | Codex | 2026-04-17 | 2026-04-17 | [x] ADR 完成并落盘；<br>[x] 模块目录骨架完成；<br>[x] migration/schema 初版完成；<br>[x] feature flags 生效验证 |  | `docs/adr/0003-workspace-scoped-agentic-ingestion.md`;<br>`apps/api/agentic_ingestion/*`;<br>`apps/api/migrations/0003_workspace_agentic_ingestion_init.sql`;<br>`tests/api/test_ingestion_feature_flags.py`;<br>`tests/unit/test_agentic_ingestion_schema.py` |
| M1 Workspace 最小模型 | DONE | Codex | 2026-04-17 | 2026-04-17 | [x] users/workspaces/workspace_members 建表；<br>[x] 登录后无 Workspace 引导创建；<br>[x] 聊天页绑定当前 Workspace；<br>[x] Workspace 鉴权校验通过 |  | `apps/api/workspaces.py`;<br>`apps/api/main.py`;<br>`apps/api/auth.py`;<br>`apps/api/chat.py`;<br>`apps/web/components/shared/workspace-onboarding-gate.tsx`;<br>`apps/web/components/shared/app-shell.tsx`;<br>`apps/web/components/chat/chat-panel.tsx`;<br>`apps/web/hooks/use-chat.ts`;<br>`tests/api/test_workspaces_api.py` |
| M2 Table Catalog 能力 | DONE | Codex | 2026-04-17 | 2026-04-17 | [x] table_catalog 建表；<br>[x] Catalog CRUD API 完成；<br>[x] catalog service 能按 business_type 命中 active target；<br>[x] 前端最小可见 |  | `apps/api/table_catalog.py`;<br>`apps/api/main.py`;<br>`tests/api/test_table_catalog_api.py`;<br>`apps/web/components/workspace/workspace-catalog-readonly.tsx`;<br>`apps/web/components/workspace/workspace-panel.tsx`;<br>`apps/web/hooks/use-workspace.ts`;<br>`apps/web/lib/workspace/api.ts`;<br>`apps/web/types/workspace.ts`;<br>`apps/web/tests/ui/workspace-catalog-readonly.test.tsx` |
| M3 Upload Inspection 新链路 | DONE | Codex | 2026-04-17 | 2026-04-17 | [x] `/ingestion/uploads` 完成；<br>[x] 原始文件落盘；<br>[x] sheet/column/sample/hash 提取；<br>[x] ingestion_uploads/ingestion_jobs 持久化 |  | `apps/api/agentic_ingestion/uploads.py`;<br>`apps/api/agentic_ingestion/router.py`;<br>`apps/api/agentic_ingestion/runtime.py`;<br>`tests/api/test_ingestion_uploads_api.py`;<br>`tests/api/test_ingestion_feature_flags.py` |
| M4 Write Ingestion Agent Runtime | DONE | Codex | 2026-04-17 | 2026-04-17 | [x] WriteIngestionAgentRuntime 完成；<br>[x] tools 挂载完成；<br>[x] structured output schema 完成；<br>[x] proposal 持久化；<br>[x] Query/Write 分流稳定 |  | `apps/api/agentic_ingestion/runtime.py`;<br>`apps/api/agentic_ingestion/routing.py`;<br>`apps/api/agentic_ingestion/models.py`;<br>`apps/api/agentic_ingestion/router.py`;<br>`tests/api/test_ingestion_plan_api.py`;<br>`tests/unit/test_ingestion_routing.py`;<br>`tests/api/test_ingestion_feature_flags.py` |
| M5 Setup Flow | DONE | Codex | 2026-04-17 | 2026-04-17 | [x] setup trigger 完成；<br>[x] setup schema 完成；<br>[x] setup 卡片 UI 完成；<br>[x] setup confirm API 完成；<br>[x] catalog entry 自动生效 |  | `apps/api/agentic_ingestion/models.py`;<br>`apps/api/agentic_ingestion/runtime.py`;<br>`apps/api/agentic_ingestion/router.py`;<br>`tests/api/test_ingestion_setup_api.py`;<br>`tests/api/test_ingestion_plan_api.py`;<br>`apps/web/components/workspace/ingestion-setup-card.tsx`;<br>`apps/web/components/workspace/workspace-catalog-readonly.tsx`;<br>`apps/web/hooks/use-workspace.ts`;<br>`apps/web/lib/workspace/api.ts`;<br>`apps/web/types/ingestion.ts`;<br>`apps/web/tests/ui/ingestion-setup-card.test.tsx` |
| M6 Approval + Execution | DONE | Codex | 2026-04-17 | 2026-04-17 | [x] `/ingestion/approve` 完成；<br>[x] `/ingestion/execute` 完成；<br>[x] SQL validator 完成；<br>[x] dry-run summary 可用；<br>[x] execution+receipt 持久化 |  | `apps/api/agentic_ingestion/models.py`;<br>`apps/api/agentic_ingestion/router.py`;<br>`apps/api/agentic_ingestion/runtime.py`;<br>`tests/unit/test_ingestion_execution_runtime.py`;<br>`tests/api/test_ingestion_execution_api.py`;<br>`tests/api/test_ingestion_feature_flags.py` |
| M7 前端完整体验 | DONE | Codex | 2026-04-17 | 2026-04-17 | [x] 上传后状态机完成；<br>[x] setup/proposal/receipt 卡片全链路完成；<br>[x] Workspace 绑定展示完成；<br>[x] 错误态可解释 |  | `apps/web/components/chat/ingestion-lifecycle-panel.tsx`;<br>`apps/web/components/chat/chat-panel.tsx`;<br>`apps/web/lib/ingestion/api.ts`;<br>`apps/web/types/ingestion.ts`;<br>`apps/web/tests/ui/ingestion-lifecycle-panel.test.tsx`;<br>`apps/web/tests/ui/chat-panel-workspace-binding.test.tsx` |
| M8 测试、迁移与灰度 | TODO | TBA |  |  | [ ] 单元/集成/e2e 完成；<br>[ ] legacy 对比测试完成；<br>[ ] 灰度开关验证通过；<br>[ ] 文档与运行手册补齐 |  |  |

### 23.1 当前迭代执行记录（可选）

| Date | Operator (Human/Agent) | Scope | Result | Notes |
|---|---|---|---|---|
| 2026-04-17 | Agent | M0 | DONE | ADR、骨架模块、初版 schema/migration、feature flag 测试已完成 |
| 2026-04-17 | Agent | M1 | DONE | Workspace API/成员鉴权、聊天 workspace 绑定校验、前端无 workspace 引导创建已完成；`tests/api` 与 `tests/security` 通过 |
| 2026-04-17 | Agent | M2 | DONE | Workspace 级 table catalog CRUD、active target 命中、Workspace 角色校验、前端 catalog 只读视图与对应测试已完成 |
| 2026-04-17 | Agent | M3 | DONE | `POST /ingestion/uploads` 已完成，支持 `.xlsx` inspection、原始文件落盘、sheet/column/sample/hash 提取与 `ingestion_uploads/ingestion_jobs` 持久化；新增 M3 API 测试并通过 |
| 2026-04-17 | Agent | M4 | DONE | `POST /ingestion/plan` 与 `WriteIngestionAgentRuntime` 已完成；实现 workspace catalog/upload/existing table 工具链、structured proposal 输出、proposal 持久化、ingestion event tool trace 记录、Query/Write 路由判定；新增 M4 API/路由单测并通过 |
| 2026-04-17 | Agent | M5 | DONE | 新增 `POST /ingestion/setup/confirm`、setup schema、catalog upsert 自动生效并在确认后自动进入 proposal；前端新增 setup 卡片 UI 与 mock setup 提交链路；M5 API/UI 测试通过 |
| 2026-04-17 | Agent | M6 | DONE | 新增 `POST /ingestion/approve` 与 `POST /ingestion/execute`，实现 approval 绑定、SQL write validator、dry-run summary、DuckDB 事务执行、`ingestion_executions` + receipt 持久化；新增 M6 API/单测并通过，且 M3-M5 回归通过 |
| 2026-04-17 | Agent | M7 | DONE | 前端聊天窗口新增 ingestion lifecycle 面板，支持 upload→plan→setup→proposal→approve→execute→receipt 全链路；补齐 Workspace 绑定与可解释错误态；新增 M7 UI 测试并通过 |
