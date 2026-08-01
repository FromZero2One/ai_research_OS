"""Stock news service — 2-layer fallback: local akshare → cloud MCP."""

from __future__ import annotations

from core.event_service import EventLogger
from core.logging import logger
from market.akshare_executor import (
    build_akshare_env,
    fetch_news_via_mcp_cloud,
    run_akshare,
)

_NEWS_CODE = (
    "import json, os, sys, akshare as ak\n"
    "try:\n"
    '    ticker = os.environ["AKSHARE_TICKER"]\n'
    "    df = ak.stock_news_em(symbol=ticker)\n"
    '    if df is None or df.empty:\n        print("__R__:[]")\n'
    "    else:\n        rows = []\n"
    "        for _, row in df.iterrows():\n"
    '            rows.append({"title": str(row.get("\u65b0\u95fb\u6807\u9898", "")),\n'
    '                "content": str(row.get("\u65b0\u95fb\u5185\u5bb9", ""))[:300],\n'
    '                "publish_time": str(row.get("\u53d1\u5e03\u65f6\u95f4", "")),\n'
    '                "source": str(row.get("\u6587\u7ae0\u6765\u6e90", "")),\n'
    '                "url": str(row.get("\u65b0\u95fb\u94fe\u63a5", "")),\n'
    "            })\n"
    '        print("__R__:" + json.dumps(rows, ensure_ascii=False))\n'
    "except Exception as e:\n"
    '    print("__E__:" + str(e), file=sys.stderr)\n'
)


class NewsService:
    """Fetch stock news via 2-layer fallback."""

    def __init__(self, session=None) -> None:
        self.events = EventLogger(session) if session else None

    async def fetch_news(self, ticker: str) -> tuple[list[dict], str]:
        """Fetch stock news via 2-layer fallback.

        Returns (news_list, source_name).
        Each news item: {title, content, publish_time, source, url}.
        """
        import asyncio as _asyncio
        import json as _json

        # Layer 1: local akshare via subprocess
        try:
            code = _NEWS_CODE
            stdout = await _asyncio.to_thread(run_akshare, code, build_akshare_env(ticker))
            if stdout:
                for line in stdout.splitlines():
                    if line.startswith("__R__:"):
                        data = _json.loads(line[6:])
                        if data:
                            logger.info(
                                "  [news] Layer 1 local: %d items for %s",
                                len(data),
                                ticker,
                            )
                            return data, "akshare_local"
        except Exception as e:
            logger.warning("  [news] Layer 1 failed: %s", e)

        # Layer 2: cloud MCP
        try:
            news = await fetch_news_via_mcp_cloud(ticker)
            if news:
                logger.info("  [news] Layer 2 cloud: %d items for %s", len(news), ticker)
                return news, "cloud_mcp"
        except Exception as e:
            logger.warning("  [news] Layer 2 failed: %s", e)

        return [], "none"
