"""Run the LLM screener-judge evaluation set against the configured model.

Usage:
    ALL_PROXY= all_proxy= PYTHONPATH=. ./.venv/Scripts/python.exe -X utf8 \
        scripts/eval_judge.py [--limit N] [--concurrency 3]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from core.adapters.llm import create_llm
from screener.judge_eval import build_eval_markdown, load_cases, run_case, summarize

REPORT_DIR = Path(__file__).resolve().parent.parent / "screener" / "reports"


async def run(cases: list[dict], concurrency: int) -> list:
    llm = create_llm()
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def one(case: dict):
        async with semaphore:
            return await run_case(llm, case)

    results = await asyncio.gather(*(one(c) for c in cases))
    return llm, results


def main(limit: int | None, concurrency: int) -> None:
    cases = load_cases()
    if limit:
        cases = cases[:limit]
    if not cases:
        raise SystemExit("没有评测用例")

    llm, results = asyncio.run(run(cases, concurrency))
    model_name = getattr(llm, "model_name", "unknown")
    markdown = build_eval_markdown(model_name, results)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"eval-judge-{datetime.now():%Y%m%d-%H%M%S}.md"
    path.write_text(markdown, encoding="utf-8")

    print(json.dumps(summarize(results), ensure_ascii=False, indent=2))
    print(f"report: {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=3)
    args = parser.parse_args()
    main(limit=args.limit, concurrency=args.concurrency)
