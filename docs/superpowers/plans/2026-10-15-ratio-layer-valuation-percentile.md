# 比率层 + PE/PB 历史分位 + 覆盖矩阵定性维度 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Market 域新增财务比率层（派生毛利率/净利率等）与 A 股 PE/PB 历史分位（落库 PG），接入报告上下文与公司详情页；覆盖矩阵增加"定性覆盖"维度。

**Architecture:** 纯函数（compute_ratios / percentile_rank / build_percentile_result）可独立单测；RatioService 走"PG first，akshare 子进程兜底"模式（与 FinancialService 一致）；估值历史新表 `market.valuation_history`；报告区块照抄 period_compare 模式在 report_service 追加；覆盖矩阵在 get_coverage_matrix 内扩展 qualitative 字段。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic；Vue 3 + TanStack Vue Query；pytest（需 docker postgres）。

**Spec:** `docs/superpowers/specs/2026-10-15-ratio-layer-valuation-percentile-design.md`

## Global Constraints

- 全中文注释/UI
- Python 3.14 全局环境（无 .venv）；pytest 需先起 docker postgres（`docker/docker-compose.yml`）
- 测试库 airesearch_test 由 conftest create_all 重建：**新表自动创建；若发现列缺失需 DROP DATABASE airesearch_test 重建**
- Alembic 迁移基线 head：`e8a2c4f6b9d1`
- akshare 子进程：ticker 走环境变量（`AKSHARE_TICKER`），禁止内插进代码；输出用 `__R__:`/`__E__:` 协议
- ruff --fix 会删"当时未用"的 import，慎用
- 报告数字区块受"禁止改写"双轨规则约束（system prompt 不改，区块标题自带"禁止改写"字样）
- pytest 预存 4 败（无 Ollama embeddings）不算回归；前端验证用 `npm run build`（含 vue-tsc）
- 禁止做规格范围外的事（不做估值增量刷新调度、不做同比趋势判断、不做港美股分位）

---

### Task 1: 纯函数 compute_ratios + percentile_rank（TDD）

**Files:**
- Create: `backend/market/ratio_service.py`
- Test: `backend/tests/test_ratio_service.py`

**Interfaces:**
- Consumes: `market.domain.FinancialMetricEntry`（已有：fiscal_year/fiscal_period/metric_name/metric_value）
- Produces:
  - `compute_ratios(metrics: list[FinancialMetricEntry]) -> list[dict]`（每期一个 dict：fiscal_year/fiscal_period + 11 个比率键，按报告期倒序，Annual 优先于同年季度）
  - `percentile_rank(series: list[float], value: float | None) -> float | None`
  - `RATIO_LABELS: dict[str, str]`（比率键→中文标签）
  - `build_percentile_result(ticker: str, rows) -> dict`（Task 3 依赖）

- [ ] **Step 1: 写失败测试**

```python
"""比率层单测：纯函数 + 服务（PG 路径，子进程 mock）。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from market.domain import FinancialMetricEntry
from market.ratio_service import (
    RATIO_LABELS,
    compute_ratios,
    percentile_rank,
)


def _entry(year: int, period: str, name: str, value: float | None) -> FinancialMetricEntry:
    return FinancialMetricEntry(
        fiscal_year=year, fiscal_period=period, metric_name=name, metric_value=value
    )


def test_compute_ratios_derived():
    metrics = [
        _entry(2024, "Annual", "revenue", 1000.0),
        _entry(2024, "Annual", "gross_profit", 400.0),
        _entry(2024, "Annual", "net_income", 100.0),
        _entry(2024, "Annual", "roe", 12.5),
    ]
    out = compute_ratios(metrics)
    assert len(out) == 1
    r = out[0]
    assert r["fiscal_year"] == 2024 and r["fiscal_period"] == "Annual"
    assert r["gross_margin"] == 40.0
    assert r["net_margin"] == 10.0
    assert r["roe"] == 12.5
    assert r["eps"] is None  # 缺原料 → None


def test_compute_ratios_zero_division_and_missing():
    metrics = [_entry(2024, "Annual", "gross_profit", 400.0)]  # 无 revenue
    out = compute_ratios(metrics)
    assert out[0]["gross_margin"] is None
    out2 = compute_ratios([_entry(2024, "Annual", "revenue", 0.0), _entry(2024, "Annual", "gross_profit", 1.0)])
    assert out2[0]["gross_margin"] is None
    assert compute_ratios([]) == []


def test_compute_ratios_annual_drops_same_year_quarters():
    metrics = [
        _entry(2024, "Annual", "revenue", 1000.0),
        _entry(2024, "Q4", "revenue", 900.0),   # 同年 Q4 被 Annual 挤掉
        _entry(2024, "Q1", "revenue", 200.0),
        _entry(2024, "Q1", "gross_profit", 80.0),
    ]
    out = compute_ratios(metrics)
    assert [r["fiscal_period"] for r in out] == ["Annual", "Q1"]
    assert out[0]["gross_margin"] is None
    assert out[1]["gross_margin"] == 40.0


def test_compute_ratios_multi_period_order():
    metrics = [
        _entry(2023, "Annual", "revenue", 800.0),
        _entry(2023, "Annual", "net_income", 80.0),
        _entry(2024, "Annual", "revenue", 1000.0),
        _entry(2024, "Annual", "net_income", 100.0),
    ]
    out = compute_ratios(metrics)
    assert [r["fiscal_year"] for r in out] == [2024, 2023]


def test_percentile_rank():
    assert percentile_rank([], 10) is None
    assert percentile_rank([5.0], 5.0) == 50.0
    assert percentile_rank([1, 2, 3, 4, 5], 3) == 60.0
    assert percentile_rank([1, 2, 3], 100) == 100.0
    assert percentile_rank([1, 2, 3], None) is None
    assert percentile_rank([1.0, 2.0], 0.5) == 0.0


def test_ratio_labels_complete():
    assert set(RATIO_LABELS) == {
        "gross_margin", "net_margin", "roe", "debt_to_equity", "asset_turnover",
        "inventory_turnover", "receivables_turnover", "current_ratio",
        "quick_ratio", "eps", "market_cap",
    }
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend; python -m pytest tests/test_ratio_service.py -v`
Expected: FAIL（ModuleNotFoundError: market.ratio_service）

- [ ] **Step 3: 最小实现**

`backend/market/ratio_service.py`：

