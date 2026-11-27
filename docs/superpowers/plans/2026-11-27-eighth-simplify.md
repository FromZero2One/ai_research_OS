# 八次简化执行计划（评审漏网残留清理）

> 依据：`docs/superpowers/specs/2026-11-27-eighth-simplify-residual-design.md`。
> 两个提交：E1 core 死代码 → E2 工具适配+文档。提交信息先过目。

## Task E1 core 死代码残留

- 核实并删 `core/event_routes.py`（零 import）
- 删 `core/shared_queries.py`（零调用方）
- 删 `ValuationRepository`（孤儿类；ORM/表保留）
- SECRET_KEY 消费方核查，零引用则删配置字段
- **Expected**：app import OK；pytest core/market 绿；git grep 零引用

## Task E2 工具适配 + 文档

- reset_stuck_runs.py 删 task_records 段
- index_pending_parallel.py 删 task_records 清理段
- tools/README.md 去 reindex_pending_docs 条目 + reset_stuck_runs 说明更新
- **Expected**：脚本语法 OK；文档一致
