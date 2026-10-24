"""选股 → 研究中心交接单测。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from company.models import Company
from research.models import ResearchSession
from research.schemas import ResearchSessionResponse
from screener.handoff import create_research_sessions
from screener.models import ScreenerJudgement, ScreenerRun


async def test_create_sessions_and_dedupe(test_session: AsyncSession):
    run = ScreenerRun(
        criteria_hash="h", criteria_text="预设组合（union）：核心资产",
        mode="presets", preset_ids=["p"], combine_mode="union",
        status="completed", candidate_count=2, result_count=2,
        created_at=datetime(2026, 10, 24, 9, 0, tzinfo=UTC),
    )
    test_session.add(run)
    await test_session.flush()
    for ticker, name in (("AAA", "甲"), ("BBB", "乙")):
        test_session.add(Company(ticker=ticker, name=name))
        test_session.add(
            ScreenerJudgement(
                run_id=run.id, ticker=ticker, name=name, recommend=True,
                reasons=[], criteria_hits=[], confidence=0.9,
                snapshot={"score": 1.0, "presets": ["核心资产"]}, status="ok",
            )
        )
    await test_session.flush()

    result = await create_research_sessions(test_session, run.id, limit=5)
    assert len(result["created"]) == 2
    sessions = (
        await test_session.execute(select(ResearchSession))
    ).scalars().all()
    assert len(sessions) == 2
    assert all(s.company_id is not None for s in sessions)
    assert all("screener" in (s.tags or []) for s in sessions)
    assert all((s.extra_metadata or {}).get("screener_run_id") == str(run.id) for s in sessions)

    # 会话详情接口按 list[str] 序列化 tags，避免 500
    detail = ResearchSessionResponse.model_validate(sessions[0])
    assert detail.tags == ["screener", str(run.id)]

    again = await create_research_sessions(test_session, run.id, limit=5)
    assert again["created"] == []
    assert len(again["skipped"]) == 2


async def test_ticker_filter_and_limit(test_session: AsyncSession):
    run = ScreenerRun(
        criteria_hash="h", criteria_text="标准", mode="presets",
        preset_ids=["p"], combine_mode="union", status="completed",
        candidate_count=3, result_count=3,
        created_at=datetime(2026, 10, 24, 9, 0, tzinfo=UTC),
    )
    test_session.add(run)
    await test_session.flush()
    for ticker, confidence in (("AAA", 0.9), ("BBB", 0.8), ("CCC", 0.7)):
        test_session.add(
            ScreenerJudgement(
                run_id=run.id, ticker=ticker, name=ticker, recommend=True,
                reasons=[], criteria_hits=[], confidence=confidence,
                snapshot={}, status="ok",
            )
        )
    await test_session.flush()

    result = await create_research_sessions(
        test_session, run.id, tickers=["BBB", "CCC"], limit=1
    )
    assert [c["ticker"] for c in result["created"]] == ["BBB"]
