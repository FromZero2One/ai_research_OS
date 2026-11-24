# ruff: noqa: E501
"""批量导入真实行情数据（直接写入数据库，绕过API层）"""

import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select

from core.database import async_session_factory
from core.logging import configure_logging, logger
from market.models import StockPrice


def fetch_yfinance(ticker: str, years: float = 1):
    """同步抓取 yfinance 数据"""
    import yfinance as yf

    periods = {1: "1y", 2: "2y", 0.5: "6mo", 0.25: "3mo"}
    period = periods.get(years, "1y")

    stock = yf.Ticker(ticker)
    hist = stock.history(period=period)

    results = []
    for idx, row in hist.iterrows():
        close = float(row["Close"])
        if close != close:  # NaN check
            continue
        results.append(
            {
                "date": idx.date(),
                "open": float(row["Open"]) if row["Open"] == row["Open"] else None,
                "high": float(row["High"]) if row["High"] == row["High"] else None,
                "low": float(row["Low"]) if row["Low"] == row["Low"] else None,
                "close": close,
                "volume": int(row["Volume"]) if row["Volume"] == row["Volume"] else 0,
            }
        )
    return results


TICKER_MAP = {
    # US stocks
    "AAPL": "AAPL",
    "MSFT": "MSFT",
    "GOOGL": "GOOGL",
    "AMZN": "AMZN",
    "NVDA": "NVDA",
    "TSLA": "TSLA",
    "JPM": "JPM",
    "BRK.B": "BRK.B",
    # A-stocks
    "000001": "000001.SZ",
    "000002": "000002.SZ",
    "600519": "600519.SS",
    "601398": "601398.SS",
    "601988": "601988.SS",
    "300750": "300750.SZ",
}


async def ingest_real_data():
    configure_logging()
    logger.info("开始导入真实行情数据...")

    async with async_session_factory() as sess:
        for local_ticker, yf_ticker in TICKER_MAP.items():
            logger.info(f"  [{local_ticker}] 从 yfinance 获取 ({yf_ticker})...")

            try:
                prices_data = await asyncio.to_thread(fetch_yfinance, yf_ticker)
            except Exception as e:
                logger.error(f"  [{local_ticker}] 获取失败: {e}")
                continue

            if not prices_data:
                logger.warning(f"  [{local_ticker}] 无数据，跳过")
                continue

            # 去重插入
            count = 0
            for row in prices_data:
                existing = await sess.execute(
                    select(StockPrice).where(
                        StockPrice.ticker == local_ticker,
                        StockPrice.date == row["date"],
                    )
                )
                if existing.scalar_one_or_none():
                    continue
                sess.add(
                    StockPrice(
                        ticker=local_ticker,
                        date=row["date"],
                        open=row["open"],
                        high=row["high"],
                        low=row["low"],
                        close=row["close"],
                        volume=row["volume"],
                    )
                )
                count += 1

            if count:
                await sess.flush()
            logger.info(f"  [{local_ticker}] 新增 {count} 条 (共 {len(prices_data)} 条获取)")

        await sess.commit()
        logger.info("✅ 所有行情数据导入完成!")


async def verify():
    async with async_session_factory() as sess:
        from sqlalchemy import text

        rows = await sess.execute(
            text(
                "SELECT ticker, count(*) as cnt FROM market.stock_prices GROUP BY ticker ORDER BY ticker"
            )
        )
        logger.info("当前数据库行情数据量:")
        for r in rows:
            logger.info(f"  {r.ticker}: {r.cnt} 条")


async def main():
    await ingest_real_data()
    await verify()


if __name__ == "__main__":
    asyncio.run(main())
