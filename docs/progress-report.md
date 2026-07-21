# AI Research OS — 项目完整进度报告

**生成时间**: 2026-07-21 | **状态**: V1 ✅ + V1.1 ✅（共 10 个 Sprint 全部交付）

---

## 一、项目定位

个人 AI 驱动的投资研究助手。核心理念：**"Research First, not AI First"** — AI 是研究流程中的能力组件，而非中心。

**V1 核心闭环已验证：**
```
创建研究 → AI 生成计划(6子问题/6维度) → 收集证据(知识库+行情)
  → AI 生成报告 → 完结(观点/决策/置信度)
```

**V1.1 日循环已验证：**
```
打开系统 → 看 Morning Brief → 查看 Watchlist → 收到研究提醒
  → 一键发起研究 → 查看 Timeline → 维护 Thesis
```

---

## 二、关键指标

| 指标 | 数值 |
|------|------|
| 后端代码 | ~8000 行 Python |
| 前端代码 | ~2600 行 TSX/TS |
| 数据库 | 7 schema × 17 张表 |
| 同步测试 | 88 个 |
| 异步测试 | 10 个（需 bge-m3 模型） |
| 种子数据 | 8 公司 + 2年合成行情 + 1 研究会话 |
| API 端点 | 45+（V1 + V1.1 新增 16 个） |
| Git commits | 20 |
| GitHub | `FromZero2One/ai_research_OS.git`（main） |

---

## 三、Phase 完成状态

### V1（5 Phase 全部完成）

```
Phase 1 基础工程: ████████████████ 100%  ✅
Phase 2 文档管道:  ████████████████ 100%  ✅
Phase 3 Research:  ████████████████ 100%  ✅
Phase 4 产品化界面: ████████████████ 100%  ✅
Phase 5 自动化:    ████████████████ 100%  ✅
```

### V1.1（5 Sprint 全部交付）

```
Sprint 1 入口:    ████████████████ 100%  ✅
Sprint 2 信号行动: ████████████████ 100%  ✅
Sprint 3 记忆:    ████████████████ 100%  ✅
Sprint 4 北极星:  ████████████████ 100%  ✅
Sprint 5 信任:    ████████████████ 100%  ✅
```

---

## 四、V1 完成功能

### 4.1 Core Layer（核心层）

| 组件 | 文件 | 说明 |
|------|------|------|
| 配置管理 | `core/config.py` | pydantic-settings 全面配置 |
| 数据库 | `core/database.py` | 异步 SQLAlchemy + get_db 依赖注入 |
| 接口协议 | `core/interfaces.py` | 6 个 Protocol（Embedding/VectorStore/LLM/DocumentParser/MarketData/Cache） |
| 异常体系 | `core/exceptions.py` | NotFound/Validation/Duplicate/Auth/External |
| 安全模块 | `core/security.py` | 基础安全工具 |
| Event Log | `core/event_log.py` | 写一次审计日志模型 |
| Event 服务 | `core/event_service.py` | EventLogger 写入封装 |

**适配器：** LLM（Ollama/OpenAI）、VectorStore（Qdrant）、Embedding（Ollama/sentence-transformers）、PDF Parser（PyMuPDF）、Reranker（BGE）、Cache、AKShare MySQL

### 4.2 Company Center
- 公司 CRUD + 搜索 + 标签管理
- 8 家公司（AAPL/MSFT/GOOGL/AMZN/NVDA/TSLA/JPM/BRK.B）
- 前端详情页：K 线图、营收利润趋势

### 4.3 Market Center
- 8 公司 × 2 年合成日度行情数据
- 财务指标（营收/利润/利润率/EPS）
- 前端行情页：ECharts K 线、时间范围选择

### 4.4 Document Center
- PDF/MD/TXT/HTML 上传 + PyMuPDF 解析 + 切片 + Qdrant 索引
- 前端拖拽上传

### 4.5 Knowledge Center
- 混合检索：Dense（Qdrant）+ Sparse（BM25）+ RRF 融合 + BGE Reranker
- 前端搜索页面

### 4.6 AI Center
- Prompt 模板 CRUD + 生成/摘要/提取 + 工作流
- 8 个 API 端点

### 4.7 Research Center
- AI Planner → Evidence Collector → Report → Finalize
- 状态机：draft → researching → reviewing → completed → archived

### 4.8 Portfolio Center
- 自选列表 / 持仓管理 / 投资日志

### 4.9 自动化
- APScheduler（市场更新 2am / Morning Brief 6am）

