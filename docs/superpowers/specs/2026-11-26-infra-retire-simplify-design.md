# 四次简化 · 基础设施退役设计文档

> 日期：2026-11-25 立项，次日（2026-11-26）执行。
> 前置：三轮瘦身已完成（深判退役等，HEAD=d10d2f5，已推送 origin/main）。
> 本轮目标：backend 只剩「采集 → 筛选 → 报告」一条直线，拔掉最后的平台时代基础设施。

## Intent（为什么）

三轮功能瘦身（二次瘦身/三次简化）后，运行链路已收敛为 compose → 确定性初筛+fact_checks → 三段报告 → latest-report，单轮 ≤2 分钟。但**基础设施层**还残留多任务时代的机制：持久任务队列（task_manager）、事件查询/清理 API、DI 容器闲置 getter。它们的维护成本（状态机、stale 收尾、reset_stuck_runs 擦屁股脚本）已远超单用户本地串行场景所需。

## 用户决策记录

- 2026-11-25：用户批准「task_manager 退役」与「event 查询/清理 API 删除」两项立项，其余（DI getter 清理、BacktestRun 历史读取、前端 CommandPalette）为待定项，见下「待定项」。

## Goals / Non-goals / Anti-goals

- **Goals**：定时选股不再经 task_manager 落库排队，直接后台执行；删除事件查询/清理 API（event_log 写入保留）；文档同步。
- **Non-goals**：不动 event_log 写入本身（AGENTS.md：write-once 审计表）；不动 market/document/knowledge；不做新功能。
- **Anti-goals**：不丢调度可靠性——定时选股失败仍要有 logger.error + run 行 failed 状态可查；不删 `screener_runs` 表（它是运行状态的唯一事实源）。

## Task A：task_manager 退役（最大项）

**现状**：`core/task_manager.py`（12.3KB，PG 持久任务表+handler 注册+重试+stale 收尾）；消费方仅 3 处——`screener/service.py`（trigger_run 落任务）、`core/screener_schedule.py`（定时触发经任务）、`core/scheduler_routes.py`（手动触发调度任务）。回测 handler 已随三轮瘦身消失。

**方案**：
1. `trigger_run` 改为：创建 `ScreenerRun` 行（status=pending）后直接 `asyncio.create_task(run_screener(db, run_id))`（或经 `asyncio.get_running_loop().run_in_executor`——实现者按现有 concurrency 模式选择，**必须保证 uvicorn 单 worker 下不丢运行**）。
2. `screener_schedule` 定时路径同样直跑，去掉任务落库。
3. 删 `core/task_manager.py`；`scheduler_routes.py` 的 `POST /scheduler/run/{name}` 改为直接触发对应协程（保留端点形状，响应语义不变）；`GET /scheduler/status` 删任务队列字段。
4. 删 `core/scheduler.py` 中 task_manager 相关 job 注册（保留 market_sync/financial_sync/screener_schedule 三个业务 job）。
5. 删 `backend/tools/reset_stuck_runs.py`（任务队列没了，stuck 概念消失；run 行卡住时手工 UPDATE 即可）。
6. **DB**：任务表（`core.tasks` 若存在）保留不迁移，ORM 类删除（与既定「删类留表」模式一致）。
7. 测试：删任务队列相关用例；新增「trigger_run 后 run 行存在且最终 completed」的直跑用例（mock 外部依赖）；调度失败路径用例保持（logger.error 断言已有）。

## Task B：事件查询/清理 API 删除

**现状**：`core/event_service.py`（4.7KB 查询/聚合）+ `core/event_routes.py`（2.6KB API）+ `core/event_cleanup.py`（1KB 清理 job）。写入方 `core/event_log.py` 保留。
**前置勘察**：确认 `frontend/src/views/System.vue` 及 `stores/api.ts` 是否消费事件查询 API——若消费，前端同步删对应展示块（本轮允许动前端，Task 4 先例）。
**方案**：删 3 个文件 + app.py 路由注册 + scheduler 中 cleanup job 注册 + 对应测试；`System.vue` 若有事件面板一并删。
**保留**：`event_log.py` 的 `log_event()` 写入函数与 `core.event_log` 表（screener.triggered/completed/failed 继续写）。

## 待定项（执行前需用户确认，或勘察后自决）

1. **DI 容器闲置 getter**：逐个 grep `profile_service/news_service/search_service/freshness_service` 等的前端/API 消费链，删确认无消费方的 getter + 对应 protocol（勘察后自决，有消费方的保留）。
2. **`ScreenerBacktestRun` 历史读取**：写入方已死（脚本直调不落库），仅剩历史行。问用户：历史回测结果还需要从 API/UI 看吗？不需要则连读取端点（若存在）一起删；需要则全留。
3. **CommandPalette 收缩**：5.9KB 对 6 页面偏重，砍到纯路由跳转。低优先，用户表态后做。

## Constraints

- 不做 alembic 迁移、不 drop 表；ORM 类删除仅限任务表（若有）
- ruff 只跑改动文件；禁止全仓 format
- 后端测试从 `backend/` 用 `.venv\Scripts\python -m pytest`；**测试与冒烟严格串行，pytest 跑完后才许起 uvicorn 冒烟**（三次简化 Task 5 教训：并发互踩 dev 库）
- 冒烟前先核对 dev 库 alembic 是否在 head（教训：曾落后 5 个迁移）
- 零新增 LLM/akshare 真实调用
- 提交切分建议：Task A 一个提交、Task B 一个提交、待定项各自或合并、文档同步收尾
- 提交信息先过目控制者，不自行 commit；不推送（推送等用户指示）

## 验收标准

1. grep `task_manager|TaskManager` 在 backend/ 零命中；`reset_stuck_runs` 零命中
2. `GET /scheduler/status` 响应无任务队列字段；定时选股照常触发且失败仅记日志
3. 事件写入继续（`screener.completed` 事件在新运行后出现），事件查询 API 404/已删
4. 全量 pytest：除既有豁免清单外全绿（豁免清单见 `memory/ai-research-os-session.md` 最新条目）
5. 冒烟：POST /runs 单轮 completed ≤2 分钟；定时任务卡（System.vue）渲染正常
6. 整分支评审（MERGE_BASE=d10d2f5）通过

## 明日恢复入口

1. 读本文档 + `git log --oneline -8`（HEAD 应为 d10d2f5，工作树干净）
2. 用户确认待定项 1-3 的取舍
3. SDD 流程照旧：写实施计划（writing-plans）→ subagent-driven 执行 → 每提交过目 → 整分支评审
