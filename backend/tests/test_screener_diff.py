"""变化日报单测 — 纯 diff 计算 + 同口径上一轮查找。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from screener.diff import build_diff_markdown, compute_diff
from screener.diff_service import build_run_diff
from screener.models import ScreenerJudgement, ScreenerRun


def _j(ticker: str, recommend: bool, status: str = "ok") -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "recommend": recommend,
        "status": status,
        "confidence": 0.9,
        "snapshot": {"industry": "银行", "price": 10.0, "market_cap": 1e10},
        "reasons": [],
        "criteria_hits": [],
    }


class TestComputeDiff:
    def test_new_and_dropped(self):
        previous = [_j("A", True), _j("B", True), _j("C", False)]
        current = [_j("A", True), _j("C", True), _j("D", False)]
        diff = compute_diff(current, previous)

        assert {j["ticker"] for j in diff["new_recommended"]} == {"C"}
        assert {j["ticker"] for j in diff["dropped_recommended"]} == {"B"}
        # C 已在新推荐中展示，不重复算新进候选
        assert {j["ticker"] for j in diff["new_candidates"]} == {"D"}
        assert {j["ticker"] for j in diff["dropped_candidates"]} == set()
        assert diff["counts"]["new_recommended"] == 1
        assert diff["counts"]["dropped_recommended"] == 1

    def test_no_previous_is_first_run(self):
        markdown = build_diff_markdown({"id": "abc", "created_at": None}, None, None)
        assert "首次运行" in markdown
        assert "无（首次运行）" in markdown


async def test_build_run_diff_uses_previous_same_preset(test_session: AsyncSession):
    common = dict(
        criteria_hash="h1",
        criteria_text="预设组合",
        mode="presets",
        preset_ids=["p1"],
        combine_mode="union",
        status="completed",
    )
    previous = ScreenerRun(
        **common,
        candidate_count=2,
        result_count=2,
        created_at=datetime(2026, 10, 24, 8, 0, tzinfo=UTC),
    )
    current = ScreenerRun(
        **common,
        candidate_count=2,
        result_count=1,
        created_at=datetime(2026, 10, 24, 9, 0, tzinfo=UTC),
    )
    test_session.add_all([previous, current])
    await test_session.flush()

    for run, rows in (
        (previous, [("A", True), ("B", True)]),
        (current, [("A", True), ("C", True)]),
    ):
        for ticker, recommend in rows:
            test_session.add(
                ScreenerJudgement(
                    run_id=run.id,
                    ticker=ticker,
                    name=ticker,
                    recommend=recommend,
                    reasons=[],
                    criteria_hits=[],
                    confidence=0.9,
                    snapshot={"industry": "银行"},
                    status="ok",
                )
            )
    await test_session.flush()

    markdown, has_previous = await build_run_diff(test_session, current.id)
    assert has_previous is True
    assert "新推荐" in markdown and "掉出推荐" in markdown
    assert "C" in markdown and "B" in markdown


def _rule(roe: float) -> dict:
    return {
        "stock_pool": {"type": "all"},
        "quant_rules": [
            {"metric": "roe", "op": ">", "value": roe, "missing_data_policy": "exclude"}
        ],
        "qualitative_criteria": [],
    }


def _run(rules: dict, when: int, hash_: str = "h1") -> ScreenerRun:
    return ScreenerRun(
        criteria_hash=hash_,
        criteria_text="预设组合",
        rules=rules,
        mode="presets",
        preset_ids=["p1"],
        combine_mode="union",
        status="completed",
        candidate_count=1,
        result_count=1,
        created_at=datetime(2026, 10, 24, when, 0, tzinfo=UTC),
    )


async def test_preset_rule_change_invalidates_baseline(test_session: AsyncSession):
    """preset_ids 相同但规则被编辑 → 不把旧规则运行当基线。"""
    previous = _run(_rule(15.0), 8)
    current = _run(_rule(20.0), 9)
    test_session.add_all([previous, current])
    await test_session.flush()

    markdown, has_previous = await build_run_diff(test_session, current.id)
    assert has_previous is False
    assert "规则已变更" in markdown
    assert "首次运行" not in markdown


async def test_previous_run_uses_latest_matching_rules(test_session: AsyncSession):
    """跳过错口径的中间运行，选择更早但规则一致的一轮作为基线。"""
    old_match = _run(_rule(20.0), 7)
    middle_changed = _run(_rule(15.0), 8)
    current = _run(_rule(20.0), 9)
    test_session.add_all([old_match, middle_changed, current])
    await test_session.flush()

    markdown, has_previous = await build_run_diff(test_session, current.id)
    assert has_previous is True
    assert "对比基线" in markdown
    assert old_match.id.hex[:8] in markdown