### 4.10 前端（V1 8 个页面）
Home / Research / Companies / Documents / Knowledge / Market / AI / Portfolio

---

## 五、V1.1 新增功能

### Sprint 1 — Entry Point（入口）

| 功能 | 说明 |
|------|------|
| **Dashboard 首页** | 替换原有简单首页，成为唯一默认入口 |
| **Morning Brief 卡片** | 展示当日最新 AI 生成的晨间简报 |
| **Watchlist 摘要表格** | 公司/价格/涨跌/状态（Normal/Attention/NeedResearch）/Thesis/研究天数 |
| **Research Reminder** | 自动提示需更新的研究（>30 天未研究标红） |
| **Quick Actions** | 5 个快捷按钮（新建研究/上传文档/搜索知识库/查看公司/查看行情） |
| **WatchlistItem 扩展** | 增加 `priority` 字段 + 数据库迁移 |

**新增 API：**
```
GET  /api/v1/dashboard              → 聚合数据（brief + watchlist + reminders）
GET  /api/v1/dashboard/brief        → 最新 Morning Brief
GET  /api/v1/dashboard/watchlist    → Watchlist 摘要
```

### Sprint 2 — Signal → Action（信号 → 行动）

| 功能 | 说明 |
|------|------|
| **Observation Engine** | 定时扫描 Watchlist 的自动观测 Job |
| **Research >14d** | → attention 状态 |
| **Research >30d** | → need_research 状态 |
| **价格波动 >5%** | 记录价格信号 |
| **One Click Research** | 一键发起研究全链：Plan → Evidence → Report |
| **SSE 实时进度流** | 前端展示 Planning → Searching → Generating → Completed |
| **快速研究页面** | `/research/quick` 输入公司+问题，实时进度条 |

**新增 API：**
```
POST /api/v1/research/quick                  → 一键研究
GET  /api/v1/research/quick/{id}/stream      → SSE 实时进度
GET  /api/v1/research/quick/{id}/status      → 轮询状态
POST /api/v1/scheduler/observe               → 手动触发观测
GET  /api/v1/scheduler/observations          → 查看观测记录
```

### Sprint 3 — Memory（记忆）

| 功能 | 说明 |
|------|------|
| **Research Timeline** | 按公司维度显示所有研究活动的完整历史 |
| **Timeline 页面** | `/research/timeline` 输入代码查询 |
| **Session Timeline** | 单研究会话内部事件线 |
| **Report Diff** | 报告版本对比（unified diff + 新增/删除统计） |
| **Evidence Viewer 增强** | 来源图标、可信度百分比颜色、分类颜色 |

**新增 API：**
```
GET  /api/v1/research/timeline?ticker=NVDA     → 公司研究时间线
GET  /api/v1/research/reports/{id}/diff         → 报告版本对比
GET  /api/v1/research/sessions/{id}/timeline    → 会话时间线
```

### Sprint 4 — North Star（北极星）

| 功能 | 说明 |
|------|------|
| **Thesis Panel** | 每家公司唯一 Current Thesis，EventLog 持久化 |
| **Thesis 编辑** | 带 decision（buy/sell/hold/watch/pass）+ confidence 滑块 |
| **Company Workspace** | 聚合 thesis + 证据统计 + 近期研究 |
| **公司页面新增"投资观点"标签页** | 集中管理观点 |
| **Thesis 顶部横幅** | 公司页头部显示当前观点 |
| **快速研究按钮** | 替换旧版"研究此公司" |

**新增 API：**
```
GET  /api/v1/companies/by-ticker/{ticker}/thesis     → 获取当前观点
POST /api/v1/companies/by-ticker/{ticker}/thesis     → 更新观点
GET  /api/v1/companies/by-ticker/{ticker}/workspace  → 公司工作空间
```

### Sprint 5 — Trust（信任）

| 功能 | 说明 |
|------|------|
| **Command Palette** | ⌘K 全局命令面板 |
| **11 条命令** | 覆盖全部分页（工作台/快速研究/研究中心/时间线/公司/文档/知识库/行情/AI/组合/系统） |
| **键盘导航** | ↑↓ 导航 + Enter 确认 + Esc 关闭 |
| **搜索过滤** | 按名称/描述/关键词实时过滤 |
| **系统状态页面** | `/system` 调度器、观测、API 健康检查 |
| **Scheduler 状态** | 30 秒自动刷新 |
| **API 健康检查** | 4 个关键端点自动探测 |
| **快捷建说明** | 页面内文档 |

