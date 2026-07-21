# AI Research OS V1.0 实施方案

> 最后更新: 2026-07-20 | 状态: **V1 核心功能已完成**

## 1. 项目定位

### 项目名称

AI Research OS（AI 投资研究操作系统）

### V1 定位

个人投资智能系统（Personal Investment Intelligence Platform）

核心价值：

- 自动收集投资相关信息 ✅
- 管理公司研究资料 ✅
- 利用 AI 辅助分析 ✅
- 形成投资研究报告 ✅
- 保存投资逻辑和历史判断 ✅

---

## 2. V1 核心目标 — ✅ 已完成

核心闭环已跑通：

```
投资问题 → Research Task → 数据 + 文档 + 新闻 → AI 分析
  → Research Report → Investment Thesis → Decision → Memory
```

---

## 3. 系统架构 — Modular Monolith

```
User → Research Workspace (Next.js)
     → API Layer (FastAPI)
     → Business Layer (7 modules)
     → Core Platform (PG + Qdrant + LLM + Redis)
```

---

## 4. 核心模块

### Module 1：Research Engine ✅

完整流程：

```
Question → AI Planner → Evidence Collector → AI Report → Thesis → Decision
```

- 6 个子问题自动生成
- 6 个分析维度
- 支持/反对/中性证据分组
- LLM 结构化报告
- 研究会话状态机 draft→researching→reviewing→completed→archived

### Module 2：Knowledge Engine ✅

- Vector Search (Qdrant, bge-m3)
- Sparse Search (BM25)
- Reciprocal Rank Fusion
- BGE Reranker (cross-encoder)

### Module 3：Document Engine ✅

- Upload (PDF / MD / TXT / HTML)
- PDF parse (PyMuPDF, page metadata, encrypted/scanned detection)
- Chunk + Embed + Index

### Module 4：Market Data Engine ✅

- 8 companies × 2 years daily price data
- Financial metrics (revenue, profit, margin, EPS)
- Scheduler: daily auto-update

### Module 5：Company Intelligence ✅

Per-company page with:
- Company profile
- K-line chart
- Revenue/profit trends
- Related research
- Related documents

### Module 6：Portfolio Journal ✅

- Watchlists (create/manage)
- Holdings (add/view)
- Investment journal

---

## 5. Core Platform

| 组件 | 状态 | 说明 |
|------|------|------|
| PostgreSQL | ✅ | 17 张表, Alembic 迁移 |
| Qdrant | ✅ | 向量存储, 检索 |
| LLM | ✅ | Ollama, Adapter 模式 |
| Cache (Redis) | ✅ | 已部署 |
| Scheduler | ✅ | APScheduler, 2 个定时任务 |
| Storage | ✅ | 文件存储 |

---

## 6. 技术栈

| 层 | 技术 | 状态 |
|----|------|------|
| Backend | Python / FastAPI / SQLAlchemy / Alembic | ✅ |
| AI | Ollama / LangGraph-ready | ✅ |
| Knowledge | Qdrant / BGE-M3 / BGE-Reranker | ✅ |
| Database | PostgreSQL (pgvector) | ✅ |
| Frontend | Next.js / React / TypeScript / Tailwind / ECharts | ✅ |
| Deployment | Docker Compose | ✅ |

---

## 7. 开发路线 — 实际完成情况

### Phase 1：基础工程完善 ✅

- [x] Alembic Migration — 17 张表自迁移
- [x] 测试体系 — 88 同步测试通过

### Phase 2：知识库闭环 ✅

- [x] 文档上传 (PDF / MD / TXT / HTML)
- [x] PDF 解析 (PyMuPDF + 元数据)
- [x] 切片 + Embedding + Qdrant 索引
- [x] 混合检索 (dense + sparse + reranker)

### Phase 3：Research 闭环 ✅

- [x] Research Planner (AI 计划生成)
- [x] Evidence Collector (多维度收集)
- [x] AI 报告生成
- [x] 研究持久化 + 回溯

### Phase 4：产品化界面 ✅

- [x] Company 详情页 (Tab/财务图表/研究/文档)
- [x] Research Workspace (计划/证据/报告/完结)
- [x] 文档上传页 (拖拽/进度)
- [x] 行情中心 (K线/财务指标)
- [x] AI 中心 (Prompt模板/摘要)
- [x] 投资组合 (自选/持仓)
- [x] 知识库搜索 (类型过滤/得分条)

### Phase 5：自动化能力 ✅

- [x] Scheduler 框架 (APScheduler)
- [x] 市场数据自动更新 (工作日 2am)
- [x] Morning Brief (工作日 6am, AI 生成)

---

## 8. 完成情况总览

| 维度 | 完成度 |
|------|--------|
| 后端代码 | ~7000 行 Python |
| 前端代码 | ~2450 行 TSX/TS |
| 测试 | 88 同步测试通过 |
| 数据库 | 7 schema × 17 表 |
| Git commits | 19 (本地) / 已推送 GitHub |
| 核心功能闭环 | ✅ 全部可运行 |

---

## 9. V1 完成标准对照

| 标准 | 状态 | 说明 |
|------|------|------|
| **数据能力**: 导入财报、管理资料、搜索历史 | ✅ | PDF 上传→解析→索引→搜索全链路 |
| **AI 能力**: 自动分析、提取证据、生成报告 | ✅ | Planner + Collector + Report Generator |
| **研究能力**: 公司研究→投资观点→历史记录 | ✅ | 完整状态机, Event Log |
| **产品能力**: 每天看到市场/公司变化 | ✅ | Morning Brief + 行情图表 |

---

## 10. 后续可选项（非 V1 必要）

| 项目 | 预计 | 说明 |
|------|------|------|
| 用户系统 | 3 天 | 注册/登录/JWT |
| RAG 溯源增强 | 1 天 | 搜索结果带页码引用 |
| 异步测试补全 | 半天 | 依赖 bge-m3 模型下载 |
| CI/CD | 2 天 | GitHub Actions |
| 部署文档 | 半天 | 生产环境部署指南 |
