"""Screener 数据模型单测 — 表结构、默认值、级联删除。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.models import ScreenerJudgement, ScreenerRule, ScreenerRun


async def test_run_defaults(test_session: AsyncSession):
    """ScreenerRun 默认 status=pending，数值字段可空。"""
    run = ScreenerRun(criteria_hash="abc123", criteria_text="标准文本")
    test_session.add(run)
    await test_session.flush()

    loaded = (
        await test_session.execute(select(ScreenerRun).where(ScreenerRun.id == run.id))
    ).scalar_one()
    assert loaded.status == "pending"
    assert loaded.rules is None
    assert loaded.candidate_count is None
    assert loaded.result_count is None
    assert loaded.report_path is None
    assert loaded.error is None
    assert loaded.created_at is not None


async def test_judgement_cascade_delete(test_session: AsyncSession):
    """删除 run 级联删除其 judgements。"""
    run = ScreenerRun(criteria_hash="h", criteria_text="t")
    test_session.add(run)
    await test_session.flush()
    j = ScreenerJudgement(
        run_id=run.id,
        ticker="600519",
        name="贵州茅台",
        recommend=True,
        reasons=["毛利率高"],
        criteria_hits=[{"criterion": "毛利率>50%", "hit": True}],
        confidence=0.9,
        snapshot={"price": 1500.0},
    )
    test_session.add(j)
    await test_session.flush()

    await test_session.delete(run)
    await test_session.flush()

    left = (
        await test_session.execute(select(ScreenerJudgement).where(ScreenerJudgement.run_id == run.id))
    ).scalars().all()
    assert left == []


async def test_judgement_failed_status(test_session: AsyncSession):
    """深判失败的 judgement：status 默认 ok，可显式置 failed 并带 error。"""
    run = ScreenerRun(criteria_hash="h", criteria_text="t")
    test_session.add(run)
    await test_session.flush()
    j = ScreenerJudgement(
        run_id=run.id,
        ticker="000001",
        name="平安银行",
        status="failed",
        error="LLM 返回坏 JSON",
    )
    test_session.add(j)
    await test_session.flush()

    loaded = (
        await test_session.execute(select(ScreenerJudgement).where(ScreenerJudgement.id == j.id))
    ).scalar_one()
    assert loaded.status == "failed"
    assert loaded.recommend is None


async def test_rule_unique_hash(test_session: AsyncSession):
    """ScreenerRule.doc_hash 唯一。"""
    test_session.add(ScreenerRule(doc_hash="hash-1", rules={"a": 1}, criteria_text="t"))
    await test_session.flush()
    import pytest
    from sqlalchemy.exc import IntegrityError

    test_session.add(ScreenerRule(doc_hash="hash-1", rules={"b": 2}, criteria_text="t2"))
    with pytest.raises(IntegrityError):
        await test_session.flush()
    await test_session.rollback()  # 失败事务必须回滚，否则 fixture teardown 的 commit 会报 PendingRollbackError
