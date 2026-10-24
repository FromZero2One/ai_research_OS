"""行业分类解析与金融行业识别（新浪行业节点，纯函数可单测）。

新浪 `newSinaHy.php` 返回行业列表；`Market_Center.getHQNodeData` 按 node
返回成分股。两层数据都只做解析，网络请求放在 scripts/ingest_industry_sina.py。
"""

from __future__ import annotations

import json

INDUSTRY_SOURCE = "sina"
FINANCIAL_KEYWORDS = (
    "银行", "保险", "证券", "多元金融", "信托", "租赁", "非银金融", "金融",
)


def parse_industry_list(text: str) -> list[dict]:
    """解析 `newSinaHy.php` 的 JS 变量 → [{code, name, count}]。

    原始格式：var S_Finance_bankuai_sinaindustry = {"new_blhy":"new_blhy,玻璃行业,19,...",...}
    """
    if "=" not in text:
        return []
    payload = text.split("=", 1)[1].strip().rstrip(";").strip()
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []

    out: list[dict] = []
    for key, value in data.items():
        parts = str(value).split(",")
        if len(parts) < 2:
            continue
        code = (parts[0] or key).strip()
        name = parts[1].strip()
        if not code or not name:
            continue
        count = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        out.append({"code": code, "name": name, "count": count})
    return out


def parse_industry_constituents(rows: list[dict] | None) -> list[dict]:
    """解析行业成分股 API → [{ticker, name}]（只保留 6 位 A 股代码）。"""
    out: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or row.get("symbol") or "").strip()
        if len(code) != 6 or not code.isdigit():
            continue
        out.append({"ticker": code, "name": row.get("name")})
    return out


def parse_sw_industry_rows(rows: list[dict] | None) -> list[dict]:
    """申万一级行业成分 → [{ticker, industry_code, industry_name}]。"""
    out: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().zfill(6)
        if len(ticker) != 6 or not ticker.isdigit():
            continue
        out.append(
            {
                "ticker": ticker,
                "industry_code": str(row.get("industry_code") or "").strip(),
                "industry_name": str(row.get("industry_name") or "").strip(),
            }
        )
    return out


def sector_of(industry_name: str | None) -> str:
    """行业 → 金融/工业。金融行业不适用流动比率、毛利率、周转率等指标。"""
    if not industry_name:
        return "unknown"
    text = str(industry_name)
    return "financial" if any(k in text for k in FINANCIAL_KEYWORDS) else "industrial"


def is_financial(industry_name: str | None) -> bool:
    return sector_of(industry_name) == "financial"
