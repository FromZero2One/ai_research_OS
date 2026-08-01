"""从 yfinance 导入真实财务指标数据"""

import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select

from core.database import async_session_factory
from core.logging import configure_logging, logger
from market.models import FinancialMetric


def fiscal_period_from_date(dt):
    """根据日期计算财年/季度"""
    month = dt.month
    if month <= 3:
        return dt.year - 1, "Q4"
    elif month <= 6:
        return dt.year, "Q1"
    elif month <= 9:
        return dt.year, "Q2"
    else:
        return dt.year, "Q3"


TICKER_MAP = {
    "AAPL": "AAPL",
    "MSFT": "MSFT",
    "GOOGL": "GOOGL",
    "AMZN": "AMZN",
    "NVDA": "NVDA",
    "TSLA": "TSLA",
    "JPM": "JPM",
    "BRK.B": "BRK-B",
    "000001": "000001.SZ",
    "000002": "000002.SZ",
    "600519": "600519.SS",
    "601398": "601398.SS",
    "601988": "601988.SS",
    "300750": "300750.SZ",
}


async def ingest_financials():
    configure_logging()
    logger.info("开始导入真实财务指标...")

    async with async_session_factory() as sess:
        for local_ticker, yf_ticker in TICKER_MAP.items():
            logger.info(f"  [{local_ticker}] 获取 ({yf_ticker})...")

            try:

                def _fetch(t=yf_ticker):
                    import yfinance as yf

                    return yf.Ticker(t).quarterly_financials

                qf = await asyncio.to_thread(_fetch)
            except Exception as e:
                logger.error(f"  [{local_ticker}] 获取失败: {e}")
                continue

            if qf is None or qf.empty:
                logger.warning(f"  [{local_ticker}] 无数据")
                continue

            count = 0
            for col in qf.columns:
                fy, fq = fiscal_period_from_date(col.date())

                # 检查是否已存在
                existing = await sess.execute(
                    select(FinancialMetric)
                    .where(
                        FinancialMetric.ticker == local_ticker,
                        FinancialMetric.fiscal_year == fy,
                        FinancialMetric.fiscal_period == fq,
                    )
                    .limit(1)
                )
                if existing.scalar_one_or_none():
                    continue

                # Total Revenue
                if "Total Revenue" in qf.index:
                    val = qf.loc["Total Revenue", col]
                    if val == val:  # not NaN
                        sess.add(
                            FinancialMetric(
                                ticker=local_ticker,
                                fiscal_year=fy,
                                fiscal_period=fq,
                                metric_name="revenue",
                                metric_value=float(val),
                            )
                        )

                # Net Income
                if "Net Income" in qf.index:
                    val = qf.loc["Net Income", col]
                    if val == val:
                        sess.add(
                            FinancialMetric(
                                ticker=local_ticker,
                                fiscal_year=fy,
                                fiscal_period=fq,
                                metric_name="net_income",
                                metric_value=float(val),
                            )
                        )

                # Operating Margin
                if "Operating Income" in qf.index and "Total Revenue" in qf.index:
                    oi = qf.loc["Operating Income", col]
                    tr = qf.loc["Total Revenue", col]
                    if oi == oi and tr == tr and tr != 0:
                        sess.add(
                            FinancialMetric(
                                ticker=local_ticker,
                                fiscal_year=fy,
                                fiscal_period=fq,
                                metric_name="operating_margin",
                                metric_value=float(oi / tr),
                            )
                        )

                # EPS
                if "Diluted EPS" in qf.index:
                    val = qf.loc["Diluted EPS", col]
                    if val == val:
                        sess.add(
                            FinancialMetric(
                                ticker=local_ticker,
                                fiscal_year=fy,
                                fiscal_period=fq,
                                metric_name="eps",
                                metric_value=float(val),
                            )
                        )

                count += 1

            if count:
                await sess.flush()
            logger.info(f"  [{local_ticker}] 写入 {count} 个季度数据")

        await sess.commit()
        logger.info("✅ 财务指标导入完成!")


async def verify():
    async with async_session_factory() as sess:
        from sqlalchemy import text

        rows = await sess.execute(
            text("""
                SELECT ticker, count(*) as cnt,
                       count(DISTINCT metric_name) as metrics,
                       count(DISTINCT fiscal_year || fiscal_period) as quarters
                FROM market.financial_metrics
                GROUP BY ticker ORDER BY ticker
            """)
        )
        logger.info("当前财务指标数据量:")
        for r in rows:
            logger.info(f"  {r.ticker}: {r.cnt} 条 ({r.metrics} 种指标 × {r.quarters} 季度)")


async def main():
    await ingest_financials()
    await verify()


if __name__ == "__main__":
    asyncio.run(main())
