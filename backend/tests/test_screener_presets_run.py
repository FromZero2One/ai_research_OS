"""presets 模式运行管线单测 — 跳过 LLM 翻译、union 排名、v1 回归。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces import LLMResponse
from screener.models import CriteriaPreset, ScreenerJudgement, ScreenerRule, ScreenerRun
from screener.service import run_screener, trigger_run

SPOT = [
    {"ticker": "600519", "name": "贵州茅台", "price": 1500.0, "turnover": 0.3, "market_cap": 1.88e12},
    {"ticker": "300750", "name": "宁德时代", "price": 200.0, "turnover": 1.0, "market_cap": 8.8e11},
]

VALID_JUDGE = {
    "recommend": True,
    "reasons": ["符合标准"],
    "criteria_hits": [{"criterion": "盈利具有持续性", "hit": True, "evidence": "资料充分"}],
    "confidence": 0.8,
}

judge_calls: list[str] = []


class FakeLLM:
    async def generate(self, messages: Any, **kwargs: Any) -> LLMResponse:
        last = messages[-1].content
        judge_calls.append(last[:50])
        if "标准文档" in last:
            payload = {
                "stock_pool": {"type": "all"},
                "quant_rules": [{"metric": "price", "op": "<", "value": 1000.0, "missing_data_policy": "exclude"}],
                "qualitative_criteria": [],
                "candidate_limit": 50,
            }
        else:
            payload = VALID_JUDGE
        return LLMResponse(content=f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```", model="fake", usage=None)


@pytest.fixture
def screener_env(monkeypatch):
    """mock 全市场快照 + LLM 创建（translate 与 service 共用 FakeLLM 以便计数）。"""
    async def _spot():
        return SPOT

    monkeypatch.setattr("screener.screening.fetch_market_spot", _spot)
    monkeypatch.setattr("screener.service.create_llm", lambda: FakeLLM())
    monkeypatch.setattr("screener.translate.create_llm", lambda: FakeLLM())

    # 单测不做真实财务数据补采（网络 + 会改变“空财务数据”的断言）
    async def _no_ingest(db, needed):
        return False

    monkeypatch.setattr("screener.service._ensure_market_data", _no_ingest)

    # 单测不连真实 Qdrant/Ollama：知识库固定返回空片段（走“无资料”证据守卫）
    class _NoKnowledge:
        async def search(self, *args, **kwargs):
            return []

    monkeypatch.setattr("screener.service._create_knowledge", lambda db: _NoKnowledge())


async def _builtin_ids(db: AsyncSession, tags: list[str]) -> list:
    rows = (
        await db.execute(
            select(CriteriaPreset).where(
                CriteriaPreset.is_builtin.is_(True), CriteriaPreset.style_tag.in_(tags)
            )
        )
    ).scalars().all()
    return [r.id for r in rows], {r.style_tag: r for r in rows}


async def test_presets_mode_end_to_end(test_session: AsyncSession, screener_env, monkeypatch):
    """presets 模式端到端：落库字段、零翻译、union 候选带命中预设。"""
    from market.models import FinancialMetric
    from screener.service import _latest_fiscal

    _, year, period = _latest_fiscal()
    for t in ("600519", "300750"):
        for metric, value in (
            ("roe", 20.0),
            ("net_margin", 30.0),
            # cfo_to_ni > 0.8：5e10 / 5e10 = 1.0
            ("operating_cash_flow", 5e10),
            ("debt_to_equity", 30.0),
            # GARP pe<40：两票 PE 分别约 18.8 / 8.8
            ("net_income", 5e10),
        ):
            test_session.add(
                FinancialMetric(
                    ticker=t, metric_name=metric, metric_value=value,
                    fiscal_year=year, fiscal_period=period,
                )
            )
    await test_session.flush()

    ids, by_tag = await _builtin_ids(test_session, ["core", "garp"])
    rules_before = (
        await test_session.execute(select(func.count()).select_from(ScreenerRule))
    ).scalar_one()

    run = await trigger_run(
        test_session,
        params={"mode": "presets", "pool": "all", "preset_ids": ids, "combine": "union"},
    )
    assert run is not None
    assert run.mode == "presets"
    assert run.preset_ids == [str(i) for i in ids]
    assert run.combine_mode == "union"
    assert run.pool_override == "all"

    done = await run_screener(test_session, run.id)
    await test_session.flush()
    assert done.status == "completed"

    # 零 LLM 翻译：ScreenerRule 无新行
    rules_after = (
        await test_session.execute(select(func.count()).select_from(ScreenerRule))
    ).scalar_one()
    assert rules_after == rules_before

    judgements = (
        await test_session.execute(select(ScreenerJudgement).where(ScreenerJudgement.run_id == run.id))
    ).scalars().all()
    # 财务数据齐备 → 两只票同时命中 core/garp → 2 候选、2 条深判
    assert done.candidate_count == 2
    assert len(judgements) == 2
    for j in judgements:
        assert set(j.snapshot["presets"]) == {"核心资产", "质量价值 GARP"}
        assert j.snapshot["hits"] == 2
    # run.rules 记录组装结果与来源预设
    assert set(done.rules["preset_names"]) == {"核心资产", "质量价值 GARP"}
    assert done.rules["combine"] == "union"


async def test_presets_mode_without_financial_data_fails_explicitly(
    test_session: AsyncSession, screener_env, monkeypatch
):
    """所需指标全市场无数据 → run 明确失败并报出指标名，不再静默产出 0 候选。"""
    ids, _ = await _builtin_ids(test_session, ["core"])
    run = await trigger_run(
        test_session,
        params={"mode": "presets", "pool": "all", "preset_ids": ids, "combine": "union"},
    )
    done = await run_screener(test_session, run.id)
    assert done.status == "failed"
    assert "没有任何数据" in (done.error or "")
    assert "roe" in (done.error or "")


async def test_quant_only_preset_skips_llm(
    test_session: AsyncSession, screener_env, monkeypatch
):
    """预设没有定性条目时，确定性初筛就是结论，不应再调用 LLM 深判。"""
    from market.models import FinancialMetric
    from screener.service import _latest_fiscal

    _, year, period = _latest_fiscal()
    for t in ("600519", "300750"):
        for metric, value in (
            ("roe", 20.0),
            ("net_margin", 30.0),
            ("operating_cash_flow", 5e10),
            ("debt_to_equity", 30.0),
            ("net_income", 5e10),
        ):
            test_session.add(
                FinancialMetric(
                    ticker=t, metric_name=metric, metric_value=value,
                    fiscal_year=year, fiscal_period=period,
                )
            )
    await test_session.flush()

    ids, _ = await _builtin_ids(test_session, ["core"])
    run = await trigger_run(
        test_session,
        params={"mode": "presets", "pool": "all", "preset_ids": ids, "combine": "union"},
    )

    async def _boom(*args, **kwargs):
        raise AssertionError("无定性标准时不应调用 judge_candidates")

    monkeypatch.setattr("screener.service.judge_candidates", _boom)
    done = await run_screener(test_session, run.id)
    assert done.status == "completed"
    assert done.candidate_count == 2
    assert done.result_count == 2

    judgements = (
        await test_session.execute(
            select(ScreenerJudgement).where(ScreenerJudgement.run_id == run.id)
        )
    ).scalars().all()
    assert all(j.recommend is True for j in judgements)
    assert all("未调用 LLM" in " ".join(j.reasons or []) for j in judgements)


async def test_presets_union_with_financials(test_session: AsyncSession, screener_env, monkeypatch):
    """灌入财务数据后 union 初筛：候选带 hits/presets（深判 snapshot 透出）。"""
    from market.models import FinancialMetric

    # union 模式会做全市场 bs/cf 灌库（真实 akshare 子进程）— 测试中 mock 掉
    async def _noop_ingest(db, date: str | None = None) -> int:
        return 0

    monkeypatch.setattr("screener.ingest.ingest_marketwide_bs_cf", _noop_ingest)
    ids, by_tag = await _builtin_ids(test_session, ["cycle"])  # 周期反转只看市值+负债率
    for t in ("600519", "300750"):
        for metric, value in (
            ("debt_to_equity", 30.0),
            # 周期反转新增 pb<2.5：净资产 8e11 → PB 2.35 / 1.1
            ("total_assets", 1e12),
            ("total_liabilities", 2e11),
        ):
            test_session.add(
                FinancialMetric(
                    ticker=t, metric_name=metric, metric_value=value,
                    fiscal_year=2026, fiscal_period="Q2",
                )
            )
    await test_session.flush()

    run = await trigger_run(
        test_session,
        params={"mode": "presets", "pool": "all", "preset_ids": ids, "combine": "union"},
    )
    done = await run_screener(test_session, run.id)
    assert done.status == "completed"
    assert done.candidate_count == 2

    judgements = (
        await test_session.execute(select(ScreenerJudgement).where(ScreenerJudgement.run_id == run.id))
    ).scalars().all()
    assert len(judgements) == 2
    for j in judgements:
        assert j.snapshot["presets"] == ["周期反转"]
        assert j.snapshot["hits"] == 1


async def test_freeform_path_regression(test_session: AsyncSession, screener_env, monkeypatch):
    """v1 回归：params=None 行为完全一致（mode NULL、走翻译）。"""
    from screener.criteria import read_criteria, write_criteria

    original = read_criteria()
    try:
        write_criteria("只选价格低于 1000 的公司")
        run = await trigger_run(test_session)
        assert run.mode is None
        assert run.preset_ids is None

        done = await run_screener(test_session, run.id)
        assert done.status == "completed"
        assert done.candidate_count == 1  # 600519 价格 1500 被排除
        assert done.rules is not None and "quant_rules" in done.rules
    finally:
        write_criteria(original)


async def test_trigger_unknown_preset_raises(test_session: AsyncSession):
    """preset_ids 含不存在的预设 → ValueError（路由层转 422）。"""
    import uuid as _uuid

    with pytest.raises(ValueError, match="预设"):
        await trigger_run(
            test_session,
            params={"mode": "presets", "pool": "all", "preset_ids": [_uuid.uuid4()], "combine": "union"},
        )
