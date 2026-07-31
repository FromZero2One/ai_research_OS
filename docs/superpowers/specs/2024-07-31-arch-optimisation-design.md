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
| 3 | 引入 DI 容器，所有 Service 通过容器获取依赖 | `core/container.py` + 各域 routes | 🔄 部分完成 |
| 4 | 统一异常为 `DomainError` 系列并注册 handler | `core/exceptions.py`, `api/app.py` | ✅ 完成 |
| 5 | 将相同模式推广至 `research`, `portfolio`, `knowledge` 等域 | `research/`, `portfolio/`, `knowledge/` | 🔄 部分完成 |
| 6 | 配置 `ruff`/`mypy`/`pre-commit`，完善单元测试覆盖 | `pyproject.toml`, CI | ⬜ 未开始 |

### 4.1 阶段 3 & 5 细分状态

| 域 | 子 Service 拆分 | Domain DTO | Repository | 容器注册 | Facade | routes 用容器 |
|----|:---:|:---:|:---:|:---:|:---:|:---:|
| `market` | ✅ `service/` 6 个 | ✅ `domain.py` | ✅ `repositories.py` (3) | ✅ 6 服务 | ✅ `MarketFacade` | ✅ 6 子 router + `aggregate.py` |
| `research` | ✅ `session_service.py` / `evidence_service.py` / `report_service.py` | ⬜ | ⬜ | ✅ 3 服务 | ✅ `ResearchFacade` | ✅ |
| `portfolio` | ✅ `service/` 3 个 (watchlist/holding/journal) | ⬜ | ⬜ | ✅ 3 服务 | ✅ `PortfolioFacade` | ✅ |
| `knowledge` | ✅ 单 Service（无拆分必要） | ⬜ | ⬜ | ✅ `knowledge_service` | ✅ `KnowledgeFacade` | ✅ |
| `document` | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ 仍用 `get_db` |
| `ai` | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ 仍用 `get_db` |
| `company` | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ 仍用 `get_db` |
| `dashboard` | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ 仍用 `get_db` |

> `research`/`portfolio`/`knowledge` 复用「Protocols + 容器 + Facade + routes 容器化」模式；其 Domain DTO / Repository 层是否引入视后续需要决定。

## 5. 迁移风险与应对
- **兼容性破坏**：在 `market/__init__.py` 保留旧函数的代理实现。
- **DI 循环依赖**：使用 Provider 的 lazy 初始化或 Factory 方式。
- **异常遗漏**：迁移完成后运行脚本搜索 `raise`，确保全部映射至 `DomainError`。
- **测试基准变更**：先保持旧返回结构，逐步改为 DTO 再更新测试。

## 6. 实施进度快照

### ✅ 已完成
- **market 域（阶段 1-4 全量）**：`market/service/`（6 个聚焦 Service）、`market/routes/`（6 子 router + `aggregate.py` + 聚合导出）、`market/domain.py`（`PriceEntry`/`FinancialMetricEntry`/`FreshnessEntry`/`MacroIndicatorEntry`）、`market/repositories.py`（`PriceRepository`/`FinancialRepository`/`FreshnessRepository`）、`market/service.py` deprecated shim、`MarketFacade` 兼容层。
- **DI 容器**：`core/container.py`（`Container` + `create_container`），懒加载 13 个服务属性；`core/database.py` 新增 `get_container` 依赖。
- **Protocols**：`core/interfaces.py` 新增 12 个域服务 Protocol（market 5 + research 3 + portfolio 3 + knowledge 1），容器懒加载 13 个服务属性（含 market `FreshnessService` 直接用具体类型）。
- **异常体系**：`core/exceptions.py` 定义 `AIResearchOSError` → `DomainError` 层级；`api/app.py` 注册 8 个 handler（`NotFoundError`/`ValidationError`/`DuplicateError`/`AuthenticationError`/`AuthorizationError`/`ExternalServiceError`/`AIResearchOSError`/`DomainError`）。全库 `raise` 扫描确认全部为结构化异常。
- **research 域**：3 个 Protocol + 容器注册 + `ResearchFacade` + routes 容器化。
- **portfolio 域**：`PortfolioService` 拆分为 `service/` 3 个子服务 + `PortfolioFacade` + 容器注册 + routes 容器化；`service/__init__.py` 保留 `PortfolioService` 后向兼容别名。
- **knowledge 域**：`KnowledgeService` Protocol + 容器注册 + `KnowledgeFacade` + routes 容器化。
- **测试基线**：全量 `91 passed / 7 failed`，7 个失败全部为环境依赖（6× market 依赖 akshare MySQL、1× knowledge 依赖 Ollama embedding），与重构前基线一致，无回归。

### 🔄 进行中
- **阶段 3/5 收尾**：`document` / `ai` / `company` / `dashboard` 4 个域仍用 `get_db` 直连，尚未接入容器（待 B7）。

### ⬜ 未开始
- **阶段 6（C8）**：配置 `[tool.mypy]`（当前仅 `[tool.ruff]`）、接入 pre-commit、完善单元测试覆盖。
- **环境依赖测试失败（非代码缺陷，需环境修复后归零）**：
  - 6× `test_market`：依赖 akshare MySQL 本地数据（600519/000001 等），需初始化对应标的本地 K 线/财务数据。
  - 1× `test_knowledge`：依赖本地 Ollama embedding 服务运行（未启动时 embedding 返回零向量 → 检索 count=0）。
- **发布收尾**：`refactor/vue3-rewrite` 分支尚未合并/创建 PR；周 8 任务（文档审查、PR 合并）待做。

## 7. 实施计划（原时间估算）
| 周 | 任务 | 状态 |
|----|------|------|
| 1 | 完成 `market` 子 Service 拆分、Interface、Router | ✅ |
| 2 | 实现 `market` Domain DTO 与 Repository | ✅ |
| 3 | 引入 DI 容器并迁移 `market` Service | ✅ |
| 4 | 统一 `market` 异常并注册 handler | ✅ |
| 5-6 | 在其他域复用相同模式 | 🔄 部分（research/portfolio/knowledge 完成，document/ai/company/dashboard 待接入） |
| 7 | 配置代码质量工具，完成全套测试 | ⬜ |
| 8 | 文档审查、PR 合并 | ⬜ |

## 8. 文档化与后续
- 本设计文档已提交至 `docs/superpowers/specs/2024-07-31-arch-optimisation-design.md`。
- 实现计划将通过 `writing-plans` skill 自动生成，并在 PR 中链接。
- CI 将在 PR 合并前检查设计文件是否为最新版本，防止实现脱离设计。

---

**结论**：通过 Service 颗粒化、Domain + Repository、统一 DI、异常层级化，实现 **更高的可维护性、可测试性和可扩展性**，并保持现有深模块优势。后续如需查看具体 Interface 定义或容器实现示例，请告知，我可以提供相应代码片段。