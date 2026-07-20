# AI Research OS — V1.0 Issue 开发任务列表

> 对应 GitHub Milestones + Issues。
> 使用方式：装好 `gh` 后，运行 `bash scripts/create-issues.sh` 一键创建所有 Issue。

---

## Milestone 1：基础工程完善 (Phase 1)

> 预计 2 周 | 优先级 P0

### ISSUE-001：Alembic Migration — 自动数据库迁移

**描述**：当前 `backend/alembic/versions/` 为空，没有任何迁移文件。需要为所有 7 个模块的 model 生成初始迁移。

**任务**：
- [ ] 确认 `backend/alembic/env.py` 已导入所有模块的 model
- [ ] 运行 `alembic revision --autogenerate -m "init"` 生成初始迁移
- [ ] 验证 `alembic upgrade head` 能创建所有表
- [ ] 更新 Makefile 确保 `make dev` → `make migrate` 流程顺畅

**涉及文件**：
- `backend/alembic/env.py`
- `backend/alembic/versions/`（新文件）
- `backend/core/base.py`（确认 Base 声明）
- `backend/core/database.py`

**验收**：`make reset-db` 能自动重建全部表结构。

---

### ISSUE-002：测试体系搭建 — Core + 业务模块

**描述**：当前 8 个 test 文件都是空函数占位。需要补全真实测试。

**任务**：
- [ ] `test_core.py` — 测试配置加载、异常类、CRUD 基类
- [ ] `test_company.py` — CRUD + 搜索 API 测试
- [ ] `test_market.py` — 行情数据查询测试
- [ ] `test_document.py` — 文档上传 + 管道测试（跳过需要 Qdrant 的部分）
- [ ] `test_knowledge.py` — 知识检索测试
- [ ] `test_research.py` — 研究会话工作流测试
- [ ] `test_ai.py` — Prompt 模板 + LLM 调用测试
- [ ] `test_portfolio.py` — 自选/持仓 CRUD 测试

**涉及文件**：
- `backend/tests/conftest.py`（测试夹具）
- `backend/tests/test_*.py`

**验收**：`make test` 通过，覆盖率 > 60%。

---

## Milestone 2：Document Pipeline (Phase 2)

> 预计 3 周 | 优先级 P0

### ISSUE-003：文档上传 API

**描述**：实现文件上传端点，支持 PDF / HTML / TXT / Markdown。

**任务**：
- [ ] 实现 `POST /api/v1/documents/upload` 端点
- [ ] 服务器端文件类型校验 + 大小限制
- [ ] 文件存储到 `data/uploads/`
- [ ] Document 记录写入数据库
- [ ] 前端上传页面（拖拽上传）

**涉及文件**：
- `backend/document/routes.py`
- `backend/document/service.py`
- `backend/document/schemas.py`
- `frontend/src/app/documents/page.tsx`

**验收**：通过 API 上传 PDF 文件，数据库生成 Document 记录。

---

### ISSUE-004：PDF 解析管道

**描述**：使用 PyMuPDF 实现 PDF 解析，提取文本 + 保留元数据（页码、标题层级）。

**任务**：
- [ ] 实现 `core/adapters/pdf_parser.py`（适配 DocumentParser Protocol）
- [ ] 解析后结构化文本 + 逐页元数据
- [ ] 集成到 Document Service 的 `parse` 步骤
- [ ] 错误处理（加密 PDF、扫描件等）

**涉及文件**：
- `backend/core/adapters/pdf_parser.py`（新建）
- `backend/core/interfaces.py`（已定义 `DocumentParser` Protocol）
- `backend/document/service.py`

**验收**：上传一份 10 页 PDF，解析出完整文本 + 每页标记。

---

### ISSUE-005：文本切片 + Embedding 管道

**描述**：解析后的文本经过切片 → embedding → 写入 Qdrant 的完整管道。

**任务**：
- [ ] 复用/优化 `document/chunker.py` 的分块逻辑
- [ ] 连接 `core/adapters/embedding.py` 的 bge-m3 生成向量
- [ ] 连接 `core/adapters/vector_store.py` 写入 Qdrant
- [ ] 切片元数据包含文档 ID、页码、chunk 序号
- [ ] 前端显示索引进度

