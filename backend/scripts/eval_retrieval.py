# ruff: noqa: E501
"""Retrieval quality evaluation — golden queries against the knowledge base.

Each golden query carries expected keywords; the query passes when at least
one expected keyword appears in the top-k retrieved chunk contents. Run this
after any retrieval change to catch regressions (e.g. silent zero vectors,
broken BM25, bad reranker wiring).

Usage:
    PYTHONPATH=. python scripts/eval_retrieval.py [--top-k 5]

Exits non-zero if any query fails, so it can be wired into CI.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from core.proxy_cleanup import clean_proxy_env

clean_proxy_env()

from core.database import async_session_factory  # noqa: E402
from knowledge.service import KnowledgeService  # noqa: E402

GOLDEN_QUERIES: list[dict] = [
    {"query": "中国银行营收如何", "keywords": ["营业收入"], "note": "revenue overview"},
    {
        "query": "中国银行2025年营业收入是多少",
        "keywords": ["658,310", "营业收入"],
        "note": "revenue figure",
    },
    {"query": "中国银行不良贷款率变化", "keywords": ["不良贷款率"], "note": "NPL ratio"},
    {"query": "中国银行净利润", "keywords": ["净利润"], "note": "net profit"},
    {
        "query": "中国银行净利息收入",
        "keywords": ["利息净收入", "净利息收入"],
        "note": "net interest income",
    },
    {"query": "中国银行资产总额", "keywords": ["资产总额"], "note": "total assets"},
    {"query": "中国银行净资产收益率", "keywords": ["净资产收益率"], "note": "ROE"},
    {"query": "中国银行分红派息", "keywords": ["股利", "派息"], "note": "dividends"},
    {"query": "中国银行员工人数", "keywords": ["员工"], "note": "headcount"},
    {"query": "中国银行拨备覆盖率", "keywords": ["拨备覆盖率"], "note": "provision coverage"},
    {"query": "中国银行核心一级资本充足率", "keywords": ["核心一级资本"], "note": "capital ratio"},
    {"query": "中国银行不良率", "keywords": ["不良贷款率"], "note": "NPL short form"},
    {"query": "中国银行分红", "keywords": ["股利", "现金分红"], "note": "dividend short form"},
]


async def evaluate(top_k: int) -> bool:
    async with async_session_factory() as session:
        svc = KnowledgeService(session)
        passed = 0
        for item in GOLDEN_QUERIES:
            hits = await svc.search(item["query"], top_k=top_k)
            contents = [r.content for r in hits]
            matched = [kw for kw in item["keywords"] if any(kw in c for c in contents)]
            ok = bool(matched)
            passed += ok
            top1 = hits[0].content.replace("\n", " ")[:44] if hits else "(no results)"
            print(
                f"{'PASS' if ok else 'FAIL'} | {item['query']} "
                f"| matched={matched or 'NONE'} | top1={top1!r}"
            )
        print(f"\n{passed}/{len(GOLDEN_QUERIES)} passed @top{top_k}")
        return passed == len(GOLDEN_QUERIES)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate knowledge retrieval quality")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    ok = asyncio.run(evaluate(args.top_k))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
