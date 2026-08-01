# 项目架构优化设计文档

## 1. 背景与目标

当前项目已具备深模块/Adapter 基础结构，但在可维护性和可扩展性方面仍有提升空间。主要痛点包括业务 Service 体积大、职责混杂；业务层直接使用 ORM；依赖分散；异常体系不统一；文件结构不够细分。

## 2. 关键改进方案

### 2.1 业务 Service 颗粒化 & Interface 化
- 将 `market/service.py` 拆分为 `price_service.py`, `news_service.py`, `financial_service.py`, `profile_service.py`。
- 为每个子 Service 在 `core/interfaces.py` 新增 `Protocol`（如 `PriceService`）。
- 在 `api/app.py` 为每个子 Service 注册独立 Router（`/api/v1/market/price` 等），保持对外统一 Facade `MarketFacade`。

### 2.2 引入 Domain DTO 与 Repository 层
- 在每个域新增 `domain.py`（业务 DTO），如 `PriceEntry`、`ResearchTimeline`。
- 在 `core/crud.py` 实现对应 Repository 接口（`PriceRepository` 等），Service 只处理 DTO。
- `schemas.py` 仅保留 API 用的 Pydantic 模型，使用 `from_orm=True` 将 DTO 转为响应。

### 2.3 统一依赖注入容器
- 新建 `core/container.py`（基于 `dependency-injector` 或轻量实现），在 `lifespan` 中一次性注册 `Interface → Implementation`（VectorStore、EmbeddingModel、LLM、Repositories、子 Services）。
- 路由使用 `Depends(container.market_price_service)` 获取实例。
- 测试只需在容器中替换实现，无需遍历 patch。

### 2.4 异常层级统一
- 在 `core/exceptions.py` 定义统一 `DomainError` 基类及子类（`InvalidInputError`, `ExternalServiceError`, `NotFoundError` 等）。
- Service 只抛出这些异常并在 `api/app.py` 注册 `exception_handler`，返回结构化 JSON。
- 使用 `raise NewError(...) from original` 保留堆栈信息。

## 3. 目录结构（改进后示例）
```
backend/
├─ core/
│   ├─ adapters/ (按功能子目录划分，如 embedding/, vector_store/, llm/)
│   ├─ interfaces.py
│   ├─ container.py
│   ├─ crud.py
│   └─ exceptions.py
├─ market/
│   ├─ service/
│   │   ├─ price_service.py
│   │   ├─ news_service.py
│   │   └─ ...
│   ├─ domain.py
│   ├─ repositories.py
│   ├─ routes/
│   │   ├─ price_routes.py
│   │   └─ ...
│   └─ __init__.py (MarketFacade)
├─ research/ … 同上模式
├─ api/app.py (FastAPI factory，加载 container, 注册子 routers)
└─ docs/superpowers/specs/2024-07-31-arch-optimisation-design.md (本文件)
```

## 4. 迁移路线

> 状态图例：✅ 已完成 ｜ 🔄 进行中 ｜ ⬜ 未开始

| # | 阶段 | 范围 | 状态 |
|---|------|------|------|
| 1 | 拆分 `market` 子 Service、Interface、Router；保留 `MarketFacade` 兼容旧调用 | `market/` | ✅ 完成 |
| 2 | 实现 Domain DTO 与 Repository，Service 改为使用 DTO | `market/domain.py`, `market/repositories.py` | ✅ 完成 |
| 3 | 引入 DI 容器，所有 Service 通过容器获取依赖 | `core/container.py` + 各域 routes | ✅ 完成 |
| 4 | 统一异常为 `DomainError` 系列并注册 handler | `core/exceptions.py`, `api/app.py` | ✅ 完成 |
| 5 | 将相同模式推广至 `research`, `portfolio`, `knowledge` 等域 | `research/`, `portfolio/`, `knowledge/` | ✅ 完成 |
| 6 | 配置 `ruff`/`mypy`/`pre-commit`，完善单元测试覆盖 | `pyproject.toml`, CI | ✅ 完成 |

### 4.1 阶段 3 & 5 细分状态

