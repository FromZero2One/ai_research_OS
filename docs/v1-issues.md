# AI Research OS — V1.0 Issue 完成状态

> 最后更新: 2026-07-20 | 状态: **V1 核心功能全部完成**

---

## Milestone 1：基础工程完善 ✅ 完成

### ISSUE-001：Alembic Migration ✅

- [x] `backend/alembic/env.py` 已导入所有 model
- [x] 初始迁移 `d199a3e17af8_init.py` 已生成
- [x] `alembic upgrade head` 可创建所有 16 张表
- [x] `make reset-db` 可一键重建

### ISSUE-002：测试体系 ✅

- [x] `test_core.py` — 异常类/健康检查/404
- [x] `test_company.py` — CRUD + 搜索
- [x] `test_market.py` — 行情查询
- [x] `test_document.py` — 上传 + 管道 (部分异步)
- [x] `test_knowledge.py` — 知识检索
- [x] `test_research.py` — 研究会话工作流
- [x] `test_ai.py` — Prompt 模板 CRUD
- [x] `test_portfolio.py` — 自选/持仓 CRUD
- [x] `test_pdf_parser.py` — PDF 解析 11 项测试

**结果**: 77 同步测试通过, 13 异步测试需要 bge-m3 模型下载

---

## Milestone 2：Document Pipeline ✅ 完成

### ISSUE-003：文档上传 API ✅

- [x] `POST /api/v1/documents/upload` 端点
- [x] 文件类型校验 + 大小限制
- [x] 存储到 `data/uploads/`
- [x] Document 记录写入数据库
- [x] 前端拖拽上传页面

### ISSUE-004：PDF 解析管道 ✅

- [x] `core/adapters/pdf_parser.py` (PyMuPDF)
- [x] 结构化文本 + 逐页元数据
- [x] Document Service 集成
- [x] 加密/扫描件/损坏文件错误处理

### ISSUE-005：切片 + Embedding 管道 ✅

- [x] `document/chunker.py` 分块
- [x] bge-m3 embedding
- [x] Qdrant upsert
- [x] 元数据 (文档 ID/页码/序号)

### ISSUE-006：RAG 检索 + 溯源 ✅

- [x] Hybrid search (dense + sparse + RRF)
- [x] BGE Reranker (cross-encoder)
- [x] 前端搜索页面 (类型过滤/得分条/展开)

---

## Milestone 3：Research 闭环 ✅ 完成

### ISSUE-007：Research Planner ✅

- [x] Research Plan 数据结构 (子问题/维度/数据需求)
- [x] LLM prompt 生成计划
- [x] 研究会话创建时可选自动触发
- [x] API: POST/GET `/sessions/{id}/plan`

### ISSUE-008：Evidence Collector ✅

- [x] 按子问题多维度搜索知识库
- [x] 对接 Market Data (价格/财务)
- [x] 证据分组 (支持/反对/中性)
- [x] 来源元数据 + 去重

### ISSUE-009：AI 报告生成 ✅

- [x] LLM 分析 prompt (综合证据形成判断)
- [x] 结构化报告 (执行摘要/关键发现/风险/结论)
- [x] 多版本支持 (draft → review → final)
- [x] 持久化到 ResearchReport

### ISSUE-010：研究回溯 ✅

- [x] 状态机 draft→researching→reviewing→completed→archived
- [x] Event Log 记录
- [x] 历史研究列表 + 搜索
- [x] 前端详情页展示完整流程

---

## Milestone 4：产品化界面 ✅ 完成

### ISSUE-011：Company 详情页 ✅

- [x] Tab 布局 (概览/财务/研究/文档)
- [x] K 线图 (ECharts, MA5/MA20/成交量)
- [x] 营收/利润趋势条形图
- [x] 关联研究 + 关联文档

### ISSUE-012：Research Workspace ✅

- [x] 操作按钮 (生成计划/收集证据/生成报告)
- [x] 研究计划展示 (子问题/维度标签)
- [x] 证据分组展示 (支持/反对/中性)
- [x] 报告预览 (展开/收起, 多版本)
- [x] 完结流程 (thesis/decision/confidence)

### ISSUE-013：行情图表 ✅

- [x] ECharts K 线图
- [x] 快速切换股票 (NVDA/AAPL/MSFT 等)
- [x] 时间范围选择 (1月/3月/半年/1年/全部)
- [x] 统计卡片 (收盘/最高/最低/均价)

---

## Milestone 5：自动化能力 ✅ 完成

### ISSUE-014：Scheduler 基础设施 ✅

- [x] `core/scheduler.py` (APScheduler 框架)
- [x] 启动/停止/状态查询
- [x] 任务注册机制

### ISSUE-015：市场数据自动更新 ✅

- [x] 定时任务 (工作日 2am)
- [x] 遍历所有公司拉取行情
- [x] API: POST `/scheduler/run/market_data_update`

### ISSUE-016：Morning Brief ✅

- [x] AI prompt 设计
- [x] 收集市场数据 + 开放研究
- [x] LLM 生成简报
- [x] 存储到 Event Log

---

## Git Commits (本阶段)

```
0830f24 feat: frontend polish — AI center + portfolio management
3acd608 feat: Phase 5 automation — scheduler + market update + morning brief
ed9566b fix: test proxy env var interference
371f16b feat: ECharts K-line charts + market page + company financials
0e8e69e feat: market data seed + RAG reranker
0fcf466 feat: RAG enhancement with BGE Reranker + search UI
43bb96f feat: Document upload page with drag-and-drop
7f71b73 feat: Company detail page with tabs
cba1f53 feat: Research Workspace frontend enhancement
07f1bbd fix: PDF parser fixes + async test client + eager loading
0efcaf5 Phase 1: infrastructure + document pipeline complete
```

## 后续可选项

| 项目 | 优先级 | 预计 |
|------|--------|------|
| 用户系统 (注册/登录) | 低 | 3 天 |
| 异步测试补全 (bge-m3) | 低 | 半天 |
| CI/CD (GitHub Actions) | 低 | 2 天 |
| 生产部署文档 | 低 | 半天 |
