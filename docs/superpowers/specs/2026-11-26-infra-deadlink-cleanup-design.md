# 七次简化（infra 退役 + 死链清理）设计

> 日期：2026-11-26。前置：六次简化 `2026-11-26-deadweight-clear-analysis-quality-design.md`（已完成）。

## 用户诉求（记录原话精神）

「尽量简化系统和优化系统，不要增加额外功能。」本设计**只做减法和运行时稳固**，不加任何指标/预设/告警/导出/方法学改造。

## Goals / Non-goals / Anti-goals

- **Goals**：执行已立项的四次简化（task_manager/事件 API/DI 清理）；清理六次简化勘察中发现的死链路（估值分位死链、profile 摄取评估、company_tags 空壳、过时 openapi.json）；仓库卫生（根目录脚本归档）；运行时稳固（事件循环显式化、测试与 Ollama 解耦）。
- **Non-goals**：估值规则分位数化（方法学改造，另行立项）；回测市值修正；任何新端点/新字段。
- **Anti-goals**：删除仍被消费的代码；让 LLM/外部服务重新回到运行链路。

## Constraints

- 不 drop 表、不做删列迁移（删类留表模式）
- ruff 只跑改动文件；pytest 严格串行；提交信息先过目
- 零新增 LLM/akshare 真实调用

## 任务分解

### Task S1：四次简化落地（方案沿用 `2026-11-26-infra-retire-simplify-design.md`）

1. **task_manager 退役**：HTTP 触发选股（`screener/routes` 经 task_manager 投递 + `document/tasks.py` handler）改为 asyncio.create_task 后台直跑（与定时选股同模式）。删 `core/task_manager.py`、`document/tasks.py`；`core.task_records` 表进删类留表名单。注意「同一时间只允许一个进行中 run」的唯一索引兜底仍在 DB 层，不丢幂等。
2. **事件查询/清理 API 删除**：删 `core/event_routes.py`、`core/event_cleanup.py` 及 app 注册、container/interfaces 引用；`event_log` 写入（EventLogger）与 `event_log.py` 保留。
3. **DI 闲置 getter 清理**：逐个 grep container 的 10 个 getter，删除无调用方者（协议同步收缩）。

### Task S2：死链路清理

1. **估值分位死链**：删 `useValuationPercentile`（views/components 零消费）；删 ratio_service 的 valuation 分位方法与其路由；`market.valuation_history` 表保留（无喂数入口在跑，留待将来）。
2. **profile 链评估**：`useIngestProfile` 无视图消费 → 删 hook；`POST /profile/{ticker}/ingest` 若无后端内消费方 → 删端点与 service 摄取分支；`GET /info`、`GET /stock-profile` 按消费方逐个裁定（Company 表写入来源若只剩此链，需保留 ingest——裁定标准：删后 Company 行还有别的写入来源即删）。
3. **company_tags 空壳**：标签 CRUD 已删，删 ORM 类/schema/relationship；`company.company_tags` 表保留；`CompanyResponse.tags` 字段移除（前端接口同步）。
4. **`frontend/openapi.json` 删除**（手写调用，文件已过时）。

### Task S3：仓库卫生

- 根目录一次性脚本（check_pg*.py、ingest_*.py、get_main_board.py 等）→ `backend/tools/archive/`（与三次简化 15 个脚本同归宿）；确有运行价值的先 grep README 引用再归档。

### Task S4：运行时稳固（无功能变化）

1. 启动脚本（start-backend.ps1 / start-dev.cmd）显式设置事件循环策略（SelectorEventLoop），解除「必须 --reload 才不崩」的隐性依赖。
2. 测试与 Ollama 解耦：document/knowledge 的 4 个环境失败用例改用假向量（monkeypatch embedding），目标豁免清单清零或仅剩日期依赖 3 个。

## 验收标准

- 全量 pytest 无新增失败（4 个 Ollama 环境失败转绿为加分项）
- `npm run build` 绿
- git grep 无任何对已删符号的引用
- 文档（README×3/USAGE/ARCHITECTURE/memory）同步
