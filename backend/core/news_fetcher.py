"""News fetching helpers for scheduled jobs (newsnow MCP + akshare)."""

from __future__ import annotations

import asyncio
import json

from core.logging import logger
from market.akshare_executor import build_akshare_env, run_akshare


async def fetch_newsnow(sectors: list[str] | None = None) -> list[str]:
    """Fetch financial news relevant to given sectors via persistent MCP."""
    from core.adapters.newsnow_mcp import get_headlines

    return await get_headlines(sectors=sectors)


async def fetch_news_akshare(ticker: str) -> list[dict]:
    """Fetch stock news via akshare subprocess (ticker passed via env)."""
    code = (
        "import json, os, sys\n"
        "import akshare as ak\n"
        "try:\n"
        '    ticker = os.environ["AKSHARE_TICKER"]\n'
        "    df = ak.stock_news_em(symbol=ticker)\n"
        '    if df is None or df.empty:\n        print("__R__:[]")\n'
        "    else:\n        rows = []\n"
        "        for _, row in df.iterrows():\n"
        '            rows.append({"title": str(row.get("新闻标题", "")),\n'
        '                         "source": str(row.get("文章来源", ""))})\n'
        '        print("__R__:" + json.dumps(rows, ensure_ascii=False)[:2000])\n'
        "except Exception as e:\n"
        '    print("__E__:" + str(e), file=sys.stderr)\n'
    )
    try:
        stdout = await asyncio.to_thread(run_akshare, code, build_akshare_env(ticker))
        if not stdout:
            return []
        for line in stdout.splitlines():
            if line.startswith("__R__:"):
                return json.loads(line[6:])
        return []
    except Exception:
        logger.debug("akshare news subprocess failed")
        return []
