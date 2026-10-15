"""数据覆盖矩阵（get_coverage_matrix）单测。

覆盖三个关键行为：
1. 只统计 is_active 公司（未关注的排除）
2. 从未抓取过的数据类型显式标 missing
3. worst_health 按 missing > stale > warn > ok 取最差
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from company.models import Company
from document.models import Document, DocumentChunk
from market.models import DataFreshness
from market.service.freshness_service import FreshnessService


async def _seed_docs(session: AsyncSession, ticker_ties: dict[str, list[Company]]) -> dict[str, Company]:
    """建公司并返回 ticker→Company 映射（供测试关联 document.company_id）。"""
    for companies in ticker_ties.values():
        session.add_all(companies)
    await session.flush()
    return {c.ticker: c for companies in ticker_ties.values() for c in companies}


async def _seed(session: AsyncSession) -> None:
    """两只关注公司 + 一只未关注公司；只给 T1 记 prices（ok）和 financials（stale）。"""
    session.add_all(
        [
            Company(ticker="T1", name="一号测试", is_active=True),
            Company(ticker="T2", name="二号测试", is_active=True),
            Company(ticker="OFF", name="未关注", is_active=False),
        ]
    )
    now = datetime.now(UTC)
    session.add_all(
        [
            DataFreshness(ticker="T1", data_type="prices", checked_at=now, status="ok"),
            DataFreshness(
                ticker="T1",
                data_type="financials",
                checked_at=now - timedelta(days=30),  # 阈值 168h，30 天必 stale
                status="ok",
            ),
        ]
    )
    await session.commit()


@pytest.mark.asyncio
async def test_coverage_matrix_basics(test_session: AsyncSession):
    await _seed(test_session)

    result = await FreshnessService(test_session).get_coverage_matrix()

    assert result["data_types"] == ["prices", "financials", "profile", "news"]
    # 未关注公司不进矩阵
    tickers = [r["ticker"] for r in result["rows"]]
    assert tickers == ["T1", "T2"]

    t1 = result["rows"][0]
    assert t1["cells"]["prices"]["health"] == "ok"
    assert t1["cells"]["financials"]["health"] == "stale"
    # T1 没抓过 profile/news → missing
    assert t1["cells"]["profile"]["health"] == "missing"
    assert set(t1["missing"]) == {"profile", "news"}
    # missing 视为最严重
    assert t1["worst_health"] == "missing"

    t2 = result["rows"][1]
    # T2 完全没有记录 → 四格全 missing
    assert t2["worst_health"] == "missing"
    assert len(t2["missing"]) == 4

    assert result["counts"]["companies"] == 2
    assert result["counts"]["with_gaps"] == 2
    assert result["counts"]["fully_covered"] == 0


@pytest.mark.asyncio
async def test_coverage_matrix_fully_covered(test_session: AsyncSession):
    """所有类型都有 ok 记录、且定性覆盖 ok 时 worst_health=ok、with_gaps=0。"""
    c = Company(ticker="FULL", name="全覆盖", is_active=True)
    test_session.add(c)
    await test_session.flush()
    # 定性维度也要 ok：已索引文档 + mda/risk 切片
    d = Document(title="年报", doc_type="pdf", company_id=c.id, is_indexed=True)
    d.chunks = [DocumentChunk(chunk_index=0, content="管理层讨论", content_type="mda")]
    test_session.add(d)
    now = datetime.now(UTC)
    for dt in ("prices", "financials", "profile", "news"):
        test_session.add(
            DataFreshness(ticker="FULL", data_type=dt, checked_at=now, status="ok")
        )
    await test_session.commit()

    result = await FreshnessService(test_session).get_coverage_matrix()
    row = result["rows"][0]
    assert row["worst_health"] == "ok"
    assert row["missing"] == []
    assert result["counts"]["fully_covered"] == 1


@pytest.mark.asyncio
async def test_coverage_qualitative_three_states(test_session: AsyncSession):
    """ok=已索引有 mda/risk；partial=已索引但无 mda/risk；missing=无文档。"""
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
    c = Company(ticker="QWORST", name="定性缺失", is_active=True)
    await _seed_docs(test_session, {"x": [c]})
    now = datetime.now(UTC)
    for dt in ("prices", "financials", "profile", "news"):
        test_session.add(DataFreshness(ticker="QWORST", data_type=dt, checked_at=now, status="ok"))
    await test_session.commit()

    result = await FreshnessService(test_session).get_coverage_matrix()
    row = next(r for r in result["rows"] if r["ticker"] == "QWORST")
    assert row["qualitative"]["health"] == "missing"
    assert row["worst_health"] == "missing"