| 域 | 子 Service 拆分 | Domain DTO | Repository | 容器注册 | Facade | routes 用容器 |
|----|:---:|:---:|:---:|:---:|:---:|:---:|
| `market` | ✅ `service/` 6 个 | ✅ `domain.py` | ✅ `repositories.py` (3) | ✅ 6 服务 | ✅ `MarketFacade` | ✅ 6 子 router + `aggregate.py` |
| `research` | ✅ `session_service.py` / `evidence_service.py` / `report_service.py` / `gather_service.py` / `thesis_service.py` / `timeline_service.py` | ⬜ | ⬜ | ✅ 6 服务 | ✅ `ResearchFacade` | ✅ |
| `portfolio` | ✅ `service/` 3 个 (watchlist/holding/journal) | ⬜ | ⬜ | ✅ 3 服务 | ✅ `PortfolioFacade` | ✅ |
| `knowledge` | ✅ 单 Service（无拆分必要） | ⬜ | ⬜ | ✅ `knowledge_service` | ✅ `KnowledgeFacade` | ✅ |
| `document` | ⬜ | ⬜ | ⬜ | ✅ `document_service` | ⬜ | ✅ |
| `ai` | ⬜ | ⬜ | ⬜ | ✅ `ai_service` | ⬜ | ✅ |
| `company` | ⬜ | ⬜ | ⬜ | ✅ `company_service` | ⬜ | ✅ |
| `dashboard` | ⬜ | ⬜ | ⬜ | ✅ `dashboard_service` | ⬜ | ✅ |

> 全部 8 个域已复用「Protocols + 容器 + Facade + routes 容器化」模式；`document`/`ai`/`company`/`dashboard` 未做子 Service 拆分（单 Service 无拆分必要），Domain DTO / Repository 层是否引入视后续需要决定。

## 5. 迁移风险与应对
- **兼容性破坏**：在 `market/__init__.py` 保留旧函数的代理实现。
- **DI 循环依赖**：使用 Provider 的 lazy 初始化或 Factory 方式。
- **异常遗漏**：迁移完成后运行脚本搜索 `raise`，确保全部映射至 `DomainError`。
- **测试基准变更**：先保持旧返回结构，逐步改为 DTO 再更新测试。

## 6. 实施进度快照

