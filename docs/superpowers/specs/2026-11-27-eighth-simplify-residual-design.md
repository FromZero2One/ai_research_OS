# 八次简化（评审漏网残留清理）设计

> 日期：2026-11-27。前置：七次简化 `2026-11-26-infra-deadlink-cleanup-design.md`（已完成并评审 Ready）。
> 用户诉求延续：「尽量简化系统，不要增加额外功能」——本轮全部为减法。

## Goals / Non-goals

- **Goals**：清理七次简化评审后勘察发现的死代码残留（event_routes 复活文件、shared_queries 零引用模块、ValuationRepository 孤儿类）；task_manager 退役的连带工具适配（reset_stuck_runs / index_pending_parallel 还在操作已死的 task_records 表）；tools/README 过时条目；SECRET_KEY 等配置残核查。
- **Non-goals**：不删任何 DB 表（删类留表约定不变）；不动 `/scheduler/run`（运维手动触发数据的唯一入口，保留）；不动 `valuation_history`/`task_records`/`research*`/`prompt_templates` 表本体。
- **Anti-goals**：新增任何端点/字段/配置。

## 任务分解

### Task E1：core 死代码残留（一个提交）
1. **删 `core/event_routes.py`**——S1.2 提交时该文件被意外保留（4 个只读端点全仓零 import），M1 删了 event_cleanup 但它漏网。删除前核实 `git ls-files` 在册、`git grep event_router` 零引用。
2. **删 `core/shared_queries.py`**——`load_watched_companies`（自选语义已随公司中心退役）、`latest_price_by_ticker` 全仓零调用方。
3. **删 `market/repositories.py` 的 `ValuationRepository`**——valuation_history 无喂数、比率层已删；ORM 类 `ValuationHistory` 与表保留。
4. **SECRET_KEY 核查**——`core/security.py` 已删；grep `SECRET_KEY`/`settings.SECRET_KEY` 消费方，零引用则连 config 字段一起删。

### Task E2：工具适配 + 文档（一个提交）
1. **`tools/reset_stuck_runs.py`**——删 `UPDATE core.task_records` 段（表已无写入方，空转），只留 screener_runs 复位；注释说明任务队列已退役。
2. **`tools/index_pending_parallel.py`**——删 `DELETE FROM core.task_records` 段（同上）。
3. **`tools/README.md`**——去 `reindex_pending_docs.py`（已删）条目；reset_stuck_runs 说明更新；轮次备注。

## 验收标准

- pytest 关键文件无新增失败；`git grep` 已删符号零引用（除文档历史记录）
- ruff 只跑改动文件；提交信息先过目
- 文档（tools/README）同步；memory 快照更新

## 明确不做（本轮裁定留档）

- `/scheduler/run/{job_name}` 保留：运维手动触发数据采集/选股的唯一入口
- `valuation_history`、`task_records`、`ai.prompt_templates`、`research*` 表：删类留表约定，DB 不动
