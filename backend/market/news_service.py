"""Stock news service — 2-layer fallback: local akshare → cloud MCP."""

from __future__ import annotations

from core.event_service import EventLogger
from core.logging import logger
from market.akshare_executor import fetch_news_via_mcp_cloud, run_akshare


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
            code = (
                f'import json, sys, akshare as ak\ntry:\n'
                f'    df = ak.stock_news_em(symbol="{ticker}")\n'
                f'    if df is None or df.empty:\n        print("__R__:[]")\n'
                f'    else:\n        rows = []\n'
                f'        for _, row in df.iterrows():\n'
                f'            rows.append({{"title": str(row.get("新闻标题", "")),\n'
                f'                "content": str(row.get("新闻内容", ""))[:300],\n'
                f'                "publish_time": str(row.get("发布时间", "")),\n'
                f'                "source": str(row.get("文章来源", "")),\n'
                f'                "url": str(row.get("新闻链接", "")),\n'
                f'            }})\n'
                f'        print("__R__:" + json.dumps(rows, ensure_ascii=False))\n'
                f'except Exception as e:\n'
                f'    print("__E__:" + str(e), file=sys.stderr)\n'
            )
            stdout = await _asyncio.to_thread(run_akshare, code)
            if stdout:
                for line in stdout.splitlines():
                    if line.startswith("__R__:"):
                        data = _json.loads(line[6:])
                        if data:
                            logger.info("  [news] Layer 1 local: %d items for %s", len(data), ticker)
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
