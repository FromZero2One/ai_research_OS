# AI Research OS V1.0 实施方案

> 最后更新: 2026-07-20

## 1. 项目定位

### 项目名称

AI Research OS（AI 投资研究操作系统）

### V1 定位

个人投资智能系统（Personal Investment Intelligence Platform）

目标不是打造股票聊天机器人，而是建立一个能够长期积累投资认知的研究基础设施。

核心价值：

- 自动收集投资相关信息
- 管理公司研究资料
- 利用 AI 辅助分析
- 形成投资研究报告
- 保存投资逻辑和历史判断

最终形成：

> 一个随着时间不断成长的个人投资大脑。

---

## 2. V1 核心目标

V1 **不追求**：

- 自动交易
- 高频量化
- 完整 Bloomberg 替代
- 复杂多 Agent 系统

V1 **只解决一个核心问题**：

> 如何持续跟踪关注公司，并形成高质量投资判断？

核心闭环：

```
投资问题 → Research Task → 数据 + 文档 + 新闻 → AI 分析
  → Research Report → Investment Thesis → Decision → Memory
```

---

## 3. 系统架构

### Modular Monolith（模块化单体架构）

特点：开发成本低、易维护、未来可拆分微服务、支持长期演进。

```
                User
                 │
        Research Workspace
                 │
             API Layer
                 │
═══════════════════════════════════════════
              Business Layer
  ┌──────┬──────┬──────┬──────┬──────┬──────┐
  │Research│Knowledge│Doc│Market│Company│Portfolio│
  │ Engine │ Engine │Engine│Data  │Intel │ Journal│
  └──────┴──────┴──────┴──────┴──────┴──────┘
                 │
═══════════════════════════════════════════
              Core Platform
  ┌─────┬──────┬──────┬──────┬──────┬────────┐
  │Postgres│Qdrant│ LLM │Cache │Scheduler│Storage│
  └─────┴──────┴──────┴──────┴──────┴────────┘
```

---

## 4. 核心模块

### Module 1：Research Engine（核心模块）

**定位**：整个系统的大脑。负责从投资问题到研究报告的完整流程。

**输入**：`分析 NVIDIA 未来三年的增长逻辑`

**输出**：Research Report（投资观点、支持证据、风险因素、关键指标、最终结论）

**内部流程**：
```
Research Question → Research Planner → Evidence Collector
  → AI Analysis → Report Generator → Memory Storage
```

**技术**：LangGraph、LLM Adapter、Prompt Management

---

### Module 2：Knowledge Engine（知识中心）

**定位**：系统长期知识资产。让 AI 理解历史资料。

**数据来源**：财报、电话会议、新闻、行业报告、公司公告

**流程**：
```
Document → Embedding → Vector Search → Retrieve → AI Reasoning
```

**技术**：Qdrant、BGE-M3 Embedding、BGE Reranker

**必须支持 Metadata Filtering**：`company=NVIDIA` `type=earnings` `year>2025`

---

### Module 3：Document Engine（文档中心）

**定位**：所有研究资料入口。支持 PDF / HTML / TXT / Markdown。

**完整 Pipeline**：
```
Upload → Parser → Cleaner → Chunk → Embedding → Index → Storage
```

**必须实现文档溯源**：AI 回答必须显示来源（哪个文档、第几页）。

**技术**：PyMuPDF、BGE-M3、Qdrant

---

### Module 4：Market Data Engine（市场数据）

**定位**：研究辅助数据。不做交易系统。

**负责**：股价、市值、PE/PB、营收/利润/现金流、行业数据

**数据源**：AkShare、Yahoo Finance

**存储**：PostgreSQL（未来考虑 TimescaleDB）

---

### Module 5：Company Intelligence（公司智能中心）

**定位**：公司知识主页。NVIDIA 页面包含：公司介绍、商业模式、财务趋势、相关新闻、研究记录、当前投资观点、风险因素。

**数据来源**：Market Data + Document + Research + Knowledge

---

### Module 6：Portfolio Journal（投资日志）

