# backend/tools

数据采集工具，用于 AI Research OS 项目。

## 文件

| 文件 | 说明 |
|------|------|
| `ingest_main_board_batch.py` | 分批采集主板股票行情数据脚本（支持 `--shard i/n` 分片并行） |
| `ingest_recommended.py` | 补采历史上被选股推荐过的票（含 002/300/688 等主板清单外的票） |
| `run_backtest_queue.py` | 依次为 6 套内置预设排队跑回测（规避 409 并发限制，自动轮询结果） |
| `prefill_periods.py` | 预补全回测所需报告期的财务数据（yjbb + 资产负债表 + 现金流 + F10），并验证完整性 |
| `final_report.py` | 汇总最近 6 次回测：指标 + 逐期持仓数 + 分段稳健性 |
| `check_coverage.py` | 行情覆盖统计（行数 / ≥200 根票数 / 最新日期） |
| `check_period_completeness.py` | 各报告期财务指标完整性检查 |
| `check_tasks.py` | 后台任务队列表（`core.task_records`）状态 |
| `check_pg_activity.py` | PostgreSQL 活跃查询/锁等待诊断 |
| `check_universe.py` | 回测票池来源检查（活跃公司 vs 全市场） |
| `fetch_cninfo_reports.py` | **从巨潮资讯网批量下载年度报告 PDF**（按选股候选/指定运行） |
| `upload_reports.py` | 把下载的年报批量上传到文档中心并等待索引（自动关联公司） |
| `index_pending_parallel.py` | **并行索引所有未完成文档**（6 并发，绕过单线程任务队列；批量导入年报时用这个） |
| `reindex_pending_docs.py` | 把未索引文档重新排进任务队列（单线程，任务丢失时用） |
| `check_pending_docs.py` | 列出未索引文档 + 最近 `document_index` 任务状态 |
| `kb_status.py` | 知识库总览：文档数 / 已索引数 / 切片总数 |
| `check_kb_hit.py` | 检查某只票在知识库的检索命中（排查事实检查/深判证据） |
| `run_presets_live.py` | 按预设排队跑**实时选股**（规避 409，轮询并打印判定分布与推荐） |
| `list_presets.py` | 列出全部预设的量化规则与定性标准（排查标准可验证性） |
| `show_judgement.py` | 查看某次运行某只票的完整判定（verdict/置信度/逐条证据） |
| `confidence_dist.py` | 置信度分布（验证 LLM 自评是否退化成固定档位） |
| `run_status.py` | 最近选股运行状态（直连 PG，避免深判时 HTTP 大响应超时） |
| `screener_task_status.py` | `screener_run` 任务队列状态（含中断原因） |
| `reset_stuck_runs.py` | 复位崩溃残留的 running/judging 运行（`--apply`；同时把任务置 failed，避免重启自动重跑） |
| `recent_activity.py` | 最近 5/10 分钟事件与任务写入（判断深判是否还在推进） |

> 一次性/已弃用脚本（含 `cleanup_duplicate_tasks.py`、`rewrite_presets_qualitative.py`、`rule_sensitivity.py` 等）已移入 `archive/` 子目录，不在日常使用范围。
| `confidence_dist.py` | 置信度分布（验证 LLM 自评是否退化成固定档位） |
| `run_status.py` | 最近选股运行状态（直连 PG，避免深判时 HTTP 大响应超时） |
| `screener_task_status.py` | `screener_run` 任务队列状态（含中断原因） |
| `reset_stuck_runs.py` | 复位崩溃残留的 running/judging 运行（`--apply`；同时把任务置 failed，避免重启自动重跑） |
| `recent_activity.py` | 最近 5/10 分钟事件与任务写入（判断深判是否还在推进） |
| `main_board_stocks.csv` | 全市场主板股票列表（2,111 只，含沪市主板 1,700 只 + 深市主板 411 只） |

## 使用说明

### 前置条件

1. 后端服务已启动（`http://localhost:8000`）
2. PostgreSQL 已启动且可连接（默认 `localhost:5432/airesearch`）
3. 已安装 `psycopg2` 和 `requests`（backend `.venv` 中已包含）

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SCREENER_BACKEND_URL` | `http://localhost:8000` | 后端 API 地址 |
| `PG_HOST` | `localhost` | PostgreSQL 主机 |
| `PG_PORT` | `5432` | PostgreSQL 端口 |
| `PG_DB` | `airesearch` | 数据库名 |
| `PG_USER` | `airesearch` | 用户名 |
| `PG_PASSWORD` | `airesearch_dev` | 密码 |
| `INGEST_PROGRESS_FILE` | `./ingest_progress.csv` | 进度记录文件路径 |

### 命令

```powershell
# 从 backend 目录运行，每次采集前 10 只
cd backend
.venv\Scripts\python tools\ingest_main_board_batch.py --limit 10

# 采集全部待采集股票（会自动跳过已有数据的，支持中断恢复）
.venv\Scripts\python tools\ingest_main_board_batch.py

# 并行采集：3 个进程分片（各用独立进度文件 ingest_progress_shard{i}.csv，任务不重叠）
.venv\Scripts\python tools\ingest_main_board_batch.py --shard 0 --num-shards 3
.venv\Scripts\python tools\ingest_main_board_batch.py --shard 1 --num-shards 3
.venv\Scripts\python tools\ingest_main_board_batch.py --shard 2 --num-shards 3
```

