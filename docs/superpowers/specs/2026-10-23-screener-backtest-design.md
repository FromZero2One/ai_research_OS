# Screener 预设回测 MVP — 设计文档

日期：2026-10-23
状态：已与用户对齐（本文件内容即对齐结果）

## 意图与动机

Screener v1.5 预设库（5 套内置大师预设）已实跑通过，但预设的**历史有效性从未验证**。
回测回答两个问题：

1. **值不值得用**：年化收益/最大回撤/胜率，对比同期沪深300
2. **抓了哪些票**：逐年调仓明细，每年选出的公司与每只的持有期收益

## 目标

- 对单个预设跑 5 年期、季度调仓的历史回测
- 汇总指标 + 逐年明细，Markdown 报告落盘（与 screener 报告同风格）
- 后端 + 后台任务 + 报告；前端入口后补（非 MVP）

## 非目标 / 反目标

- 不做交易成本、滑点建模（报告显著注明"未计费用"）
- 不做参数网格优化
- 不做前端页面
- 不做 LLM 定性判断的历史复现（历史定性不可信，回测只用量化规则）

## 用户已确认的决策

| 决策 | 选择 |
|---|---|
| 产出 | 汇总 + 逐年明细两者都要 |
| 调仓频率 | 每季度（财报季结束后首个交易日） |
| 历史财务数据 | akshare 按需拉取（yjbb / F10 按期查询），入库后复用 |
| 历史日线 | 外部 MySQL `8.137.104.120:3306`（凭据只放 .env `BACKTEST_MYSQL_URL`，文档不带明文）只读源，首次灌入本地 `market.stock_prices` |
| 回测区间 | 5 年 |
| 产出形态 | 后端 + Markdown 报告，前端后补 |
| 历史市值 | 以外部库实际结构为准（已探明，见下） |

## 外部 MySQL 实际结构（2026-10-23 连库探明）

- `akshare.stock_history_daily_info_entity`：**1611 万行，全部为前复权（adjust='qfq'）**，
  1990-12-19 ~ 2026-06-05，5371 只票。列：symbol/date/open/close/high/low/volume/
  Trading_Value/Turnover_Rate 等。**无股本/市值列，有少量重复行**（同票同日多条）。
- `akshare.stock_value_entity`：仅 5000 行（单日 2025-09-25 快照），**无历史市值可用**。
- `akshare.stock_name_entity`：5386 只票名映射。

### 由此确定的决策

1. **复权**：外部库即前复权价，直接用 `close` 计算收益（除权除息已处理）
2. **历史市值**：外部库无历史股本 → 用 `买入日收盘价 × 当前总股本` 近似
   （总股本来自 `stock_value_entity`/akshare 现值），报告显著声明该近似；
   排名 tie-break 与市值规则均用此近似值
3. **去重**：灌库前按 (symbol, date) 去重 + 本地 `market.stock_prices` 增加
   (ticker, date) 唯一约束迁移（第二个迁移）
4. **调仓日 4-30 歧义**（年报与 Q1 同窗口披露）：统一用**年报**（报告期 N 的 Q4），
   即 4 月调仓只用上一年年报数据，不混用 Q1

## 核心流程

```
POST /api/v1/screener/backtests {preset_id, years=5}
  → ScreenerBacktestRun 落库（status=pending）+ TaskRecord 后台任务
  → worker：
     ① 数据准备（按需、幂等、入本地库）：
        a. 日线：外部 MySQL 拉回测区间内全 A 股日线 → market.stock_prices
        b. 财务：akshare yjbb/F10 按报告期拉 5 年内各期 → market.financial_metrics
        c. 基准：akshare 沪深300 指数日线 → 内存（不入 stock_prices）
     ② 调仓日序列：区间内每个财报披露截止日（4-30/8-31/10-31/次年4-30）后首个交易日
     ③ 每个调仓日（确定性，纯函数可单测）：
        - 取该日之前最近已披露报告期的财务指标（避免未来函数）
        - 复用 screening.evaluate_quant_rules + rank_candidates（limit=20，等权）
        - 该日收盘价买入，下一调仓日收盘价结算
     ④ 组装净值曲线 → 汇总指标 + 逐年明细
     ⑤ Markdown 报告落 screener/reports/backtest_<id>.md
```

