# 九次简化（第九轮死代码清理）设计

> 日期：2026-11-27。前置：八次简化 `2026-11-27-eighth-simplify-residual-design.md`（已完成，评审 Ready）。
> 延续「只减不增」。

## Goals

- 删 `screener/ingest.py` 的 `ingest_single_company`（全仓零调用方；其余 `ingest_marketwide_*` 均有消费方，保留）
- 删 backend/scripts 三个零引用脚本：`cleanup_vectors.py`、`reseed_builtin_presets.py`、`backfill_announcement_dates.py`
- 删 knowledge 只读路由（`GET /search`、`GET /search/document/{id}`）及注册——前端零调用（文档问答 UI 已随 research 模块删除），工具直调 service；knowledge service 与内部检索（screener 深判证据）保留
- 删前端 api.ts 死 hooks：`useList`/`useCreate`/`useDelete`/`useIngestFinancials`

## Non-goals

- 不动 knowledge service 本体（screener 证据检索在用）
- 不动 `ingest_industry_sina/sw`、`financial_sync`（已核实有消费方/文档在册）
- 不删任何 DB 表

## 验收

- git grep 已删符号零引用；app import OK；ruff 改动文件绿；pytest 关键文件无新增失败；`npm run build` 过