**涉及文件**：
- `backend/document/chunker.py`
- `backend/document/service.py`
- `backend/core/adapters/embedding.py`
- `backend/core/adapters/vector_store.py`

**验收**：上传 PDF 后，Qdrant 中能查到对应 chunk 向量。

---

### ISSUE-006：RAG 检索 + 溯源

**描述**：知识库搜索能返回带来源引用的 AI 回答。

**任务**：
- [ ] 完善 `knowledge/service.py` 的 hybrid search（dense + sparse RRF）
- [ ] 实现 BGE Reranker 二次排序
- [ ] 检索结果附带文档标题/页码/doc_type 等元数据
- [ ] AI 回答时引用来源（`来源：NVIDIA Annual Report P38`）
- [ ] 前端搜索页面展示来源链接

**涉及文件**：
- `backend/knowledge/service.py`
- `backend/knowledge/routes.py`
- `backend/core/adapters/reranker.py`（新建）
- `frontend/src/app/knowledge/page.tsx`
- `frontend/src/lib/api.ts`

**验收**：上传财报后搜索"营收增长"，回答中附带来源引用。

---

## Milestone 3：Research 闭环 (Phase 3)

> 预计 4 周 | 优先级 P0

### ISSUE-007：Research Planner — 研究计划生成

**描述**：输入研究问题，AI 自动拆解为研究计划（需要收集哪些证据、分析哪些维度）。

**任务**：
- [ ] 设计 Research Plan 数据模型（子问题列表、数据需求、分析维度）
- [ ] 实现 LLM prompt 生成研究计划
- [ ] 研究会话创建时自动触发 Plan
- [ ] 前端显示研究计划

**涉及文件**：
- `backend/research/models.py`（新增 ResearchPlan）
- `backend/research/service.py`
- `backend/research/schemas.py`
- `backend/ai/service.py`
- `frontend/src/app/research/[id]/page.tsx`

**验收**：创建"分析 NVIDIA 增长逻辑"任务，自动生成包含财务/行业/竞争维度的研究计划。

---

### ISSUE-008：Evidence Collector — 证据收集

**描述**：根据研究计划，自动从知识库 + 行情数据 + 外部源收集证据。

**任务**：
- [ ] 实现 LangGraph 工作流：Plan → 并行检索 → 过滤 → 排序
- [ ] 对接 Knowledge Engine（RAG 检索）
- [ ] 对接 Market Data（财务指标）
- [ ] 证据分组：支持性 / 反对性 / 中性
- [ ] 证据关联来源元数据

**涉及文件**：
- `backend/research/service.py`
- `backend/research/models.py`（ResearchEvidence）
- `backend/knowledge/service.py`
- `backend/market/service.py`

**验收**：研究任务自动收集 10+ 条相关证据，标记正反方向。

---

### ISSUE-009：AI 分析 + 报告生成

**描述**：基于收集的证据，AI 生成结构化研究报告。

**任务**：
- [ ] 实现 LLM 分析 prompt（综合多方证据形成判断）
- [ ] 生成结构化报告：投资观点 / 支持证据 / 风险因素 / 结论
- [ ] 支持多版本报告（draft → review → final）
- [ ] 报告持久化到 ResearchReport 模型

**涉及文件**：
- `backend/research/models.py`（ResearchReport）
- `backend/research/service.py`
- `backend/research/schemas.py`
- `backend/ai/service.py`

**验收**：研究任务完成后，自动生成一份包含观点、证据、风险、结论的完整报告。

---

### ISSUE-010：研究记录持久化 — Memory + 回溯

**描述**：每次研究的完整过程（问题→证据→分析→结论）持久化保存，支持回溯查看。

**任务**：
- [ ] 研究会话状态机完善（draft → researching → reviewing → completed → archived）
- [ ] 研究过程 Event Log 记录（用已有的 `core/event_service.py`）
- [ ] 历史研究列表 + 搜索
- [ ] 前端研究详情页展示完整流程

**涉及文件**：
- `backend/research/service.py`
- `backend/research/models.py`
- `backend/research/routes.py`
- `backend/core/event_service.py`
- `frontend/src/app/research/[id]/page.tsx`

**验收**：完成一次研究后，重新打开可以查看从问题到结论的完整过程。

---

## Milestone 4：产品化界面 (Phase 4)

