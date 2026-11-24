# 项目瘦身设计：只留价值筛选核心链路

日期：2026-11-24
状态：已与用户确认边界

## 意图与背景

用户诉求：项目功能太多太杂，最终目的只有一个——**系统根据数据与年报筛选出具备价值投资的股票**。要求对非核心功能做**代码级删除**（不是隐藏）。

保留的核心链路（Screener 全链，项目内完成度最高、回测最优）：

```
market（行情+财务） → company（股票池） → document/knowledge（年报 RAG）
  → screener（量化初筛 + LLM 深判 + 报告 + 回测 + 定时推送）
```

## Goals

- 删除 4 个后端模块：`research/`、`portfolio/`、`ai/`、`dashboard/`
- 删除对应前端页面与 API 封装，首页从 Dashboard 改为 Screener
- 保留：定时筛选 + 变化日报/失败告警 Webhook（用户确认留，是自动化出口）
- 保留：8 个预设全留（种子数据，删之无益，且非价值类预设是回测对照组）
- 保留：数据库表与 Alembic 迁移历史（只删代码，不写 drop 迁移；数据可回捡）

## Non-goals / Anti-goals

- 不删数据库表、不做破坏性迁移
- 不重构保留模块的内部代码（除拆依赖所必需的最小改动）
- 不动 `core/` 的任务队列、调度、事件日志、观测引擎骨架（观测引擎只摘除 research 时效部分）

## 已确认的依赖拆解点（探明于 2026-11-24）

| 位置 | 现状 | 处理 |
|---|---|---|
| `screener/handoff.py` + routes 挂载 + `test_screener_handoff.py` | 送入研究中心 | 整体删除（含前端「送入研究」按钮） |
| `knowledge/service.py:550` 引 `ai.models.PromptTemplate` | 问答模型选择 | 改用 `core.adapters.llm` 配置默认 |
| `core/container.py` | 6 个 research + 2 个 portfolio + ai + dashboard provider | 删属性与 Protocol |
| `core/interfaces.py` | research 协议 + PromptTemplate 类型 | 删 |
| `core/shared_queries.py` | `latest_research_by_company` | 删 |
| `core/observation_engine.py` | 「距上次研究 N 天」阈值逻辑 | 摘除 research 段，保留价格/文档新鲜度观测 |
| `core/task_manager.py` | `quick_research` 任务类型 | 删 handler 与注册 |
| `company/service.py` | 会话/证据关联查询 | 摘除 research 段 |
| `api/app.py` / `alembic/env.py` / `seed_data.py` / `tools/*.py` | import 被删模块 | 清理 |
| 前端 `api.ts` / router / 视图 | research/portfolio/ai/dashboard 相关 | 删；`/` 重定向到 `/screener` |

## 前端保留页面

Screener（首页）、Market、Companies/CompanyDetail、Documents、Knowledge、System。删除 Dashboard、Research×4、Portfolio、AICenter。

## 测试处理

删除被删模块的测试（research/portfolio/ai/dashboard/handoff/fact_validator/period_compare 等）；其余测试不动。验证门槛：被删引用清零（grep）、后端全部保留文件可 import/编译、前端 `npm run build`（vue-tsc）通过。

## 已拍板的决策（2026-11-24 用户确认）

- **LLM Token 用量保留**：把 `/ai/usage` 端点迁到 core 路由（如 event_routes 或新 system 路由），System 页卡片继续可用
- **Thesis 保留手动版**：`/companies/by-ticker/{ticker}/thesis` 端点与前端 `useThesis` 保留，仅摘除「回退读 research session」逻辑
- System.vue / CompanyDetail.vue 中 research/dashboard 相关 UI 段落直接删除
- `CommandPalette.vue` 硬编码的 快速研究/研究中心/时间线/Dashboard/AI中心 入口删除
- `core/observation.py` 模型的 `days_since_research` 列保留（不做 drop 迁移），代码停写该字段
- `task_manager.py` 的 quick_research 仅是 docstring 示例，实际注册在 `research/quick.py`，随模块删除即可
- `core/event_routes.py` 仅 docstring 提及，不改
- screener 自身的 `portfolio.py`/`portfolio_store.py`（构建组合功能）与被删的 `backend/portfolio/` 无关，勿误删

## 留给实现者的裁量

- 观测引擎摘除粒度：只要不残留 research import，阈值常量与事件类型可一并清理
- 文档（README/USAGE/backend/README）本轮**不重写**，仅在完成后补一节「模块已裁剪」说明，避免文档工程吞掉主体工作
- DB 中 research/portfolio/ai 相关表保留原样（含 scheduler 里 dashboard 聚合任务直接删除注册）