```python
"""比率层 — 财务比率派生 + A 股 PE/PB 历史分位。

纯函数（compute_ratios / percentile_rank / build_percentile_result）可独立单测；
RatioService 负责取数与缓存（PG first，akshare 子进程兜底）。
数字唯一事实源原则：原料只来自 market.financial_metrics / market.valuation_history，
不从文档/证据抽数。
"""

from __future__ import annotations

from market.domain import FinancialMetricEntry

# 比率键 → 中文标签（报告区块与前端共用）
RATIO_LABELS: dict[str, str] = {
    "gross_margin": "毛利率",
    "net_margin": "净利率",
    "roe": "ROE",
    "debt_to_equity": "资产负债率",
    "asset_turnover": "总资产周转率",
    "inventory_turnover": "存货周转率",
    "receivables_turnover": "应收账款周转率",
    "current_ratio": "流动比率",
    "quick_ratio": "速动比率",
    "eps": "每股收益",
    "market_cap": "总市值",
}

_PERIOD_RANK = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "Annual": 5}

# 透出类比率（financial_metrics 已有原始值，直接带出）
_PASSTHROUGH = (
    "roe", "debt_to_equity", "asset_turnover", "inventory_turnover",
    "receivables_turnover", "current_ratio", "quick_ratio", "eps", "market_cap",
)


def _metric_lookup(
    metrics: list[FinancialMetricEntry],
) -> dict[tuple[int, str], dict[str, float]]:
    """按 (年度, 报告期) 分组取第一个非空值（先到先得）。"""
    grouped: dict[tuple[int, str], dict[str, float]] = {}
    for m in metrics:
        if m.metric_value is None:
            continue
        grouped.setdefault((m.fiscal_year, m.fiscal_period), {}).setdefault(
            m.metric_name, m.metric_value
        )
    return grouped


def _dedup_periods(periods: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """同年并存 Annual 与季度时丢弃季度（Annual 即年报期末）。"""
    annual_years = {y for y, p in periods if p == "Annual"}
    return [(y, p) for y, p in periods if p == "Annual" or y not in annual_years]


def compute_ratios(metrics: list[FinancialMetricEntry]) -> list[dict]:
    """由财务指标派生比率；缺原料或除零 → None，不猜测。按报告期倒序返回全部期。"""
    grouped = _metric_lookup(metrics)
    periods = _dedup_periods(list(grouped))
    periods.sort(key=lambda p: (p[0], _PERIOD_RANK.get(p[1], 0)), reverse=True)

    out: list[dict] = []
    for year, period in periods:
        vals = grouped[(year, period)]
        revenue = vals.get("revenue")

        def _margin(numer: float | None) -> float | None:
            if numer is None or not revenue:
                return None
            return round(numer / revenue * 100, 4)

        row: dict = {
            "fiscal_year": year,
            "fiscal_period": period,
            "gross_margin": _margin(vals.get("gross_profit")),
            "net_margin": _margin(vals.get("net_income")),
        }
        row.update({k: vals.get(k) for k in _PASSTHROUGH})
        out.append(row)
    return out


def percentile_rank(series: list[float], value: float | None) -> float | None:
    """value 在序列中的百分位（<= value 的比例 × 100）。

    空序列或 value 为 None → None；单一值 → 50（无分布意义，取中性）。
    """
    if value is None or not series:
        return None
    if len(series) == 1:
        return 50.0
    return round(sum(1 for x in series if x <= value) / len(series) * 100, 1)


def build_percentile_result(ticker: str, rows) -> dict:
    """由估值历史序列（按 trade_date 升序）构建分位结果（纯函数）。

    rows 为含 trade_date/pe/pe_ttm/pb 属性的对象序列（ORM 行）。
    current 取最新交易日的值。
    """
    if not rows:
        return {"ticker": ticker, "available": False, "reason": "no_data"}
    latest = rows[-1]
    fields: dict[str, dict] = {}
    for field in ("pe", "pe_ttm", "pb"):
        series = [getattr(r, field) for r in rows if getattr(r, field) is not None]
        current = getattr(latest, field)
        fields[field] = {
            "current": current,
            "percentile": percentile_rank(series, current),
            "samples": len(series),
        }
    return {
        "ticker": ticker,
        "available": True,
        "trade_date": latest.trade_date.isoformat(),
        "start_date": rows[0].trade_date.isoformat(),
        **fields,
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend; python -m pytest tests/test_ratio_service.py -v`
Expected: 全 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/market/ratio_service.py backend/tests/test_ratio_service.py
git commit -m "feat: ratio layer pure functions - compute_ratios, percentile_rank"
```

---

### Task 2: ValuationHistory 模型 + 迁移 + Repository + conftest 清理表

**Files:**
- Modify: `backend/market/models.py`（文件末尾追加模型）
- Create: `backend/alembic/versions/f3a8c2e1b7d9_add_valuation_history.py`
- Modify: `backend/market/repositories.py`（末尾追加 Repository）
- Modify: `backend/tests/conftest.py:175-190`（ALL_TABLES 追加一行）
- Test: `backend/tests/test_ratio_service.py`（追加 DB 冒烟测试）

**Interfaces:**
- Produces:
  - 模型 `market.models.ValuationHistory`（ticker/trade_date/pe/pe_ttm/pb/total_mv，(ticker, trade_date) 唯一）
  - `market.repositories.ValuationRepository`：`get_for_ticker(ticker) -> list[ValuationHistory]`（按 trade_date 升序）、`upsert(ticker, rows: list[dict]) -> int`（rows 含 trade_date: date 与 pe/pe_ttm/pb/total_mv，跳过已存在日期）

- [ ] **Step 1: 模型 + Repository + conftest**

`backend/market/models.py` 需在 sqlalchemy import 行加入 `UniqueConstraint`，文件末尾追加：

```python
class ValuationHistory(Base, UUIDMixin, TimestampMixin):
    """个股估值历史（A 股，乐咕乐股 stock_a_indicator_lg 全序列）。

    用于 PE/PB 历史分位：首次访问经 akshare 子进程拉全量入库，之后只查 PG。
    """

    __tablename__ = "valuation_history"
    __table_args__ = (
        UniqueConstraint("ticker", "trade_date", name="uq_valuation_ticker_date"),
        {"schema": "market"},
    )

    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    pe: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_mv: Mapped[float | None] = mapped_column(Float, nullable=True)
