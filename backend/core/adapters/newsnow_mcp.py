"""NewsNow MCP client — persistent connection with parallel fetching."""

from __future__ import annotations

import asyncio
from typing import Any

from core.logging import logger


class NewsNowMCPClient:
    """Persistent MCP client — runs connection in a background asyncio task."""

    def __init__(self) -> None:
        self._session: Any = None
        self._lock = asyncio.Lock()
        self._ready = asyncio.Event()

    async def _run(self) -> None:
        """Background task: keep MCP connection alive."""
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client, StdioServerParameters

        params = StdioServerParameters(
            command="npx",
            args=["-y", "tsx", "/home/wsm/codes/newsnow/tools/mcp-server.ts"],
            env={"BASE_URL": "https://newsnow.busiyi.world"},
        )

        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    self._ready.set()
                    logger.info("  [newsnow] MCP connected")
                    while True:
                        await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("  [newsnow] MCP task cancelled")
        except Exception as e:
            logger.warning("  [newsnow] MCP task failed: %s", e)
        finally:
            self._session = None
            self._ready.clear()

    async def fetch_headlines(
        self, sources: list[str] | None = None, max_per_source: int = 5
    ) -> list[str]:
        """Fetch headlines from multiple sources in parallel."""
        if sources is None:
            sources = ["cls-telegraph", "wallstreetcn-news", "jin10"]
        if not self._session:
            return []

        async with self._lock:
            async def _fetch(src: str) -> list[str]:
                try:
                    result = await self._session.call_tool("get_news", {"id": src})
                    items: list[str] = []
                    count = 0
                    for c in result.content:
                        for line in c.text.strip().split("\n"):
                            line = line.strip()
                            if not line or not line[0].isdigit():
                                continue
                            if "](" in line and count < max_per_source:
                                head = line.split("](")[0]
                                head = head.split(". ", 1)[-1].lstrip("[")
                                if head and len(head) > 5 and "http" not in head:
                                    items.append(head)
                                    count += 1
                    return items
                except Exception as e:
                    logger.debug("  [newsnow] source %s failed: %s", src, e)
                    return []

            results = await asyncio.gather(*[_fetch(s) for s in sources])
            headlines: list[str] = []
            seen: set[str] = set()
            for items in results:
                for h in items:
                    if h not in seen:
                        seen.add(h)
                        headlines.append(h)
            return headlines[:15]


_client: NewsNowMCPClient | None = None
_client_task: asyncio.Task | None = None


def _ensure_client() -> NewsNowMCPClient:
    global _client, _client_task
    if _client is None:
        _client = NewsNowMCPClient()
        _client_task = asyncio.create_task(_client._run())
    return _client


async def get_headlines() -> list[str]:
    """Get news headlines via persistent MCP client."""
    client = _ensure_client()
    if not client._session:
        try:
            await asyncio.wait_for(client._ready.wait(), timeout=15)
        except asyncio.TimeoutError:
            logger.warning("  [newsnow] connection timeout")
            return []
    return await client.fetch_headlines()