### 主板股票列表来源

`main_board_stocks.csv` 通过 akshare 新浪源获取，包含 2,111 只主板股票（沪市主板 600/601/603/605 前缀，深市主板 000 前缀），已按 `pure_code`（纯 6 位代码）和 `板块` 分类。

数据已批量导入 `company.companies` 表（`is_active=false`, `priority=999`），可直接使用采集脚本拉取行情。

## 批量获取年报（巨潮资讯网）

用于给知识库/定性选股补年报，两个脚本配合使用，均幂等（重复运行不会重复下载/上传）。

### 1. 下载 PDF

```powershell
cd backend

# 默认：取最近一次 completed 选股运行的全部候选股票
.venv\Scripts\python tools\fetch_cninfo_reports.py

# 指定某次运行（run_id 见选股页/GET /api/v1/screener/runs）
.venv\Scripts\python tools\fetch_cninfo_reports.py a62a2cd7-3df2-4a30-8b0a-dda5ed4ce3c2
```

- 数据源：巨潮资讯网公告接口 `hisAnnouncement/query`（需 `orgId` 映射，脚本自动取 `szse_stock.json`）
- 只取**最新一期主年报**（排除摘要/英文版/更正/公告）
- 输出：`backend/data/uploads/kb/{ticker}_{年份}_annual.pdf` + `manifest.csv`（代码/名称/年份/标题/公告日/URL/大小）
- 已存在的 PDF 自动跳过；无年报（如新上市）会打印「无年报」跳过

### 2. 上传并建立索引

```powershell
# 全部上传（需后端在跑 + Ollama 提供 bge-m3 embedding）
.venv\Scripts\python tools\upload_reports.py

# 只传部分（PowerShell 会把未加引号的逗号拆成多个参数，务必加引号）
.venv\Scripts\python tools\upload_reports.py --tickers "600519,603893"
.venv\Scripts\python tools\upload_reports.py --limit 3
```

- 缺失的公司会自动补进 `company.companies`（`is_active=false`, `priority=999`），保证 `company_id` 关联
- `doc_type=annual_report`，标题 `{公司名} {年份}年年度报告`
- 同名文档已存在则跳过上传；上传后轮询 `/documents/{id}/status` 直到 `is_indexed=true`
- 索引耗时取决于 PDF 大小（100 页年报约 1-3 分钟；17MB 大文件更久）
- 批量导入几十份以上时，`upload_reports.py` 的轮询可能超时（单线程队列慢），此时用
  `tools\index_pending_parallel.py` 直接并行索引剩余文档

### 3. 批量索引加速（大批量导入必读）

```powershell
# 6 并发索引所有未索引文档（会先清空 pending 的 document_index 任务，避免重复）
.venv\Scripts\python tools\index_pending_parallel.py

# 查进度
.venv\Scripts\python tools\kb_status.py          # 总数 / 已索引 / 切片数
.venv\Scripts\python tools\check_pending_docs.py # 还有哪些没索引
```

- 必须从 `backend/` 运行；脚本会显式导入所有模块模型（否则跨 schema 外键解析失败）
- `OLLAMA_NUM_PARALLEL=4`（User 环境变量）可让 embedding 请求在 Ollama 端并行，实测 ~3.8 份/分钟
- embedding 批大小默认 64（`document/service.py: embed_chunks_safely`）
- 索引已幂等：重新索引会先删除旧切片与旧向量；PDF 文本中的 NUL 字节（`0x00`）会在入库前清洗

### 常见问题

- **接口返回 0 条**：巨潮查询必须用 `stock={code},{orgId}` 格式，只传代码不行
- **索引一直 false**：确认 `ollama list` 里有 `bge-m3:latest` 且 11434 端口可达（本机默认 localhost）
- **重复下载/上传**：脚本已做幂等；若想强制重来，删除对应 PDF 或 `document.documents` 中同名记录
- **PDF 合法性**：巨潮只提供公开披露文件，请自行遵守其使用条款

## 选股相关工具

```powershell
# 跑预设（可只跑指定预设；不带参数跑高成长/深度价值/金融价值）
.venv\Scripts\python tools\run_presets_live.py
.venv\Scripts\python tools\run_presets_live.py 9df4fd6f-b15e-4db2-a43c-048e09be1f36

# 查运行状态（直连 PG，深判期间也不会超时）
.venv\Scripts\python tools\run_status.py 3

# 看某只票的完整判定与逐条证据
.venv\Scripts\python tools\show_judgement.py <run_id> 002602

# 预设标准审计（只读查看；改写脚本已移入 archive/）
.venv\Scripts\python tools\list_presets.py
```

- 运行卡在 `judging`（后端崩溃/热重载导致）：`tools\reset_stuck_runs.py --apply` 复位。
  该脚本同时把 `screener_run` 任务置 `failed`，否则后端重启会「恢复」任务并自动重跑。
- 深判耗时参考（DeepSeek，46 只候选）：约 9–10 分钟；逐条检索上线后单只 +20~30%。
- `confidence` 是 LLM 自评、未校准；`tools\confidence_dist.py` 可看分布（当前集中在 0.95/0.92/0.85）。
- 2026-11-25 二次瘦身：回测不再走 API（引擎保留），排队回测统一用 `tools\run_backtest_queue.py`；`run_presets_live.py` 为预设实时选股的脚本入口。