```

`backend/market/repositories.py`：import 行加入 `ValuationHistory`，文件末尾追加：

```python
class ValuationRepository(DomainRepository[ValuationHistory]):
    """Persistence for A-stock valuation history (percentile source)."""

    model = ValuationHistory

    async def get_for_ticker(self, ticker: str) -> list[ValuationHistory]:
        stmt = (
            select(ValuationHistory)
            .where(ValuationHistory.ticker == ticker.upper())
            .order_by(ValuationHistory.trade_date)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(self, ticker: str, rows: list[dict]) -> int:
        """按 (ticker, trade_date) 插入不存在的行，返回插入数。"""
        if not rows:
            return 0
        ticker_upper = ticker.upper()
        dates = [r["trade_date"] for r in rows]
        existing = await self.session.execute(
            select(ValuationHistory.trade_date).where(
                ValuationHistory.ticker == ticker_upper,
                ValuationHistory.trade_date.in_(dates),
            )
        )
        existing_dates = set(existing.scalars().all())
        inserted = 0
        for r in rows:
            if r["trade_date"] in existing_dates:
                continue
            self.session.add(
                ValuationHistory(
                    ticker=ticker_upper,
                    trade_date=r["trade_date"],
                    pe=r.get("pe"),
                    pe_ttm=r.get("pe_ttm"),
                    pb=r.get("pb"),
                    total_mv=r.get("total_mv"),
                )
            )
            inserted += 1
        if inserted:
            await self.session.flush()
        return inserted
```

`backend/tests/conftest.py` ALL_TABLES 列表在 `"market.data_freshness",` 后加：

```python
    "market.valuation_history",
```

- [ ] **Step 2: 迁移文件**

`backend/alembic/versions/f3a8c2e1b7d9_add_valuation_history.py`：

```python
"""add market.valuation_history (PE/PB percentile source)

Revision ID: f3a8c2e1b7d9
Revises: e8a2c4f6b9d1
Create Date: 2026-10-15

比率层（2026-10-15）：A 股估值历史全序列入 PG，供 PE/PB 历史分位计算。
首次访问经 akshare 子进程（stock_a_indicator_lg）拉全量，之后只查 PG。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "f3a8c2e1b7d9"
down_revision: str | None = "e8a2c4f6b9d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "valuation_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("pe", sa.Float(), nullable=True),
        sa.Column("pe_ttm", sa.Float(), nullable=True),
        sa.Column("pb", sa.Float(), nullable=True),
        sa.Column("total_mv", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("ticker", "trade_date", name="uq_valuation_ticker_date"),
        schema="market",
    )
    op.create_index(
        "ix_market_valuation_history_ticker",
        "valuation_history",
        ["ticker"],
        schema="market",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_market_valuation_history_ticker",
        table_name="valuation_history",
        schema="market",
    )
    op.drop_table("valuation_history", schema="market")
```

- [ ] **Step 3: DB 冒烟测试（追加到 test_ratio_service.py）**

```python
from datetime import date

from market.models import ValuationHistory
from market.repositories import ValuationRepository


@pytest.mark.asyncio
async def test_valuation_repository_upsert_and_get(test_session: AsyncSession):
    repo = ValuationRepository(test_session)
    rows = [
        {"trade_date": date(2024, 1, 2), "pe": 10.0, "pe_ttm": 11.0, "pb": 1.2, "total_mv": 100.0},
        {"trade_date": date(2024, 1, 3), "pe": 10.5, "pe_ttm": 11.5, "pb": 1.3, "total_mv": 105.0},
    ]
    assert await repo.upsert("600000", rows) == 2
    # 重复 upsert 幂等
    assert await repo.upsert("600000", rows) == 0
    got = await repo.get_for_ticker("600000")
    assert len(got) == 2
    assert got[0].trade_date == date(2024, 1, 2)  # 升序
```

- [ ] **Step 4: 跑测试 + 开发库迁移**

Run: `cd backend; python -m pytest tests/test_ratio_service.py -v`
Expected: 全 PASS（新表由 create_all 自动建；若报"relation valuation_history不存在"先 DROP DATABASE airesearch_test 重建）

Run: `cd backend; python -m alembic upgrade head`
Expected: 迁移应用到开发库，head 变为 f3a8c2e1b7d9

- [ ] **Step 5: 提交**

```bash
git add backend/market/models.py backend/market/repositories.py backend/tests/conftest.py backend/alembic/versions/f3a8c2e1b7d9_add_valuation_history.py backend/tests/test_ratio_service.py
git commit -m "feat: valuation_history table + repository for PE/PB percentiles"
```

---

### Task 3: RatioService（取数 + akshare 兜底）+ 容器装配（TDD）

**Files:**
- Modify: `backend/market/ratio_service.py`（追加 RatioService 类与 akshare 采集码）
- Modify: `backend/core/container.py`
- Test: `backend/tests/test_ratio_service.py`（追加服务测试）

**Interfaces:**
- Consumes: Task 1 纯函数；Task 2 ValuationRepository；`market.repositories.FinancialRepository.get_for_ticker`；`market.akshare_executor.run_akshare/build_akshare_env/is_a_stock`
- Produces:
  - `RatioService(session).read_ratios(ticker: str, limit: int = 3) -> list[dict]`
  - `RatioService(session).valuation_percentile(ticker: str) -> dict`（非 A 股/no_data 时 `{"available": False, "reason": ...}`）
  - `Container.ratio_service` 属性（Task 4 路由依赖）

- [ ] **Step 1: 写失败测试（追加到 test_ratio_service.py）**

```python
from market.ratio_service import RatioService


@pytest.mark.asyncio
async def test_read_ratios_from_pg(test_session: AsyncSession):
    test_session.add_all(
        [
            FinancialMetric(ticker="600000", fiscal_year=2024, fiscal_period="Annual", metric_name="revenue", metric_value=1000.0),
            FinancialMetric(ticker="600000", fiscal_year=2024, fiscal_period="Annual", metric_name="gross_profit", metric_value=400.0),
            FinancialMetric(ticker="600000", fiscal_year=2023, fiscal_period="Annual", metric_name="revenue", metric_value=800.0),
        ]
    )
    await test_session.commit()
    out = await RatioService(test_session).read_ratios("600000")
    assert len(out) == 2
    assert out[0]["gross_margin"] == 40.0
    assert out[0]["fiscal_year"] == 2024  # 倒序


@pytest.mark.asyncio
async def test_valuation_percentile_from_pg(test_session: AsyncSession):
    test_session.add_all(
        [
            ValuationHistory(ticker="600000", trade_date=date(2024, 1, 2), pe=10.0, pe_ttm=11.0, pb=1.2),
            ValuationHistory(ticker="600000", trade_date=date(2024, 1, 3), pe=20.0, pe_ttm=21.0, pb=2.2),
        ]
    )
    await test_session.commit()
    out = await RatioService(test_session).valuation_percentile("600000")
    assert out["available"] is True
    assert out["pe"]["current"] == 20.0
    assert out["pe"]["percentile"] == 100.0
    assert out["pe"]["samples"] == 2


@pytest.mark.asyncio
async def test_valuation_percentile_non_a_stock(test_session: AsyncSession):
    out = await RatioService(test_session).valuation_percentile("AAPL")
    assert out == {"ticker": "AAPL", "available": False, "reason": "non_a_stock"}


@pytest.mark.asyncio
async def test_valuation_percentile_fetch_on_miss(monkeypatch: pytest.MonkeyPatch, test_session: AsyncSession):
    """PG 不足 2 行时走 akshare 采集（mock 子进程），入库后算分位。"""
    from datetime import datetime

    fake_stdout = (
        '__R__:[{"trade_date": "2024-01-02", "pe": 10.0, "pe_ttm": 11.0, "pb": 1.2, "total_mv": 100.0}, '
        '{"trade_date": "2024-01-03", "pe": 15.0, "pe_ttm": 16.0, "pb": 1.5, "total_mv": 110.0}]'
    )

    def _fake_run(code, env=None):
        return fake_stdout

    monkeypatch.setattr("market.akshare_executor.run_akshare", _fake_run)
    out = await RatioService(test_session).valuation_percentile("600000")
    assert out["available"] is True
    assert out["pe"]["current"] == 15.0
    assert out["pe"]["percentile"] == 100.0
    rows = await ValuationRepository(test_session).get_for_ticker("600000")
    assert len(rows) == 2  # 已入库


@pytest.mark.asyncio
async def test_valuation_percentile_fetch_failure(monkeypatch: pytest.MonkeyPatch, test_session: AsyncSession):
    """akshare 失败 → available False，不抛错。"""
    monkeypatch.setattr("market.akshare_executor.run_akshare", lambda code, env=None: None)
    out = await RatioService(test_session).valuation_percentile("600000")
    assert out["available"] is False
```

注意：测试文件顶部 import 需补 `from market.models import FinancialMetric`（Task 2 只加了 ValuationHistory）。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend; python -m pytest tests/test_ratio_service.py -v`
Expected: FAIL（ImportError: RatioService）

- [ ] **Step 3: 实现 RatioService**

`backend/market/ratio_service.py` 顶部补 import，末尾追加：

```python
from datetime import date as _date

from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from core.event_service import EventLogger
from market.akshare_executor import build_akshare_env, is_a_stock, run_akshare
from market.repositories import FinancialRepository, ValuationRepository

# A 股估值历史全序列（乐咕乐股），ticker 经环境变量传入
_A_VALUATION_HISTORY_CODE = """\
import json, os, sys
import akshare as ak
try:
    ticker = os.environ["AKSHARE_TICKER"]
    df = ak.stock_a_indicator_lg(symbol=ticker)
    if df is None or df.empty:
        print("__R__:[]")
    else:
        def _g(row, k):
            v = row.get(k)
            return float(v) if v is not None and v == v else None
        rows = []
        for _, row in df.iterrows():
            rows.append({
                "trade_date": str(row.get("trade_date"))[:10],
                "pe": _g(row, "pe"), "pe_ttm": _g(row, "pe_ttm"),
                "pb": _g(row, "pb"), "total_mv": _g(row, "total_mv"),
            })
        print("__R__:" + json.dumps(rows, ensure_ascii=False))
except Exception as e:
    print("__E__:" + str(e), file=sys.stderr)
"""


class RatioService:
    """比率层服务 — 财务比率（PG）+ A 股 PE/PB 历史分位（PG first，akshare 兜底）。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)
        self.financial_repo = FinancialRepository(session)
        self.valuation_repo = ValuationRepository(session)

    async def read_ratios(self, ticker: str, limit: int = 3) -> list[dict]:
        """最近 N 期财务比率（纯函数计算，原料只来自指标库）。"""
        metrics = await self.financial_repo.get_for_ticker(ticker.upper())
        return compute_ratios(metrics)[:limit]

    async def valuation_percentile(self, ticker: str) -> dict:
        """PE/PE-TTM/PB 历史分位（仅 A 股）。历史不足 2 行时先经 akshare 拉全量入库。"""
        ticker_upper = ticker.upper()
        if not is_a_stock(ticker):
            return {"ticker": ticker_upper, "available": False, "reason": "non_a_stock"}
        rows = await self.valuation_repo.get_for_ticker(ticker_upper)
        if len(rows) < 2:
            fetched = await self._fetch_valuation_history(ticker_upper)
            if fetched:
                await self.valuation_repo.upsert(ticker_upper, fetched)
                await self.events.record(
                    source="market",
                    event_type="valuation_history.ingested",
                    entity_type="valuation_history",
                    entity_id=ticker_upper,
                    payload={"count": len(fetched), "ticker": ticker_upper},
                )
                rows = await self.valuation_repo.get_for_ticker(ticker_upper)
        return build_percentile_result(ticker_upper, rows)

    async def _fetch_valuation_history(self, ticker: str) -> list[dict]:
        """akshare 子进程拉估值历史；失败返回 []（不抛错，分位退化为无数据）。"""
        import asyncio as _asyncio
        import json as _json

        try:
            stdout = await _asyncio.to_thread(run_akshare, _A_VALUATION_HISTORY_CODE, build_akshare_env(ticker))
        except Exception:
            return []
        if not stdout:
            return []
        for line in stdout.splitlines():
            if not line.startswith("__R__:"):
                continue
            try:
                raw = _json.loads(line[6:])
            except _json.JSONDecodeError:
                return []
            rows: list[dict] = []
            for r in raw:
                try:
                    trade_date = _date.fromisoformat(str(r.get("trade_date", ""))[:10])
                except ValueError:
                    continue
                rows.append(
                    {
                        "trade_date": trade_date,
                        "pe": r.get("pe"),
                        "pe_ttm": r.get("pe_ttm"),
                        "pb": r.get("pb"),
                        "total_mv": r.get("total_mv"),
                    }
                )
            return rows
        return []
