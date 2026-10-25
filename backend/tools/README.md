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
