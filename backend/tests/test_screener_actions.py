"""选股结果动作单测 — 加入自选（幂等、缺失公司、只处理推荐股）。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from company.models import Company
from screener.actions import add_to_watchlist
from screener.models import ScreenerJudgement, ScreenerRun


async def _setup(test_session: AsyncSession) -> ScreenerRun:
    run = ScreenerRun(
        criteria_hash="h",
        criteria_text="标准",
        mode="presets",
        preset_ids=["p"],
        combine_mode="union",
        status="completed",
        candidate_count=3,
        result_count=2,
        created_at=datetime(2026, 10, 24, 9, 0, tzinfo=UTC),
    )
    test_session.add(run)
    await test_session.flush()
    for ticker, name, recommend in (
        ("AAA", "甲", True),
        ("BBB", "乙", True),
        ("CCC", "丙", False),
    ):
        test_session.add(
            ScreenerJudgement(
                run_id=run.id, ticker=ticker, name=name, recommend=recommend,
                reasons=[], criteria_hits=[], confidence=0.9, snapshot={}, status="ok",
            )
        )
    test_session.add_all([
        Company(ticker="AAA", name="甲", is_active=False),
        Company(ticker="BBB", name="乙", is_active=True),
        # CCC 有公司记录但不是推荐股；DDD 推荐但无公司记录
    ])
    test_session.add(
        ScreenerJudgement(
            run_id=run.id, ticker="DDD", name="丁", recommend=True,
            reasons=[], criteria_hits=[], confidence=0.8, snapshot={}, status="ok",
        )
    )
    await test_session.flush()
    return run


async def test_add_recommended_to_watchlist(test_session: AsyncSession):
    run = await _setup(test_session)
    result = await add_to_watchlist(test_session, run.id)

    assert [c["ticker"] for c in result["added"]] == ["AAA"]
    assert [c["ticker"] for c in result["already"]] == ["BBB"]
    assert [c["ticker"] for c in result["missing"]] == ["DDD"]

    company = (
        await test_session.execute(select(Company).where(Company.ticker == "AAA"))
    ).scalar_one()
    assert company.is_active is True
    # 未推荐的 CCC 不受影响
    ccc = (
        await test_session.execute(select(Company).where(Company.ticker == "CCC"))
    ).scalar_one_or_none()
    assert ccc is None or ccc.is_active is False


async def test_add_specific_ticker_and_idempotent(test_session: AsyncSession):
    run = await _setup(test_session)
    first = await add_to_watchlist(test_session, run.id, tickers=["AAA"])
    assert [c["ticker"] for c in first["added"]] == ["AAA"]
    second = await add_to_watchlist(test_session, run.id, tickers=["AAA"])
    assert second["added"] == []
    assert [c["ticker"] for c in second["already"]] == ["AAA"]


async def test_unknown_run_raises(test_session: AsyncSession):
    import uuid

    try:
        await add_to_watchlist(test_session, uuid.uuid4())
    except ValueError:
        return
    raise AssertionError("expected ValueError")