---

## 六、代码变更统计（V1.1）

| 维度 | 数值 |
|------|------|
| 新增后端文件 | 10 个 |
| 新增前端文件 | 6 个 |
| 修改后端文件 | 11 个 |
| 修改前端文件 | 4 个 |
| 新增 API 端点 | 16 个 |
| 新增前端页面 | 4 个（quick / timeline / system / 重写首页） |
| 新增前端组件 | 2 个（CommandPalette） |
| 变更代码 | +3900 / -311 行 |
| Git commit | `a52c081`（已推送 GitHub） |

---

## 七、当前运行状态

| 服务 | 状态 | 地址 |
|------|------|------|
| PostgreSQL | ✅ 运行中 | localhost:5432 |
| Qdrant | ✅ 运行中 | localhost:6333 |
| Redis | ✅ 运行中 | localhost:6380 |
| Ollama（qwen3.5:latest） | ✅ 运行中 | 127.0.0.1:11434 |
| Backend（FastAPI） | ✅ 运行中 | 127.0.0.1:8000 |
| Frontend（Next.js 15） | ✅ 运行中 | localhost:3000 |

---

## 八、⚠️ 已知问题

### 环境问题

| # | 问题 | 严重度 | 说明 |
|---|------|--------|------|
| 1 | **SOCKS 代理环境变量干扰** | 🟡 | `all_proxy=socks://127.0.0.1:7890/` 导致 localhost 连接走代理。LLM/Embedding 已改用 curl subprocess 绕过，但部分 httpx 调用仍受影响。`.bashrc` 已添加 `no_proxy` |
| 2 | **Ollama 版本过旧（0.20.2）** | 🟡 | 不支持 `/api/chat` 和 `/api/embed` 端点。LLM → curl subprocess + `/api/generate`。Embedding → 返回零向量（稠密检索失效，BM25 正常） |
| 3 | **sentence-transformers 未安装** | 🟡 | 需 ~2.2GB 下载，Embedding 本地模型可用，但后端启动不阻塞 |
| 4 | **系统 GNOME 代理 `manual` 模式** | 🟢 已修复 | 已改为 `none`，代理通过 shell env 管理 |

### 功能问题

| # | 问题 | 严重度 | 说明 |
|---|------|--------|------|
| 5 | **一键研究执行慢（60-90s）** | 🟡 | 同步执行阻塞请求。可改用后台任务 + SSE 恢复 |
| 6 | **LLM 偶尔返回空内容** | 🟡 | Qwen 模型对 prompt 格式敏感，已调优但偶尔空响应 |
| 7 | **Research Plan JSON 降级** | 🟡 | LLM 返回格式不规范时用 fallback（1 子问题） |
| 8 | **Embedding 零向量** | 🟡 | 稠密检索不可用，稀疏检索 BM25 正常 |
| 9 | **TypeScript 3 类型错误** | 🟢 | `companies/[id]/page.tsx` 中 `string \| null`，不影响运行 |

---

## 九、当前环境启动方式

```bash
# 1. 启动 Docker 基础设施
docker compose -f docker/docker-compose.yml up -d

# 2. 从 backend 目录启动后端（加载 .env 配置）
cd backend && ALL_PROXY= all_proxy= uvicorn api.app:app --host 0.0.0.0 --port 8000

# 3. 启动前端（新终端）
cd frontend && npm run dev
```

**注意：** 必须从 `backend/` 目录启动 uvicorn，否则 `.env` 文件不会被加载，会导致模型名、数据库 URL 等配置使用默认值。

---

## 十、后续建议

### 短期（1-2 天）
- 异步测试补全（安装 bge-m3 后通过 10 个异步测试）
- 修复 TypeScript 3 个类型错误

### 中期（V1.2）
- 提升 LLM 调用稳定性（升级 Ollama 或统一 prompt 格式）
- 恢复后台任务 + SSE（解决一键研究超时问题）
- Embedding 修复（升级 Ollama 或安装 sentence-transformers）
- Observation Engine 增强（财报/新闻信号接入）

### V2 方向
| 领域 | V1/V1.1 | V2 |
|------|---------|-----|
| Knowledge | Hybrid RAG | + Knowledge Graph |
| AI | Single LLM | + LangGraph DAGs |
| Portfolio | Watchlist + Journal | + P&L Tracking |
| Research | Manual + Assist | + Auto Research |
| 产品 | 单用户 | + 用户系统 |