```

注意 EventLogger.record 的实际签名以 `core/event_service.py` 为准（现有调用见 financial_service.py:123-129，保持同构）。若 monkeypatch 的 `market.akshare_executor.run_akshare` 因函数内 `from ... import run_akshare` 拿到旧引用而失效，改为 monkeypatch 模块属性并让 `_fetch_valuation_history` 在调用点引用模块（`from market import akshare_executor` 后用 `akshare_executor.run_akshare`），以测试实际通过为准。

`backend/core/container.py`：`__init__` 加 `self._ratio = None`，仿 freshness_service 加属性：

```python
    @property
    def ratio_service(self) -> "RatioService":
        if self._ratio is None:
            from market.ratio_service import RatioService

            self._ratio = RatioService(self.session)
        return self._ratio
```

（freshness_service 未走 Protocol，ratio 同样直接返回类；类型注解可用字符串或直接 import 类名。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend; python -m pytest tests/test_ratio_service.py -v`
Expected: 全 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/market/ratio_service.py backend/core/container.py backend/tests/test_ratio_service.py
git commit -m "feat: RatioService - ratios read + valuation percentile with akshare fallback"
```

---

### Task 4: 路由 + app 注册

**Files:**
- Create: `backend/market/routes/ratio_routes.py`
- Modify: `backend/api/app.py`（import 区 + include_router 区各一行）
- Test: `backend/tests/test_ratio_service.py`（追加 async_client 路由测试）

**Interfaces:**
- Consumes: `Container.ratio_service`（Task 3）
- Produces: `GET /api/v1/market/ratios/{ticker}`、`GET /api/v1/market/ratios/{ticker}/valuation-percentile`

- [ ] **Step 1: 写失败路由测试（追加）**

```python
@pytest.mark.asyncio
async def test_ratio_routes(async_client):
    from core.database import get_container  # noqa: F401  # conftest 已 override

    r1 = await async_client.get("/api/v1/market/ratios/600000")
    assert r1.status_code == 200
    assert r1.json() == {"ticker": "600000", "ratios": []}

    r2 = await async_client.get("/api/v1/market/ratios/600000/valuation-percentile")
    assert r2.status_code == 200
    # akshare 未配置时退化，不 5xx
    assert r2.json()["available"] in (True, False)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend; python -m pytest tests/test_ratio_service.py -v`
Expected: FAIL（404）

- [ ] **Step 3: 实现路由并注册**

`backend/market/routes/ratio_routes.py`：

```python
"""Ratio endpoints — 财务比率（近 N 期）+ A 股估值历史分位。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from core.container import Container
from core.database import get_container

router = APIRouter(prefix="/market/ratios", tags=["Market Center"])


@router.get("/{ticker}")
async def get_ratios(
    ticker: str,
    limit: int = Query(default=3, le=10, description="返回最近 N 期"),
    container: Container = Depends(get_container),
):
    """最近 N 期财务比率（派生毛利率/净利率 + 透出 ROE/资产负债率/周转率等）。"""
    ratios = await container.ratio_service.read_ratios(ticker, limit=limit)
    return {"ticker": ticker.upper(), "ratios": ratios}


@router.get("/{ticker}/valuation-percentile")
async def get_valuation_percentile(
    ticker: str,
    container: Container = Depends(get_container),
):
    """PE/PE-TTM/PB 历史分位（仅 A 股；无数据时 available=false，不报错）。"""
    return await container.ratio_service.valuation_percentile(ticker)
```

`backend/api/app.py`：import 区（market 路由按字母序处）加：

```python
from market.routes.ratio_routes import router as market_ratio_router
```

include_router 区（line 247-261 之间 market 系列处）加：

```python
    app.include_router(market_ratio_router, prefix="/api/v1")
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `cd backend; python -m pytest tests/test_ratio_service.py -v`
Expected: 全 PASS

Run: `cd backend; python -m pytest tests/ -x -q --deselect tests/test_knowledge.py -q 2>&1 | Select-String -Pattern "failed|passed"`
Expected: 仅预存 4 败（Ollama embeddings 相关），无新增失败

- [ ] **Step 5: 提交**

```bash
git add backend/market/routes/ratio_routes.py backend/api/app.py backend/tests/test_ratio_service.py
git commit -m "feat: market ratio endpoints - /market/ratios/{ticker}[/valuation-percentile]"
```

---

### Task 5: 报告区块 build_ratio_block + report_service 接入（TDD）

**Files:**
- Modify: `backend/market/ratio_service.py`（追加 build_ratio_block）
- Modify: `backend/research/report_service.py:209-218`（peer_block 之后追加）
- Test: `backend/tests/test_ratio_service.py`（追加）

**Interfaces:**
- Consumes: RatioService.read_ratios / valuation_percentile；company.models.Company
- Produces: `build_ratio_block(db: AsyncSession, company_id: uuid.UUID | None) -> str | None`（无公司/无数据 → None）

- [ ] **Step 1: 写失败测试（追加）**

```python
import uuid

from company.models import Company


@pytest.mark.asyncio
async def test_build_ratio_block_none_without_company(test_session: AsyncSession):
    from market.ratio_service import build_ratio_block

    assert await build_ratio_block(test_session, None) is None
    assert await build_ratio_block(test_session, uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_build_ratio_block_with_data(test_session: AsyncSession):
    from market.ratio_service import build_ratio_block

    company = Company(ticker="600000", name="测试银行", is_active=True)
    test_session.add(company)
    await test_session.flush()
    test_session.add_all(
        [
            FinancialMetric(ticker="600000", fiscal_year=2024, fiscal_period="Annual", metric_name="revenue", metric_value=1000.0),
            FinancialMetric(ticker="600000", fiscal_year=2024, fiscal_period="Annual", metric_name="gross_profit", metric_value=400.0),
            ValuationHistory(ticker="600000", trade_date=date(2024, 1, 2), pe=10.0, pe_ttm=11.0, pb=1.2),
            ValuationHistory(ticker="600000", trade_date=date(2024, 1, 3), pe=20.0, pe_ttm=21.0, pb=2.2),
        ]
    )
    await test_session.commit()
    block = await build_ratio_block(test_session, company.id)
    assert block is not None
    assert "财务比率" in block
    assert "毛利率" in block and "40" in block
    assert "禁止改写" in block
    assert "分位" in block and "100" in block
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend; python -m pytest tests/test_ratio_service.py -v -k block`
Expected: FAIL（ImportError: build_ratio_block）

- [ ] **Step 3: 实现**

`backend/market/ratio_service.py` 末尾追加：

```python
async def build_ratio_block(db: AsyncSession, company_id) -> str | None:
    """报告上下文区块：财务比率（最新期）+ PE/PB 分位（A 股）。无数据返回 None。"""
    if not company_id:
        return None
    from company.models import Company

    company = (
        await db.execute(sa_select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if not company or not company.ticker:
        return None

    svc = RatioService(db)
    lines: list[str] = []

    ratios = await svc.read_ratios(company.ticker, limit=1)
    if ratios:
        r = ratios[0]
        parts = [
            f"{RATIO_LABELS[k]} {v:g}"
            for k, v in r.items()
            if k not in ("fiscal_year", "fiscal_period") and v is not None
        ]
        if parts:
            lines.append(
                f"## 财务比率（{r['fiscal_year']} {r['fiscal_period']}，"
                f"来源 Market 指标库，禁止改写）\n" + "；".join(parts)
            )

    vp = await svc.valuation_percentile(company.ticker)
    if vp.get("available"):
        vp_parts = [
            f"{k.upper()} 当前 {v['current']:g}，历史分位 {v['percentile']:g}%（样本 {v['samples']}）"
            for k, v in vp.items()
            if k in ("pe", "pe_ttm", "pb")
            and v.get("current") is not None
            and v.get("percentile") is not None
        ]
        if vp_parts:
            lines.append(
                f"## 估值历史分位（截至 {vp['trade_date']}，来源 Market 估值库，禁止改写）\n"
                + "；".join(vp_parts)
            )

    return "\n\n".join(lines) if lines else None
```

`backend/research/report_service.py` 在 peer_block 追加块之后（line 218 后）加：

```python
        # 比率层 + 估值分位（Market 数字事实源，同 period/peer block 模式）
        from market.ratio_service import build_ratio_block

        if ratio_block := await build_ratio_block(self.session, session.company_id):
            context_parts.append(f"\n{ratio_block}")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend; python -m pytest tests/test_ratio_service.py tests/test_research.py -v`
Expected: 全 PASS（test_research.py 无回归）

- [ ] **Step 5: 提交**

```bash
git add backend/market/ratio_service.py backend/research/report_service.py backend/tests/test_ratio_service.py
git commit -m "feat: ratio block in report context (dual-track market numbers)"
```

---

### Task 6: 覆盖矩阵定性维度（后端，TDD）

**Files:**
- Modify: `backend/market/service/freshness_service.py`（get_coverage_matrix）
- Test: `backend/tests/test_freshness_coverage.py`（追加 3 态用例）

**Interfaces:**
- Produces: 矩阵每行新增 `row["qualitative"] = {"health": "ok"|"partial"|"missing", "has_mda_risk": bool}`；counts 新增 `qualitative_ok`；worst_health 纳入定性（partial→warn 级、missing→missing 级，沿用 dt_priority）

- [ ] **Step 1: 写失败测试（追加到 test_freshness_coverage.py）**

```python
from document.models import Document, DocumentChunk


async def _seed_docs(session: AsyncSession, ticker_ties: dict[str, list[Company]]) -> dict[str, Company]:
    """建公司并返回 ticker→Company 映射（供测试关联 document.company_id）。"""
    for companies in ticker_ties.values():
        session.add_all(companies)
    await session.flush()
    return {c.ticker: c for companies in ticker_ties.values() for c in companies}


@pytest.mark.asyncio
async def test_coverage_qualitative_three_states(test_session: AsyncSession):
    """ok=已索引+mda/risk；partial=已索引但无 mda/risk；missing=无文档。"""
    c_ok = Company(ticker="QOK", name="定性全", is_active=True)
    c_part = Company(ticker="QPART", name="定性半", is_active=True)
    c_none = Company(ticker="QNONE", name="定性无", is_active=True)
    by_ticker = await _seed_docs(test_session, {"x": [c_ok, c_part, c_none]})

    d1 = Document(title="年报", doc_type="pdf", company_id=by_ticker["QOK"].id, is_indexed=True)
    d1.chunks = [
        DocumentChunk(chunk_index=0, content="管理层讨论", content_type="mda"),
        DocumentChunk(chunk_index=1, content="其他", content_type="other"),
    ]
    d2 = Document(title="公告", doc_type="pdf", company_id=by_ticker["QPART"].id, is_indexed=True)
    d2.chunks = [DocumentChunk(chunk_index=0, content="公告正文", content_type="other")]
    test_session.add_all([d1, d2])
    await test_session.commit()

    result = await FreshnessService(test_session).get_coverage_matrix()
    qual = {r["ticker"]: r["qualitative"]["health"] for r in result["rows"]}
    assert qual["QOK"] == "ok"
    assert qual["QPART"] == "partial"
    assert qual["QNONE"] == "missing"
    assert result["counts"]["qualitative_ok"] == 1


@pytest.mark.asyncio
async def test_coverage_qualitative_not_indexed_is_missing(test_session: AsyncSession):
    """有文档但未索引（is_indexed=False）→ missing。"""
    c = Company(ticker="QNIDX", name="未索引", is_active=True)
    by_ticker = await _seed_docs(test_session, {"x": [c]})
    test_session.add(
        Document(title="草稿", doc_type="pdf", company_id=by_ticker["QNIDX"].id, is_indexed=False)
    )
    await test_session.commit()

    result = await FreshnessService(test_session).get_coverage_matrix()
    row = next(r for r in result["rows"] if r["ticker"] == "QNIDX")
    assert row["qualitative"]["health"] == "missing"


@pytest.mark.asyncio
async def test_coverage_qualitative_missing_worst(test_session: AsyncSession):
    """量化全 ok 但定性 missing → worst_health=missing。"""
    c = Company(ticker="QWORST", name="定性缺口", is_active=True)
    await _seed_docs(test_session, {"x": [c]})
    now = datetime.now(UTC)
    for dt in ("prices", "financials", "profile", "news"):
        test_session.add(DataFreshness(ticker="QWORST", data_type=dt, checked_at=now, status="ok"))
    await test_session.commit()

    result = await FreshnessService(test_session).get_coverage_matrix()
    row = next(r for r in result["rows"] if r["ticker"] == "QWORST")
    assert row["qualitative"]["health"] == "missing"
    assert row["worst_health"] == "missing"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend; python -m pytest tests/test_freshness_coverage.py -v`
Expected: FAIL（KeyError: 'qualitative'）

- [ ] **Step 3: 实现**

`backend/market/service/freshness_service.py` 的 `get_coverage_matrix` 中，`records = await self.get_freshness(...)` 之前插入：

```python
        # 定性覆盖：已索引文档 + 含 mda/risk 切片 → ok；仅已索引 → partial；无 → missing
        from sqlalchemy import func

        from document.models import Document, DocumentChunk

        indexed_ids = {
            row[0]
            for row in (
                await self.session.execute(
                    sa_select(Document.company_id)
                    .where(Document.is_indexed.is_(True), Document.company_id.isnot(None))
                    .distinct()
                )
            ).all()
        }
        mda_risk_ids = {
            row[0]
            for row in (
                await self.session.execute(
                    sa_select(Document.company_id)
                    .join(DocumentChunk, DocumentChunk.document_id == Document.id)
                    .where(
                        Document.is_indexed.is_(True),
                        Document.company_id.isnot(None),
                        DocumentChunk.content_type.in_(["mda", "risk"]),
                    )
                    .distinct()
                )
            ).all()
        }

        def _qual_health(cid) -> str:
            if cid in mda_risk_ids:
                return "ok"
            if cid in indexed_ids:
                return "partial"
            return "missing"
```

行循环内（cells 组装后）加：

```python
            qual = _qual_health(c.id)
            qual_rank = {"ok": dt_priority("ok"), "partial": dt_priority("warn"), "missing": dt_priority("missing")}[qual]
```

worst 计算后（rows.append 前）加：

```python
            if qual_rank > dt_priority(worst):
                worst = "warn" if qual == "partial" else "missing"
```

rows.append 的 dict 加两处：

```python
                    "qualitative": {"health": qual, "has_mda_risk": qual == "ok"},
```

counts 返回 dict 加：

```python
                "qualitative_ok": sum(1 for r in rows if r["qualitative"]["health"] == "ok"),
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend; python -m pytest tests/test_freshness_coverage.py tests/test_market.py -v`
Expected: 全 PASS（旧用例不回归——它们断言的键仍在）

- [ ] **Step 5: 提交**

```bash
git add backend/market/service/freshness_service.py backend/tests/test_freshness_coverage.py
git commit -m "feat: qualitative coverage dimension in coverage matrix (mda/risk indexed)"
```

---

### Task 7: 前端 hooks + CompanyDetail 比率卡片

**Files:**
- Modify: `frontend/src/stores/api.ts`（282 行 CoverageMatrix 类型附近 + market hooks 区追加）
- Modify: `frontend/src/views/CompanyDetail.vue`（财务数据 tab）

**Interfaces:**
- Consumes: Task 4 两个 GET 端点
- Produces: `useRatios(ticker)`、`useValuationPercentile(ticker)`；`CoverageRow` 类型扩展 `qualitative`

- [ ] **Step 1: api.ts 追加 hooks**

在 `useCoverageMatrix`（约 283 行）附近，先给现有 `CoverageRow` 接口补可选字段（找到该 interface 定义处）：

```ts
export interface CoverageRow {
  ticker: string
  name: string
  cells: Record<string, { health: string; age_hours?: number; checked_at?: string; record_count?: number | null }>
  missing: string[]
  worst_health: string
  qualitative?: { health: 'ok' | 'partial' | 'missing'; has_mda_risk: boolean }
}
```

在 `useFinancialMetrics`（约 294 行）后追加：

```ts
export interface RatioPeriod {
  fiscal_year: number
  fiscal_period: string
  gross_margin: number | null
  net_margin: number | null
  roe: number | null
  debt_to_equity: number | null
  asset_turnover: number | null
  inventory_turnover: number | null
  receivables_turnover: number | null
  current_ratio: number | null
  quick_ratio: number | null
  eps: number | null
  market_cap: number | null
}

export interface PercentileField { current: number | null; percentile: number | null; samples: number }
export interface ValuationPercentile {
  available: boolean
  reason?: string
  trade_date?: string
  start_date?: string
  pe?: PercentileField
  pe_ttm?: PercentileField
  pb?: PercentileField
}

export function useRatios(ticker: MaybeRefOrGetter<string>) {
  return useGet<{ ticker: string; ratios: RatioPeriod[] }>(
    computed(() => ['ratios', toValue(ticker)]),
    computed(() => (toValue(ticker) ? `/market/ratios/${toValue(ticker)}` : '')),
  )
}

export function useValuationPercentile(ticker: MaybeRefOrGetter<string>) {
  return useGet<ValuationPercentile>(
    computed(() => ['valuation-percentile', toValue(ticker)]),
    computed(() => (toValue(ticker) ? `/market/ratios/${toValue(ticker)}/valuation-percentile` : '')),
  )
}
```

（`computed`/`toValue` 等已在该文件 import；若缺按现有文件头补。）

- [ ] **Step 2: CompanyDetail.vue 加卡片**

script 部分（line 38 `useFinancialMetrics` 附近）加：

```ts
import { useRatios, useValuationPercentile } from '@/stores/api'

const { data: ratioData } = useRatios(ticker)
const { data: vp } = useValuationPercentile(ticker)
const ratios = computed(() => ratioData.value?.ratios || [])
const ratioRows: { key: keyof RatioPeriod; label: string; fmt?: (v: number) => string }[] = [
  { key: 'gross_margin', label: '毛利率', fmt: (v) => v.toFixed(1) + '%' },
  { key: 'net_margin', label: '净利率', fmt: (v) => v.toFixed(1) + '%' },
  { key: 'roe', label: 'ROE', fmt: (v) => v.toFixed(1) + '%' },
  { key: 'debt_to_equity', label: '资产负债率', fmt: (v) => v.toFixed(1) + '%' },
  { key: 'asset_turnover', label: '总资产周转率', fmt: (v) => v.toFixed(2) },
  { key: 'current_ratio', label: '流动比率', fmt: (v) => v.toFixed(2) },
  { key: 'quick_ratio', label: '速动比率', fmt: (v) => v.toFixed(2) },
  { key: 'eps', label: 'EPS', fmt: (v) => v.toFixed(2) },
]
const vpFields = computed(() =>
  vp.value?.available
    ? (['pe', 'pe_ttm', 'pb'] as const)
        .filter((k) => vp.value![k])
        .map((k) => ({ key: k, label: { pe: 'PE', pe_ttm: 'PE-TTM', pb: 'PB' }[k] }))
    : [],
)
```

template：财务数据 tab 的 FinancialBars 卡片网格之后（约 line 200）加：

```vue
<el-card shadow="never" class="mt-4">
  <template #header>📊 比率与估值分位</template>
  <el-table v-if="ratios.length" :data="ratios" size="small" style="width:100%">
    <el-table-column label="报告期" width="100">
      <template #default="{ row }">{{ row.fiscal_year }} {{ row.fiscal_period }}</template>
    </el-table-column>
    <el-table-column v-for="r in ratioRows" :key="r.key" :label="r.label" align="right">
      <template #default="{ row }">{{ row[r.key] != null ? r.fmt!(row[r.key]) : '—' }}</template>
    </el-table-column>
  </el-table>
  <el-empty v-else description="暂无比率数据（需先采集财务）" :image-size="60" />
  <div v-if="vpFields.length" class="vp-grid mt-4">
    <div v-for="f in vpFields" :key="f.key">
      <div class="text-xs text-secondary">{{ f.label }} · {{ vp![f.key]!.samples }} 样本（{{ vp!.trade_date }}）</div>
      <div class="font-medium">{{ vp![f.key]!.current ?? '—' }}</div>
      <el-progress :percentage="vp![f.key]!.percentile ?? 0" :stroke-width="8" :format="(p: number) => p.toFixed(0) + '%' " />
    </div>
  </div>
  <div v-else class="text-xs text-secondary mt-2">估值历史分位无数据（仅 A 股可用）</div>
</el-card>
```

style 区追加：

```css
.vp-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
```

- [ ] **Step 3: 类型检查 + 构建验证**

Run: `cd frontend; npm run build`
Expected: vue-tsc 0 error、vite build 成功

- [ ] **Step 4: 提交**

```bash
git add frontend/src/stores/api.ts frontend/src/views/CompanyDetail.vue
git commit -m "feat(frontend): ratio & valuation percentile card on company detail"
```

---

### Task 8: Market.vue 覆盖矩阵定性列

**Files:**
- Modify: `frontend/src/views/Market.vue`（矩阵卡片约 88-103 行 + CSS 158-162 行）

**Interfaces:**
- Consumes: 后端 coverage 响应新字段 qualitative / counts.qualitative_ok（Task 6）；api.ts CoverageRow.qualitative（Task 7）

- [ ] **Step 1: 模板改动**

header 行（line 89 附近）的统计串加"定性覆盖"：

```vue
<span class="text-xs text-secondary">{{ coverage.counts.companies }} 家关注 · 全覆盖 {{ coverage.counts.fully_covered }} · 缺口 {{ coverage.counts.with_gaps }} · 过期 {{ coverage.counts.stale }} · 定性 {{ coverage.counts.qualitative_ok }}</span>
```

表头行（line 92-93）在 v-for dt 之后加一列：

```vue
<span class="c-cell">定性</span>
```

数据行（line 95-97）在 v-for dt cell 之后加：

```vue
<span class="c-cell" :style="{ color: qualColor(row.qualitative?.health) }">{{ qualLabel(row.qualitative?.health) }}</span>
```

script 加两个辅助函数：

```ts
const qualLabel = (h?: string) => ({ ok: '✅', partial: '⚠️', missing: '❌' } as Record<string, string>)[h || 'missing'] ?? '❌'
const qualColor = (h?: string) => ({ ok: '#34d399', partial: 'var(--warning)', missing: '#f87171' } as Record<string, string>)[h || 'missing'] ?? '#f87171'
```

- [ ] **Step 2: CSS 改动**

`.coverage-row` 的 `grid-template-columns: 1fr repeat(4, 90px)` 改为：

```css
.coverage-row { display: grid; grid-template-columns: 1fr repeat(5, 90px); align-items: center; gap: 8px; padding: 6px 10px; border-radius: 8px; cursor: pointer; }
```

- [ ] **Step 3: 类型检查 + 构建**

Run: `cd frontend; npm run build`
Expected: 0 error

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/Market.vue
git commit -m "feat(frontend): qualitative column in coverage matrix"
```

---

### Task 9: 文档同步 + 全量回归

**Files:**
- Modify: `backend/README.md`（数据库表清单 / API 约定处）
- Modify: `USAGE.md`（4.2 公司中心 / 4.3 市场中心 功能描述）
- Modify: `memory/ai-research-os-session.md`（变更日志 + 下一步优先级勾掉 1、2）

- [ ] **Step 1: 全量后端回归**

Run: `cd backend; python -m pytest tests/ -q 2>&1 | Select-String -Pattern "failed|passed"`
Expected: 与基线一致——仅预存 Ollama embeddings 相关失败，无新增

- [ ] **Step 2: 文档更新**

- `backend/README.md`「数据库」小节：market schema 表清单加 `valuation_history`（估值历史，PE/PB 分位源）
- `USAGE.md` 4.2 公司中心：财务数据 tab 提及"比率与估值分位卡片"；4.3 市场中心：覆盖矩阵提及"定性覆盖维度（年报正文 mda/risk）"，API 清单加 `/market/ratios/{ticker}` 与 `/market/ratios/{ticker}/valuation-percentile`
- `memory/ai-research-os-session.md`：变更日志加本次条目；「下一步优先级」勾掉第 1、2 项并标注迁移新 head `f3a8c2e1b7d9`

- [ ] **Step 3: 提交**

```bash
git add backend/README.md USAGE.md memory/ai-research-os-session.md
git commit -m "docs: sync ratio layer, valuation percentile, qualitative coverage"
```

---

## Self-Review 记录

- 规格覆盖：比率层（Task 1/3/4/5/7）、PE/PB 分位（Task 2/3/4/7）、覆盖矩阵定性（Task 6/8）、报告区块（Task 5）、文档（Task 9）——无缺口
- 类型一致性：build_percentile_result / ValuationRepository.upsert / read_ratios 签名在各 Task 间已对齐；qualitative 字段名前后端一致
- 占位符：无 TBD/TODO；所有代码步骤给出完整代码
- 已知风险：EventLogger.record 签名以 core/event_service.py 实际为准（Task 3 注明）；monkeypatch run_akshare 需注意函数内 import 引用（Task 3 注明处理方式）