## 关键设计决策

| 决策 | 默认 | 理由 |
|---|---|---|
| 调仓时点 | 财报披露截止日后首个交易日 | 保证财务数据"当时可见"，杜绝未来函数 |
| 选股财务期 | 调仓日前最近已披露完整报告期 | 同上 |
| 组合 | 规则通过者按 score→市值 取前 20 等权 | 与现网排名逻辑一致 |
| 停牌/退市 | 收盘价缺失 → 该票当期收益按 0 并在明细标注；连续缺失顺延 | MVP 简化 |
| ST 过滤 | MVP 不做（snapshot 名称含 ST 可后续加） | 先跑通 |
| 基准 | 沪深300（akshare `stock_zh_index_daily`，代码 sh000300） | 对比锚点 |
| candidate_limit | 20 | 20 只等权已够分散，降低计算量 |

## 汇总指标定义

- 累计收益、年化收益（CAGR）
- 最大回撤（按调仓日净值序列）
- 年度胜率（跑赢沪深300 的年度占比）
- 逐年超额收益

## 数据模型

新表 `screener.backtest_runs`（迁移）：

| 列 | 类型 | 说明 |
|---|---|---|
| id | uuid | PK |
| preset_id | uuid | 回测的预设 |
| years | int | 回测年数 |
| status | str | pending/running/completed/failed |
| error | text nullable | 失败信息 |
| result | json nullable | 汇总指标 + 逐年明细 |
| report_path | str nullable | 报告文件路径 |
| started_at / finished_at | str nullable | 时间戳 |

## 模块与文件

```
backend/screener/
  backtest.py          # 纯函数核心：调仓日生成、单期选股、收益计算、净值/指标
  backtest_data.py     # 数据准备：外部 MySQL 日线拉取灌库、akshare 历史财务按期拉取
  backtest_report.py   # Markdown 报告渲染
  backtest_service.py  # 编排：状态机 + 后台任务 handler
  models.py            # + ScreenerBacktestRun
backend/alembic/versions/xxxx_add_backtest_runs.py
backend/tests/test_screener_backtest*.py
```

外部 MySQL 连接：`settings.BACKTEST_MYSQL_URL`（.env 配置，默认空=禁用日线外部源）。

## 报告结构（Markdown）

```
# 预设回测报告：<预设名>（2021-10 ~ 2026-10）
## 概览
- 调仓次数 / 区间 / 组合规模 / 未计交易费用声明
## 汇总指标
- 累计收益 / 年化 / 最大回撤 / 年度胜率 / vs 沪深300
## 逐年明细
### 2021Q4 → 2022Q1
| 代码 | 名称 | 买入价 | 卖出价 | 收益 |
...
## 数据说明
- 财务数据按报告期、日线来源（前复权）、停牌处理方式
- 市值近似声明：买入日收盘价 × 当前总股本
- 幸存者偏差声明：已退市票可能不在数据源中
```

## 数据完整性守则（builder 必须遵守）

- 灌库前 (symbol, date) 去重；本地加 (ticker, date) 唯一约束
- 调仓日序列从 `market.stock_prices` 实际日期推导；日历为空 → 明确报错，不产出退化回测
- 外部 MySQL 走 `asyncio.to_thread` + 分块拉取 + connect_timeout；凭据仅存 .env
- 幸存者偏差与市值近似在报告显著声明

## 风险与已知简化

1. 停牌股按 0 收益处理会轻微低估策略（简化声明在报告）
2. 历史财务期"当时可见性"依赖披露截止日近似（真实披露日有早有晚，统一按截止日）
3. 外部 MySQL 为外部资源，不可用时回测降级为"本地已有日线"并在报告注明覆盖范围
