# 项目进度快照 — 2026-11-24 二次瘦身执行中（8/11 完成）

> 本文件由 SDD 控制器维护，供下次会话恢复。详细账本：`.superpowers/sdd/2026-11-24-slim-to-value-recommendation/progress.md`
> 当前 HEAD：`b46fa32`（main，未推送；BASE=07ff9b7）
> 最后更新：2026-11-24 深夜收工

## 正在进行的项目

**价值推荐聚焦 · 二次瘦身**（设计文档 + 11 任务实施计划均已完成并批准）
- 目标：系统收敛为「每日自动产出 Markdown 价值推荐清单（股票+理由）」
- 设计：`docs/superpowers/specs/2026-11-24-slim-to-value-recommendation-design.md`
- 计划：`docs/superpowers/plans/2026-11-24-slim-to-value-recommendation.md`

## 任务进度

| 任务 | 状态 | 提交 |
|---|---|---|
| 1 删组合/再平衡 | ✅ 完成+评审通过 | b0a2bed |
| 2 删表现跟踪/快照 | ✅ 完成+评审通过（修一轮：config 重复行） | 4802b97 |
| 3 回测降级脚本 | ✅ 完成+评审通过 | 0afd307 |
| 4 删 freeform 模式 | ✅ 完成+评审通过（顺带修复 HEAD 上 union 运行 ImportError） | d756dff |
| 5 删运行取消机制 | ✅ 完成+评审通过（含 Task3 遗留：fail_stale_backtest_runs 测试+类改名） | f75f6e4 |
| 6 删近似命中 | ✅ 完成+评审通过（顺带补 union 全链路测试） | bc2b806 |
| 7 预设只读化+compose 拆分 | ✅ 完成+评审通过 | b46fa32 |
| 8 事实检查确定性化 fact_checks.py | ⏳ 剩余（与 9 合并 dispatch，最重） | |
| 9 报告改投资理由文档+latest-report | ⏳ 剩余（与 8 合并） | |
| 10 前端收缩 | ✅ 完成+评审通过（Screener.vue 464 行，build 绿） | 210946a |
| 11 文档同步+全量验证 | ⏳ 剩余 | |
| 最终整分支评审 | ⏳ 剩余（MERGE_BASE=07ff9b7） | |

## 剩余任务清单（预计 2.5~3 小时）

### Task 8 + 9（合并 dispatch，~85 分）
- **Task 8 事实检查确定性化**（核心新功能）：
  - 新建 `backend/screener/fact_checks.py`：三检查器——审计意见（KB 检索+关键词）、诉讼/处罚（KB 检索命中即 fail）、现金覆盖（财务指标计算）
  - `run_fact_checks(checks, knowledge, company_id, financials) -> list[dict]`，每项 `{check, result: pass|fail|not_found, evidence, citation, detail}`
  - judge.py 接线：LLM 调用前执行；任一 fail→reject、任一 not_found→insufficient（优先级 reject > insufficient > LLM 结论）；LLM 只收叙事标准
  - seeds.py：深度价值/金融价值 qualitative 改写为结构化 fact_check 条目（注意：preset.qualitative JSON 列现在存 dict，消费端须容忍）
  - `scripts/reseed_builtin_presets.py` 幂等重灌 + `test_fact_checks.py` 测试先行（6 个用例）
- **Task 9 报告改造**：
  - report.py 推荐股四段结构：量化筛选（数值+行业分位）→ 事实检查 → 年报证据 → 不推荐/存疑原因
  - `GET /api/v1/screener/latest-report` 路由（前端 `useScreenerLatestReport` 钩子已就位，404 优雅降级已做）
  - 落地后验证前后端联动

### Task 11（~30 分）
- README×4 + `memory/ai-research-os-session.md` + `tools/README.md`（archive 失配）+ `frontend/README.md`（knowledge 路由失配）更新
- 全量 pytest + `npm run build` + 改动文件 ruff/pre-commit

### 最终整分支评审（~20 分）
- 对 07ff9b7..HEAD 全量 diff 整体审查 → finishing-a-development-branch

## 恢复要点

1. **恢复入口**：读 `.superpowers/sdd/2026-11-24-slim-to-value-recommendation/progress.md`（SDD 账本，含完整遗留项与裁定记录）+ `git log --oneline -10`（HEAD 应为 b46fa32，工作树应干净）
2. **执行方式**：subagent-driven-development 流程照旧（task-brief 脚本 → 派实现者 → review-package → 派评审员）；脚本路径与裁定记录详见账本「停机摘要」节
3. **用户已批准的节奏**：8+9 合并一个 dispatch（一个实现者、两个提交）；纯删除任务评审可抽查
4. **完成后**：最终整分支评审（MERGE_BASE=07ff9b7）→ finishing-a-development-branch

## 既有测试失败（勿归咎新任务）
- `test_screener_backtest_pit.py::test_announcement_date_filters_future_data`
- `test_presets_union_with_financials`（日期依赖）
- `test_screener_judge.py::test_snippet_hit_with_citation_kept`（'SnippetKnowledge' 无 session 属性）

## 后续立项候选（用户已表态）
- LLM 调用优化：结果缓存 + top N 截断（不动逐条检索）
- 测试提速：service 级测试替代 TestClient + 单语句 TRUNCATE
