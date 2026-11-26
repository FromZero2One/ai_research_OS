# 七次简化执行计划（infra 退役 + 死链清理）

> 依据：`docs/superpowers/specs/2026-11-26-infra-deadlink-cleanup-design.md`。
> 顺序：S1(1)→S1(2)→S1(3)→S2(1)→S2(2)→S2(3+4)→S3→S4→文档同步+全量回归+评审。每步独立提交，提交信息先过目。

## Task S1.1 task_manager 退役

- 勘察：`grep task_manager` → screener/routes/runs.py、document/tasks.py、scheduler_routes.py、api/app.py
- 改造：POST /screener/runs 直接 `asyncio.create_task(run_screener(...))`（参考 screener_schedule._run_one 模式）；删 task handler 注册与 `document/tasks.py`、`core/task_manager.py`
- DB：`core.task_records` 删类留表；任务状态查询端点（若有）同步删
- 测试：test 涉及 task 队列的用例改直调或删
- **Expected**：`git grep task_manager` 仅剩历史迁移；POST runs 仍 409 幂等（DB 唯一索引兜底）

## Task S1.2 事件查询/清理 API 删除

- 删 `core/event_routes.py`、`core/event_cleanup.py`、app 注册、scheduler_routes 中 event 相关端点
- 保留：`EventLogger` 写入、`core.event_log` 表
- **Expected**：app import OK；pytest 事件相关用例删/改

## Task S1.3 DI 闲置 getter 清理

- grep container 每个 getter 的调用方；删零调用 getter + 对应 Protocol
- **Expected**：app import OK；container 缩小

## Task S2.1 估值分位死链

- 删 `useValuationPercentile`、ratio_service valuation 分位方法、对应路由；表保留
- **Expected**：npm build 绿；pytest market 相关全绿

## Task S2.2 profile 链裁定

- 逐端点查消费方（前端 hook / 后端内部调用）；无消费即删
- Company 写入来源核实：profile ingest 之外是否还有写入（market_sync 等）
- **Expected**：删后 Company 表数据来源不受影响（screener 数据质量统计仍可跑）

## Task S2.3 company_tags 空壳 + openapi.json

- 删 CompanyTag ORM/schema/relationship、CompanyResponse.tags；前端接口同步
- 删 frontend/openapi.json
- **Expected**：app import OK；npm build 绿

## Task S3 根目录脚本归档

- 移 `*.py`（根目录一次性脚本）→ backend/tools/archive/；README 引用先查
- **Expected**：根目录仅剩项目级文件（README/USAGE/AGENTS.md 等）

## Task S4 运行时稳固

- 启动脚本加 SelectorEventLoop 显式策略
- document/knowledge 4 个 Ollama 环境失败用例 monkeypatch embedding 假向量
- **Expected**：全量 pytest 失败 ≤3（仅日期依赖类）

## Task F 文档同步 + 全量回归 + 整分支评审

- README×3/USAGE/ARCHITECTURE/memory 同步；全量 pytest；code-reviewer 评审；提交信息过目