**定位**：记录投资过程。不是交易系统。

保存：为什么买？当时观点？依据是什么？后来发生什么？判断是否正确？

价值：形成个人投资反馈系统。

---

## 5. Core Platform

| 组件 | 技术 | 职责 |
|------|------|------|
| Database | PostgreSQL | 公司数据、研究数据、投资记录 |
| Vector DB | Qdrant | 文档向量、研究记忆 |
| LLM Layer | Ollama / OpenAI (通过 Adapter 隔离) | Qwen / DeepSeek / GPT |
| Cache | Redis | 缓存层 |
| Scheduler | APScheduler | 自动任务（市场数据更新、Morning Brief） |
| Storage | 本地文件 | PDF、原始数据、报告文件 |

---

## 6. 技术栈

| 层 | 技术 |
|----|------|
| Backend | Python / FastAPI / SQLAlchemy / Pydantic / Alembic |
| AI | Ollama / LangGraph / LlamaIndex |
| Knowledge | Qdrant / BGE-M3 / BGE-Reranker |
| Database | PostgreSQL (pgvector) |
| Frontend | Next.js / React / TypeScript / Tailwind / ECharts |
| Deployment | Docker Compose |

---

## 7. 开发路线

### Phase 1：基础工程完善（2 周）

目标：补齐生产基础。

- [ ] Alembic Migration — 完成所有表自动迁移
- [ ] 测试体系 — Core / RAG / Research 测试

验收：系统可以自动初始化数据库。

### Phase 2：知识库闭环（3 周）

目标：PDF → AI 问答。

- [ ] 文档上传
- [ ] PDF 解析（PyMuPDF）
- [ ] 切片 + Embedding
- [ ] Qdrant 索引
- [ ] 检索回答 + 溯源

验收：上传 NVIDIA 财报，可以回答相关问题并显示来源。

### Phase 3：Research 闭环（4 周）

目标：核心价值闭环。

- [ ] Research Planner（研究计划生成）
- [ ] Evidence Collector（证据收集）
- [ ] AI 分析 + 报告生成
- [ ] 研究记录持久化

验收：可以自动生成一份完整公司研究报告。

### Phase 4：产品化（3 周）

目标：提升使用体验。

- [ ] Company 页面（资料 + 财务 + 新闻 + Research）
- [ ] Research Workspace（任务 + AI 过程 + 报告）
- [ ] Evidence 页面（观点对应证据）

### Phase 5：自动化能力（1 个月）

- [ ] Morning Brief 每日自动生成
- [ ] 市场变化 / 关注公司变化 / 投资逻辑变化 / 风险提醒

---

## 8. 优先级

| 优先级 | 任务 | 价值 |
|--------|------|------|
| P0 | Research 闭环、Document Pipeline、RAG 质量、数据库迁移 | ★★★★★ |
| P1 | 测试体系、Company 页面、Evidence 展示、Morning Brief | ★★★★ |
| P2 | 行情图表、Portfolio 增强、事件系统 | ★★★ |
| P3 | Trading Agents、知识图谱、复杂 Agent 系统 | ★★ |

---

## 9. V1 完成标准

**数据能力**：导入财报、管理研究资料、搜索历史信息

**AI 能力**：自动分析问题、提取证据、生成报告

**研究能力**：完成公司研究 → 投资观点 → 历史记录

**产品能力**：每天打开系统可以看到今天市场发生什么、关注公司发生什么、投资逻辑是否变化、下一步研究什么

---

## 10. 长期演进

| 版本 | 定位 | 新增能力 |
|------|------|----------|
| V1 | Personal Research Assistant | 研究闭环 |
| V2 | AI Investment Analyst | Trading Agents、Event Engine、Knowledge Graph |
| V3 | Investment Intelligence Platform | 多 Agent 协作、行业模型、因子系统 |

---

## 11. 最终原则

**Research First, not AI First** — AI 只是能力。

真正资产是：**数据 → 知识 → 研究 → 观点 → 经验**。

最终目标：建立一个长期积累、不断进化的个人投资智能系统。