> 预计 3 周 | 优先级 P1

### ISSUE-011：Company 详情页

**描述**：公司知识主页，整合资料、财务、新闻、研究记录。

**任务**：
- [ ] Company 前端页面重构（tab 布局：概览/财务/文档/研究）
- [ ] 财务数据图表（ECharts：营收/利润趋势）
- [ ] 关联文档列表
- [ ] 关联研究历史

**涉及文件**：
- `frontend/src/app/companies/[id]/page.tsx`
- `frontend/src/app/companies/page.tsx`
- `frontend/src/lib/api.ts`
- `backend/company/routes.py`（可能需新增聚合端点）

**验收**：打开 NVIDIA 页面能看到公司信息 + 财务图表 + 关联研究。

---

### ISSUE-012：Research Workspace 交互增强

**描述**：研究任务的过程可视化（AI 思考步骤、证据收集进度、报告生成状态）。

**任务**：
- [ ] 研究任务状态实时更新（轮询 / WebSocket）
- [ ] 研究计划可视化（检查清单）
- [ ] 证据列表（支持/反对分组）
- [ ] 报告预览 + 版本切换

**涉及文件**：
- `frontend/src/app/research/[id]/page.tsx`
- `frontend/src/app/research/page.tsx`

**验收**：进行研究时，前端实时显示进度，完成后直接查看报告。

---

### ISSUE-013：Market 行情图表

**描述**：股票行情可视化，K 线图 + 技术指标。

**任务**：
- [ ] 集成 ECharts
- [ ] K 线图组件
- [ ] 财务指标图表
- [ ] 时间段选择（1月/3月/1年/5年）

**涉及文件**：
- `frontend/src/app/market/page.tsx`
- `frontend/package.json`（添加 ECharts）
- `frontend/src/components/StockChart.tsx`（新建）

**验收**：输入股票代码，显示 K 线图 + 可切换时间范围。

---

## Milestone 5：自动化能力 (Phase 5)

> 预计 1 个月 | 优先级 P1

### ISSUE-014：Scheduler 基础设施

**描述**：使用 APScheduler 实现每日定时任务。

**任务**：
- [ ] 确认/修复 `core/config.py` 中的调度配置
- [ ] 实现任务注册机制
- [ ] 支持每日/每周定时任务
- [ ] 任务日志记录

**涉及文件**：
- `backend/api/app.py`（lifespan 中启动 scheduler）
- `backend/core/scheduler.py`（新建）
- `backend/core/config.py`

**验收**：启动后端后，定时任务按配置时间自动触发。

---

### ISSUE-015：Market Data 自动更新

**描述**：每日自动更新关注公司的市场数据。

**任务**：
- [ ] 每日 2am 更新股价/市值/估值指标
- [ ] 更新 AkShare 行情数据到 PostgreSQL
- [ ] 变更检测（价格异动、估值区间变化）

**涉及文件**：
- `backend/market/service.py`
- `backend/core/adapters/akshare_mysql.py`

**验收**：定时任务自动拉取当日行情数据并更新数据库。

---

### ISSUE-016：Morning Brief 自动生成

**描述**：每日生成市场简报 + 关注公司动态。

**任务**：
- [ ] Morning Brief prompt 设计
- [ ] 收集市场概况 + 关注公司变化
- [ ] AI 生成简报
- [ ] 简报推送/展示

**涉及文件**：
- `backend/research/service.py`
- `backend/ai/service.py`
- `frontend/src/app/page.tsx`（首页展示）

**验收**：每天早上自动生成一份包含市场变化和关注公司动态的简报。

---

## 附录：Issue 创建脚本

```bash
#!/bin/bash
# scripts/create-issues.sh — 一键创建所有 GitHub Issue
# 需要 gh CLI 认证

MILESTONES=(
  "Phase 1: 基础工程完善"
  "Phase 2: Document + RAG Pipeline"
  "Phase 3: Research 闭环"
  "Phase 4: 产品化界面"
  "Phase 5: 自动化能力"
)

# 创建 Milestones
for m in "${MILESTONES[@]}"; do
  gh api repos/:owner/:repo/milestones -f title="$m" > /dev/null 2>&1 || true
done

echo "Milestones created. Run each ISSUE-NNN section individually."
```