### ✅ 已完成
- **market 域（阶段 1-4 全量）**：`market/service/`（6 个聚焦 Service）、`market/routes/`（6 子 router + `aggregate.py` + 聚合导出）、`market/domain.py`（`PriceEntry`/`FinancialMetricEntry`/`FreshnessEntry`/`MacroIndicatorEntry`）、`market/repositories.py`（`PriceRepository`/`FinancialRepository`/`FreshnessRepository`）、`market/service.py` deprecated shim、`MarketFacade` 兼容层。
- **DI 容器**：`core/container.py`（`Container` + `create_container`），懒加载 20 个服务属性；`core/database.py` 新增 `get_container` 依赖。
- **Protocols**：`core/interfaces.py` 现有 19 个域服务 Protocol（market 5 + research 5 + timeline 1 + portfolio 3 + knowledge 1 + company 1 + document 1 + ai 1 + dashboard 1），容器懒加载 20 个服务属性（含 market `FreshnessService` 直接用具体类型）。
- **异常体系**：`core/exceptions.py` 定义 `AIResearchOSError` → `DomainError` 层级；`api/app.py` 注册 8 个 handler（`NotFoundError`/`ValidationError`/`DuplicateError`/`AuthenticationError`/`AuthorizationError`/`ExternalServiceError`/`AIResearchOSError`/`DomainError`）。全库 `raise` 扫描确认全部为结构化异常。
- **research 域**：6 个 Protocol（session/evidence/report/gather/thesis/timeline）+ 容器注册 + `ResearchFacade` + routes 容器化；`quick.py` 后台任务与 SSE 也统一走容器工厂。
- **portfolio 域**：`PortfolioService` 拆分为 `service/` 3 个子服务 + `PortfolioFacade` + 容器注册 + routes 容器化；`service/__init__.py` 保留 `PortfolioService` 后向兼容别名。
- **knowledge 域**：`KnowledgeService` Protocol + 容器注册 + `KnowledgeFacade` + routes 容器化。
- **document/ai/company/dashboard 域**：4 个 Protocol + 容器注册 + routes 容器化（B7 收尾完成）。
- **模型注册**：`api/app.py` 显式导入全部 ORM 模型（与 `alembic/env.py` 同列表），不再依赖路由对服务模块的传递性导入——消除了 lazy 容器化后 mapper 配置不完整的隐患。
- **后台任务容器化**：`scheduler_jobs.market_data_update` 与 `quick_research` 任务处理器改用 `create_container(session)` 工厂，后台与请求路径共用同一依赖图。
- **安全修复（P0）**：akshare 子进程不再把 ticker 拼进 Python 源码；改由环境变量传参（`build_akshare_env` + `AKSHARE_TICKER`），并加字符白名单纵深防御。新增 `tests/test_akshare_safety.py`（18 个用例，含真实子进程隔离验证）。
- **测试夹具**：conftest 同步覆盖 `get_container`，所有容器化路由在测试中走每次测试独立的 NullPool 会话，消除了 TestClient 与 pytest 事件循环间连接池串用导致的 "Event loop is closed"。
- **测试基线**：全量 `116 passed / 0 failed`（`airesearch_test` 独立测试库 + 基础设施在线的环境下），此前 7 个环境依赖失败已全部归零。
- **部署边界**：README 新增安全边界章节；`SECRET_KEY` 默认随机生成、CORS 默认指向 5173、`.env` 对齐；research 的 mutation 端点（finalize/generate-report/create report）从 query param 改为请求体（前后端同步）。
- **数据层**：BM25 语料改为分页全量加载（`BM25_MAX_CHUNKS` 可配置上限，默认不截断）；`PriceRepository`/`FinancialRepository` upsert 改为批量查询；新增 pg_trgm GIN 索引迁移（加速 ILIKE 兜底检索）；embedding/LLM 共享 httpx 客户端改为事件循环感知（修复跨 loop 复用）。
- **scheduler_jobs 拆分**：拆为 `core/market_sync.py`、`core/news_fetcher.py`、`core/brief_generator.py`，原模块保留为兼容转发层；新增 `core/event_cleanup.py`（事件日志每周保留清理，`EVENT_LOG_RETENTION_DAYS=90`）。
- **代码质量门槛**：全仓库 `ruff check` + `ruff format` 清零（含既有历史欠账）；`[tool.mypy]` 配置（core 范围 + market domain/repositories + research schemas）零错误；`.pre-commit-config.yaml` 接入 ruff/ruff-format/mypy 三钩子并全部通过；mypy 修复过程中顺带对齐了 8 个域服务的 Protocol 真实签名（Any → 具体类型，`TYPE_CHECKING` 导入保持运行时解耦）。

### 🔄 进行中
- **发布收尾**：`refactor/vue3-rewrite` 分支尚未合并/创建 PR。

### ⬜ 未开始
- **Protocol 全覆盖**：`research`/`portfolio`/`knowledge` 等域服务的返回类型仍为 ORM 模型直出（协议已对齐具体签名，但未引入独立 DTO 层）；是否引入视后续需要决定。

## 7. 实施计划（原时间估算）
| 周 | 任务 | 状态 |
|----|------|------|
| 1 | 完成 `market` 子 Service 拆分、Interface、Router | ✅ |
| 2 | 实现 `market` Domain DTO 与 Repository | ✅ |
| 3 | 引入 DI 容器并迁移 `market` Service | ✅ |
| 4 | 统一 `market` 异常并注册 handler | ✅ |
| 5-6 | 在其他域复用相同模式 | ✅（全部 8 域 + 后台任务已容器化） |
| 7 | 配置代码质量工具，完成全套测试 | ✅ |
| 8 | 文档审查、PR 合并 | ⬜ |

## 8. 文档化与后续
- 本设计文档已提交至 `docs/superpowers/specs/2024-07-31-arch-optimisation-design.md`。
- 实现计划将通过 `writing-plans` skill 自动生成，并在 PR 中链接。
- CI 将在 PR 合并前检查设计文件是否为最新版本，防止实现脱离设计。

---

**结论**：通过 Service 颗粒化、Domain + Repository、统一 DI、异常层级化，实现 **更高的可维护性、可测试性和可扩展性**，并保持现有深模块优势。后续如需查看具体 Interface 定义或容器实现示例，请告知，我可以提供相应代码片段。
