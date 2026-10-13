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
from market.models import DataFreshness
from market.service.freshness_service import FreshnessService


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
    """所有类型都有 ok 记录时 worst_health=ok、with_gaps=0。"""
    test_session.add(Company(ticker="FULL", name="全覆盖", is_active=True))
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
