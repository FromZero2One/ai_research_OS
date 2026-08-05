---
name: ai-research-os-session
description: AI Research OS 进度快照 — 完成度、已知限制、下一步、机器环境
metadata:
  type: project
---

# AI Research OS — 进度快照

## 位置
`/home/wsm/codes/ai_research_OS/`

## 变更日志
- **2026-08-05**: 修 K 线刷新不更新 — 根因是 akshare MySQL 镜像(`stock_zh_a_hist`)停更，而 `fetch_akshare` Layer 1 不查新鲜度直接返回旧数据。修复：`config.py` 加 `PRICE_STALE_DAYS=5`；`price_service.py` Layer 1 超过阈值自动落到 Layer 2 实时子进程；Makefile 加 `make refresh-market`(跑 akshare_mcp 管道增量 + curl ingest 同步 PG)。另发现 `useIngestProfile` invalidate key 写 `['companies']`，详情页用 `['company', id]`，刷新后公司资料不刷新。
- **2026-08-04**: 目录与模块清理 — 删 `scripts/`、顶层 `data/`、`docs/`；删死代码 `security.py`/`aggregate.py`/`news_fetcher.py`/`mcp_company/`(外部 MCP 实际走 akshare_executor + newsnow_mcp)；`crud.py` → `market/`；新增 `backend/README.md`/`frontend/README.md`(经代码核对)，USAGE 瘦身，前端删死 `lint` script。测试 125 passed。
- **2026-08-01**: 文档与代码对齐，前端 Vue 3 完成度约 80%。

## 完成度（按模块）

| 模块 | 完成度 | 现状 |
|------|:---:|------|
| 公司中心 | ~90% | CRUD/搜索/标签/Thesis/工作区/自选全可用 |
| 市场中心 | ~75% | A股行情/财务/估值可用；美股为合成数据占位（yfinance 受代理限制） |
| 文档中心 | ~90% | 上传→后台索引→表格结构化→关联公司全链路；OCR 明确 V1 不做 |
| 知识中心 | ~90% | 混合 RAG + Reranker + 中文检索优化 + 文档问答（模型切换）+ 评估集 |
| AI 中心 | ~80% | 模板/摘要后端全；工作流前端 UI 未做 |
| 研究中心 | ~90% | 会话/计划/证据/报告/决策/时间线/一键研究全链路 |
| 投资组合 | ~40% | 自选已并入公司；持仓/日志仅后端，前端待 V2 |
| 系统/调度 | ~85% | 调度/观察/任务/事件/新鲜度可用；newsnow 依赖外部路径 |

总体：V1.1 目标基本达成，V2 未启动，单用户本地工具（无认证）。

## 未完成清单（代码驱动，2026-08-04 更新）
> 每项均含代码证据；上方"完成度"表为估算，本清单为准。

**A. 前端缺口（后端就绪）**
1. **持仓/日志前端半成品** — 后端 `portfolio/routes.py:25-86` 端点就绪；前端 hook `api.ts:347/349`(useHoldings/useAddHolding) 已定义但 **0 视图消费**，journal 无 hook；`Portfolio.vue` 只渲染自选
2. **AI 工作流前端空白** — 后端 `ai/routes.py:93-109` 就绪；前端 grep `/ai/workflow` 全 src 0 命中；且后端仅顺序执行(V1)，LangGraph DAG 待 V2

**B. 功能降级/受限**
3. **美股行情** — `price_service.py:283` yfinance 仅为 fallback；`seed_market_data.py` 种子是合成数据；`ingest_real_data.py` 有真实抓取但仅手工跑
4. **Embedding 失败→零向量** — `core/adapters/embedding.py:91-93` 失败返回零向量，稠密检索靠 BM25+RRF 兜底
5. **OCR 不支持** — `document/service.py:325` "(OCR not supported in V1)"

**C. 半成品代码（定义未用）**
6. **5 个前端 hook 零消费** — `useHoldings`/`useAddHolding`/`useCompanyThesis`/`useReportDiff`/`useGet`（均定义于 `stores/api.ts`，无视图 import）

## 下一步优先级（按代码缺口排序）
1. **持仓/日志前端接通** — hook 已写好，只差视图接入（工作量最小）
2. **AI 工作流前端** — 后端就绪，需补列表/执行 UI
3. **美股行情** — 解决 yfinance 通道/代理；或确认合成数据是否够用

## 环境要点
- 本机代理 `socks://127.0.0.1:7890`：后端启动时 `clean_proxy_env()` 清理，脚本需自行调用；HuggingFace 下载走 `HF_ENDPOINT=https://hf-mirror.com`
- akshare 走独立 `akshare_mcp` venv 子进程（ticker 经环境变量传递）；云端 MCP 层默认禁用（`AKSHARE_CLOUD_MCP_URL` 留空）
- 外部数据源路径均可在 `backend/.env` 覆盖（AKSHARE_MCP_DIR / NEWSNOW_MCP_SERVER_PATH / AKSHARE_MYSQL_*）

## 相关文档
- **启动命令** → [`USAGE.md`](../USAGE.md)「服务启动与停止」
- **关键设计决策** → [`README.md`](../README.md)「Key Design Decisions」
