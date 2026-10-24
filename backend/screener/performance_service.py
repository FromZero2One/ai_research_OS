"""推荐后表现服务 — 从运行推荐 + 日线计算 T+1 等权收益。"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.models import ScreenerJudgement, ScreenerRun
from screener.performance import compute_stock_performance, summarize


def _run_local_date(run: ScreenerRun) -> date | None:
    value = run.created_at
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone().date()


async def build_run_performance(
    db: AsyncSession, run_id: uuid.UUID | str
) -> dict:
    run = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.id == uuid.UUID(str(run_id))))
    ).scalar_one_or_none()
    if run is None:
        raise ValueError(f"运行不存在: {run_id}")

    run_date = _run_local_date(run)
    base = {
        "run_id": str(run.id),
        "run_created_at": run.created_at.isoformat() if run.created_at else None,
        "entry_rule": "T+1 收盘价（运行日之后首个交易日）",
        "status": run.status,
        "recommended_count": 0,
        "with_entry_price": 0,
        "summary": summarize([]),
        "stocks": [],
    }
    if run.status != "completed":
        return {**base, "message": "运行尚未完成，暂不能计算表现"}
    if run_date is None:
        return {**base, "message": "运行缺少创建时间"}

    from market.models import StockPrice

    judgements = (
        await db.execute(
            select(ScreenerJudgement).where(
                ScreenerJudgement.run_id == run.id,
                ScreenerJudgement.status == "ok",
                ScreenerJudgement.recommend.is_(True),
            )
        )
    ).scalars().all()
    if not judgements:
        return {**base, "message": "本次运行没有推荐股票"}

    tickers = [j.ticker for j in judgements]
    price_rows = (
        await db.execute(
            select(StockPrice.ticker, StockPrice.date, StockPrice.close)
            .where(
                StockPrice.ticker.in_(tickers),
                StockPrice.date >= run_date,
                StockPrice.close.is_not(None),
            )
            .order_by(StockPrice.ticker, StockPrice.date)
        )
    ).all()

    by_ticker: dict[str, list[tuple[date, float]]] = {}
    for ticker, day, close in price_rows:
        by_ticker.setdefault(ticker, []).append((day, float(close)))

    stocks: list[dict] = []
    for j in judgements:
        rows = by_ticker.get(j.ticker, [])
        # T+1：取运行日之后的首个有收盘价的交易日
        entry = next(((d, c) for d, c in rows if d > run_date), None)
        if entry is None:
            perf = compute_stock_performance(run_date, None, [])
            status = "no_entry_price"
        else:
            entry_date, entry_price = entry
            after = [(d, c) for d, c in rows if d >= entry_date]
            perf = compute_stock_performance(entry_date, entry_price, after)
            status = "ok"
        snapshot = j.snapshot or {}
        stocks.append(
            {
                "ticker": j.ticker,
                "name": j.name,
                "industry": snapshot.get("industry"),
                **perf,
                "status": status,
            }
        )

    return {
        **base,
        "recommended_count": len(judgements),
        "with_entry_price": sum(1 for s in stocks if s["status"] == "ok"),
        "summary": summarize(stocks),
        "stocks": stocks,
    }
