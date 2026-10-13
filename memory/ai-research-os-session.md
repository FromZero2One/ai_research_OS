---
name: ai-research-os-session
description: AI Research OS 进度快照 — 完成度、已知限制、下一步、机器环境
metadata:
  type: project
---

# AI Research OS — 进度快照

## 位置
`E:\Project\ai_research_OS\`（Windows；旧机器路径 /home/wsm/codes/... 已废弃）

## 变更日志
- **2026-10-13**: 分析师优化方案（先砍后补）。**砍**: AI 工作流（drop ai_workflows 表，0d04258）、akshare MySQL 镜像层（A股改 akshare 子进程直连，bac6cf3）、合成数据种子脚本（10e324b）。**补**: 数据覆盖矩阵（ae90779 + 单测 c3ef444）。另: 迁移补齐 morning_briefs/observations（8208cea）、LLM 切 DeepSeek 云端并完成分类评测（deepseek-chat 15/15=100% vs 关键词基线 26.7%）、plan_type 贯通快速研究（67a138f）、token 用量统计、period_compare（YoY/QoQ/同业中位）、ReportCharts 可视化、start-dev.cmd 一键启动、三份文档架构同步（5894dda）。全套测试 132 passed / 5 failed（失败均为无 Ollama embeddings 的环境依赖）。
- **2026-08-05**: 修 K 线刷新不更新（PRICE_STALE_DAYS 陈旧镜像问题，该问题已随 MySQL 层移除而消失）。
- **2026-08-04**: 目录与模块清理，测试 125 passed。

## 完成度（按模块）

| 模块 | 完成度 | 现状 |
|------|:---:|------|
| 公司中心 | ~90% | CRUD/搜索/标签/Thesis/自选全可用；搜索范围为自建公司库（PG） |
| 市场中心 | ~85% | A股行情/财务/估值 akshare 直连全链路 + 数据覆盖矩阵；美股 yfinance 备选 |
| 文档中心 | ~90% | 上传→后台索引→表格结构化→关联公司全链路；OCR 明确 V1 不做 |
| 知识中心 | ~90% | 混合 RAG + Reranker + 中文检索优化 + 文档问答 + 评估集 |
| AI 中心 | ~75% | 模板/摘要/提取/Token 用量统计；AI 工作流已移除（单用户用不上） |
| 研究中心 | ~92% | 全链路 + plan_type 四模板 + LLM 证据分类 + 多周期/同业比对 + 报告可视化 |
| 投资组合 | ~40% | 自选已并入公司；持仓/日志仅后端，前端待做 |
| 系统/调度 | ~85% | 调度/观察/任务/事件/新鲜度/覆盖矩阵/Token 用量卡片 |

总体：V1.1 达成，V2 按分析师优先级推进中（见下）。

## 下一步优先级（2026-10-13 定稿，按此顺序继续）

1. **比率层 + 历史分位**（下一项，未开始）
   - 基于标准枚举指标（`market/models.py` FinancialMetricName + normalize_metric_name）计算派生比率：毛利率/净利率/ROE/资产负债率/周转率
   - PE/PB 历史分位：akshare `stock_a_indicator_lg` 已在用（profile_service 估值直连），历史序列入 PG 后算当前值所处分位
   - 产出：`market/ratio_service.py`（纯函数可单测）+ 研究报告上下文区块 + 前端展示
2. **报告引用回溯**（未开始）
   - 报告生成时把论断内联 evidence id（如 `[ev:abc123]`），前端渲染为可点击锚点回跳证据卡
   - 改动点：`research/report_service.py`（prompt 要求引用标注）+ `ResearchDetail.vue`（解析渲染）
3. **跨会话证据继承**（未开始）
   - 同公司新研究 session 自动带入历史已核实证据（structured_facts 非空的），标 `inherited` 来源
   - 改动点：`research/gather_service.py`（auto_gather 前查历史）+ Evidence 模型加来源标记
4. **差异日报**（未开始）
   - 晨报改造：只报变化（新公告/财报日临近/价格异动/证据与旧结论冲突），不做综合评分
   - 改动点：`core/brief_generator.py` + `core/observation_engine.py`

### 已完成（本轮，勿重做）
- ✅ 数据覆盖矩阵 — `GET /market/freshness/coverage` + Market 页卡片（缺口标 missing）

## 已明确放弃（勿再提议）
- multi-agent / trading agents / LangGraph DAG 工作流（单用户工具过度设计）
- akshare MySQL 中间层（子进程直连替代）
- 合成行情数据（研究工具宁缺毋假）

## 环境要点（本机 Windows）
- docker compose 栈：postgres/qdrant/redis（`docker/docker-compose.yml`）；一键启动 `start-dev.cmd`（依赖栈+后端:8000+前端:5173）
- LLM：DeepSeek 云端（.env OPENAI_* 已配，key 已 gitignore）；light tier 同走云端；本机无 ollama
- Embedding 仍指向本机 Ollama（未安装）→ 文档上传/知识检索的稠密向量不可用，BM25 兜底；pytest 有 5 项因此失败
- akshare 走独立 `akshare_mcp` venv 子进程（`AKSHARE_MCP_DIR` 指向旧机器路径，**本机需改 .env 并确认 venv 存在**，否则 A 股采集失败但不崩）
- 迁移 head：`c3d5e7a9b1f2`（含 drop ai_workflows）
- pytest 需先起 docker postgres；`tests/test_session` fixture 为服务级测试专用（勿用 managed_session，会写进开发库）

## 相关文档
- **启动命令** → [`USAGE.md`](../USAGE.md)「服务启动与停止」
- **架构与配置** → [`backend/README.md`](../backend/README.md)
- **下一步方案细节** → [`README.md`](../README.md)「Roadmap」
