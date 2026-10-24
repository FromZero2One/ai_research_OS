"""行业分类解析与金融行业识别单测（纯函数）。"""

from __future__ import annotations

from screener.industry import (
    is_financial,
    parse_industry_constituents,
    parse_industry_list,
    parse_sw_industry_rows,
    sector_of,
)


def test_parse_industry_list():
    text = (
        'var S_Finance_bankuai_sinaindustry = '
        '{"new_blhy":"new_blhy,玻璃行业,19,14.7,sz300093,金刚光伏",'
        '"new_yh":"new_yh,银行,42,5.1,sh601398,工商银行"}'
    )
    industries = parse_industry_list(text)
    assert {i["code"] for i in industries} == {"new_blhy", "new_yh"}
    by_code = {i["code"]: i for i in industries}
    assert by_code["new_yh"]["name"] == "银行"
    assert by_code["new_yh"]["count"] == 42


def test_parse_industry_list_bad_input():
    assert parse_industry_list("not a js var") == []
    assert parse_industry_list("var x = bad-json;") == []


def test_parse_industry_constituents():
    rows = [
        {"code": "600519", "name": "贵州茅台"},
        {"symbol": "sz000001", "name": "平安银行"},
        {"code": "BAD", "name": "非A股"},
    ]
    out = parse_industry_constituents(rows)
    assert [r["ticker"] for r in out] == ["600519"]


async def test_attach_industries(test_session):
    from market.models import StockIndustry
    from screener.service import _attach_industries

    test_session.add(
        StockIndustry(ticker="600519", industry_code="new_ljhy", industry_name="酿酒行业")
    )
    await test_session.flush()

    candidates = [{"ticker": "600519"}, {"ticker": "000001"}]
    await _attach_industries(test_session, candidates)

    assert candidates[0]["industry"] == "酿酒行业"
    assert candidates[0]["sector"] == "industrial"
    assert candidates[1]["industry"] is None
    assert candidates[1]["sector"] == "unknown"


def test_parse_sw_industry_rows():
    rows = [
        {"ticker": "600519", "industry_code": "801120", "industry_name": "食品饮料"},
        {"ticker": "1", "industry_code": "801780", "industry_name": "银行"},
        {"ticker": "BAD", "industry_code": "x", "industry_name": "x"},
    ]
    out = parse_sw_industry_rows(rows)
    assert [r["ticker"] for r in out] == ["600519", "000001"]
    assert out[1]["industry_name"] == "银行"


def test_sector_of():
    assert sector_of("银行") == "financial"
    assert sector_of("保险") == "financial"
    assert sector_of("证券") == "financial"
    assert sector_of("多元金融") == "financial"
    assert sector_of("非银金融") == "financial"
    assert sector_of("金融行业") == "financial"
    assert sector_of("酿酒行业") == "industrial"
    assert sector_of(None) == "unknown"
    assert is_financial("银行") is True
    assert is_financial("电子器件") is False
