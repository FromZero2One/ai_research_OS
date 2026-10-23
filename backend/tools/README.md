# backend/tools

数据采集工具，用于 AI Research OS 项目。

## 文件

| 文件 | 说明 |
|------|------|
| `ingest_main_board_batch.py` | 分批采集主板股票行情数据脚本 |
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
```

### 主板股票列表来源

`main_board_stocks.csv` 通过 akshare 新浪源获取，包含 2,111 只主板股票（沪市主板 600/601/603/605 前缀，深市主板 000 前缀），已按 `pure_code`（纯 6 位代码）和 `板块` 分类。

数据已批量导入 `company.companies` 表（`is_active=false`, `priority=999`），可直接使用采集脚本拉取行情。
