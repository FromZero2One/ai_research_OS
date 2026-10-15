# 设计文档：比率层 + PE/PB 历史分位 + 覆盖矩阵定性维度

- 日期：2026-10-15
- 状态：已确认（用户批准设计方向）
- 前置依据：memory/ai-research-os-session.md「下一步优先级」第 1、2 项；核心数据分工原则（2026-10-14 定稿）

## 0. 已确认的决策

| 决策点 | 结论 |
|--------|------|
| PE/PB 历史分位实现 | 落库 PG（按定稿方案），akshare 失败时允许空缺 |
| 前端展示位置 | 公司详情页（CompanyDetail）；报告上下文区块两处生效 |
| 覆盖矩阵定性判定标准 | 已索引文档 + 含 mda 或 risk 切片 → ok |
| 比率层适用范围 | A/HK/US 三市统一；PE/PB 分位仅 A 股 |
| 代码位置 | 新建 market/ratio_service.py（方案 A），不放 research 域 |

## 1. 比率层（后端）

### 1.1 纯函数

```
market/ratio_service.py
├── compute_ratios(metrics: list[FinancialMetricEntry]) -> list[RatioEntry]  # 纯函数
└── percentile_rank(series: list[float], value: float) -> float | None       # 纯函数
```

### 1.2 指标口径

- **派生**（由原始指标计算）：
  - 毛利率 = gross_profit / revenue × 100%
  - 净利率 = net_income / revenue × 100%
- **透出**（financial_metrics 已有原始值，直接带出）：
  - roe、debt_to_equity（注：A 股采集链路存的实为"资产负债率%"）、asset_turnover、inventory_turnover、receivables_turnover、current_ratio、quick_ratio、eps、market_cap
- **取数口径**：每期取该期全部指标；同一 ticker 多期并存时，优先 Annual，其次 Q4/Q3/Q2/Q1；展示最近 3 期
- **缺原料处理**：除零、原料指标缺失 → 该比率为 None，不猜测、不回退

## 2. PE/PB 历史分位（仅 A 股）

### 2.1 新表

```
market.valuation_history
├── ticker        String(16), index
├── trade_date    Date
├── pe            Float nullable
├── pe_ttm        Float nullable
├── pb            Float nullable
├── total_mv      Float nullable
└── 唯一约束：(ticker, trade_date)
```

Alembic 迁移：基于 head e8a2c4f6b9d1 新增一个 revision。

### 2.2 数据流

1. 首次访问：akshare `stock_a_indicator_lg` 子进程拉全历史序列（trade_date/pe/pe_ttm/pb/total_mv），批量入库（复用 run_akshare + build_akshare_env 模式，ticker 走环境变量）
2. 之后访问：直接查 PG 计算分位，不再调 akshare
3. akshare 失败 / venv 未配置：返回 `{available: false}`，不抛错；前端显示"无分位数据"
4. 增量更新：本期不做（历史估值序列变化极慢），后续可在调度中心补

### 2.3 分位算法

- `percentile_rank(series, value)`：value 在序列中小于等于它的比例（0~100）
- 边界：空序列 → None；单一值 → 50；value 超出序列范围 → 0 或 100
- 输出：pe / pe_ttm / pb 各自的当前值 + 历史分位 + 样本量 + 起止日期

## 3. API

| 路由 | 说明 |
|------|------|
| `GET /api/v1/market/ratios/{ticker}` | 最近 3 期比率列表（含派生+透出） |
| `GET /api/v1/market/ratios/{ticker}/valuation-percentile` | PE/PE-TTM/PB 当前值+历史分位（仅 A 股，非 A 股返回 available:false） |

- 新建 `market/routes/ratio_routes.py`，注册进 `backend/api/app.py`（第 16 个 router，前缀 /api/v1）
- schemas 加在 `market/schemas.py`，服务经 Container 装配（沿用现有模式）

## 4. 报告上下文区块

- `ratio_service.build_ratio_block(session: AsyncSession, ticker) -> str | None`
  - 生成 `## 财务比率与估值分位` 区块：比率表（最新期）+ PE/PB 分位（若有）
  - 数字标注报告期与口径，非 A 股或无数据时整块返回 None（不输出空区块）
- 接入点：`research/report_service.py` 约 218 行，peer_block 之后追加（与 period/peer block 并列）
- 报告 system prompt 不改：数字区块天然受"禁止改写数字"双轨规则约束

## 5. 前端（公司详情页）

- CompanyDetail.vue 财务区块旁新增"📊 比率与估值分位"卡片：
  - 左：比率表（近 3 期 × 指标）
  - 右：PE / PE-TTM / PB 当前值 + 百分位进度条（0-100%）
- `stores/api.ts` 新增 2 个 useQuery（无分位数据时卡片显示"无数据"态）

## 6. 覆盖矩阵定性维度

### 6.1 判定标准

对每家关注公司（company.companies.is_active=true）：

| 状态 | 条件 |
|------|------|
| ok | 存在 is_indexed=true 的文档，且其 chunks 中含 content_type ∈ {mda, risk} 的切片 |
| partial | 有已索引文档，但无 mda/risk 切片 |
| missing | 无已索引文档 |

### 6.2 实现

- `freshness_service.get_coverage_matrix` 每行新增 `qualitative` 字段；worst_health 计算纳入，映射沿用现有 `dt_priority` 严重度：qualitative missing → 视同 missing(3)，qualitative partial → 视同 warn(1)，qualitative ok → ok(0)，与量化维度取最严重者
- 查询方式：一次 join（documents × document_chunks，按 content_type 聚合）批量取全矩阵数据，避免 N+1
- 响应 counts 增加 `qualitative_ok`

### 6.3 前端

- Market.vue 覆盖矩阵卡片加"定性"列；grid 列数从硬编码 `repeat(4, 90px)` 改为随 data_types + 1 动态

## 7. 测试

| 对象 | 用例 |
|------|------|
| compute_ratios | 正常计算 / 缺原料 → None / 除零 → None / 多期并存取数口径 |
| percentile_rank | 空序列 / 单一值 / 边界值 / 正常分布 |
| 覆盖矩阵定性 | ok / partial / missing 三态 + worst_health 纳入（沿用现有 coverage 测试文件） |
| 回归 | pytest 全量（预存 4 败——Ollama embeddings——除外） |

## 8. 明确不做（本期范围外）

- 估值历史增量更新 / 定时刷新（挂调度中心，后续）
- 比率的同比环比趋势判断（只出数，解读留给报告 LLM）
- 港股/美股估值分位（无数据源）
- 证据继承、差异日报（优先级 3、4，挂起）
