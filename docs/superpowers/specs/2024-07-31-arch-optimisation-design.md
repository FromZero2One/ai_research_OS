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
1. **阶段 1** – 拆分 `market` 子 Service 与 Interface、Router。保留 `MarketFacade` 兼容旧调用。
2. **阶段 2** – 实现 Domain DTO 与 Repository，Service 改为使用 DTO。
3. **阶段 3** – 引入 DI 容器，所有 Service 通过容器获取依赖。
4. **阶段 4** – 统一异常为 `DomainError` 系列并注册 handler。
5. **阶段 5** – 将相同模式推广至 `research`, `portfolio`, `knowledge` 等域。
6. **阶段 6** – 配置 `ruff`/`mypy`/`pre‑commit`，完善单元测试覆盖。

## 5. 迁移风险与应对
- **兼容性破坏**：在 `market/__init__.py` 保留旧函数的代理实现。
- **DI 循环依赖**：使用 Provider 的 lazy 初始化或 Factory 方式。
- **异常遗漏**：迁移完成后运行脚本搜索 `raise`，确保全部映射至 `DomainError`。
- **测试基准变更**：先保持旧返回结构，逐步改为 DTO 再更新测试。

## 6. 实施计划（时间估算）
| 周 | 任务 |
|----|------|
| 1 | 完成 `market` 子 Service 拆分、Interface、Router |
| 2 | 实现 `market` Domain DTO 与 Repository |
| 3 | 引入 DI 容器并迁移 `market` Service |
| 4 | 统一 `market` 异常并注册 handler |
| 5‑6 | 在其他域复用相同模式 |
| 7 | 配置代码质量工具，完成全套测试 |
| 8 | 文档审查、PR 合并 |

## 7. 文档化与后续
- 本设计文档已提交至 `docs/superpowers/specs/2024-07-31-arch-optimisation-design.md`。
- 实现计划将通过 `writing-plans` skill 自动生成，并在 PR 中链接。
- CI 将在 PR 合并前检查设计文件是否为最新版本，防止实现脱离设计。

---

**结论**：通过 Service 颗粒化、Domain + Repository、统一 DI、异常层级化，实现 **更高的可维护性、可测试性和可扩展性**，并保持现有深模块优势。后续如需查看具体 Interface 定义或容器实现示例，请告知，我可以提供相应代码片段。