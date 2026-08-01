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
        from mcp.client.stdio import StdioServerParameters, stdio_client

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

    _FINANCE_KEYWORDS = [
        "股",
        "涨",
        "跌",
        "价",
        "市值",
        "季报",
        "财报",
        "营收",
        "利润",
        "业绩",
        "投资",
        "融资",
        "减持",
        "增持",
        "回购",
        "分红",
        "基金",
        "ETF",
        "IPO",
        "上市",
        "退市",
        "重组",
        "央行",
        "利率",
        "降息",
        "加息",
        "降准",
        "期货",
        "期权",
        "债券",
        "国债",
        "美元",
        "人民币",
        "汇率",
        "通胀",
        "AI",
        "芯片",
        "半导体",
        "新能源",
        "光伏",
        "电动",
        "订单",
        "合同",
        "中标",
        "产能",
        "扩产",
        "收购",
        "并购",
        "出售",
        "剥离",
        "亿",
        "万",
        "元",
        "美元",
        "%",
    ]

    # Sector → keyword mapping for relevance filtering
    _SECTOR_KEYWORDS: dict[str, list[str]] = {
        "银行": [
            "银行",
            "信贷",
            "存款",
            "贷款",
            "息差",
            "不良",
            "拨备",
            "理财",
            "资管",
            "金融监管",
            "Financial",
            "financial",
        ],
        "Financial Services": [
            "银行",
            "信贷",
            "存款",
            "贷款",
            "息差",
            "不良",
            "拨备",
            "理财",
            "资管",
            "金融监管",
            "Financial",
        ],
        "证券": ["券商", "证券", "投行", "经纪", "资管", "自营", "两融", "IPO", "承销"],
        "保险": ["保险", "保费", "理赔", "寿险", "财险", "健康险", "偿付能力"],
        "房地产": [
            "地产",
            "房地产",
            "楼市",
            "房贷",
            "土地",
            "房企",
            "物业",
            "万科",
            "保利",
            "Real Estate",
        ],
        "汽车": [
            "汽车",
            "新能源车",
            "电动",
            "锂电",
            "充电",
            "比亚迪",
            "特斯拉",
            "蔚来",
            "小鹏",
            "Auto",
        ],
        "医药": ["医药", "医疗", "创新药", "CXO", "生物", "器械", "医保", "集采", "Health"],
        "科技": [
            "科技",
            "AI",
            "芯片",
            "半导体",
            "互联网",
            "软件",
            "云计算",
            "大模型",
            "人工智能",
            "Tech",
        ],
        "消费": [
            "消费",
            "零售",
            "电商",
            "白酒",
            "食品",
            "饮料",
            "家电",
            "免税",
            "旅游",
            "Consumer",
        ],
        "能源": [
            "能源",
            "石油",
            "煤炭",
            "电力",
            "光伏",
            "风电",
            "核电",
            "天然气",
            "绿电",
            "Energy",
        ],
        "制造": ["制造", "工业", "装备", "机械", "军工", "船舶", "航空", "Industrial"],
    }

    @staticmethod
    def _is_finance_related(headline: str) -> bool:
        return any(kw in headline for kw in NewsNowMCPClient._FINANCE_KEYWORDS)

    @staticmethod
    def _matches_sector(headline: str, sectors: list[str]) -> bool:
        """Check if headline matches any given sector (supports CJK/English names)."""
        if not sectors:
            return True
        # Collect all keywords for the given sectors
        all_kws: list[str] = []
        for sector in sectors:
            s_lower = sector.lower()
            # Direct key match
            if sector in NewsNowMCPClient._SECTOR_KEYWORDS:
                all_kws.extend(NewsNowMCPClient._SECTOR_KEYWORDS[sector])
            # Fuzzy match: check if sector name contains Chinese key
            for cn_key, cn_kws in NewsNowMCPClient._SECTOR_KEYWORDS.items():
                if cn_key.lower() in s_lower or s_lower in cn_key.lower():
                    all_kws.extend(cn_kws)
        all_kws = list(set(all_kws))
        return any(kw.lower() in headline.lower() for kw in all_kws) if all_kws else True

    async def fetch_headlines(
        self,
        sources: list[str] | None = None,
        sectors: list[str] | None = None,
        max_per_source: int = 5,
    ) -> list[str]:
        """Fetch finance headlines relevant to given sectors."""
        if sources is None:
            sources = ["cls-telegraph", "wallstreetcn-news", "jin10"]
        sectors = sectors or []
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
                    if h in seen:
                        continue
                    seen.add(h)
                    if not self._is_finance_related(h):
                        continue
                    if sectors and not self._matches_sector(h, sectors):
                        continue
                    headlines.append(h)
            return headlines[:10]


_client: NewsNowMCPClient | None = None
_client_task: asyncio.Task | None = None


def _ensure_client() -> NewsNowMCPClient:
    global _client, _client_task
    if _client is None:
        _client = NewsNowMCPClient()
        _client_task = asyncio.create_task(_client._run())
    return _client


async def get_headlines(sectors: list[str] | None = None) -> list[str]:
    """Get finance headlines relevant to given sectors.

    Args:
        sectors: List of Chinese sector names (e.g. ["银行", "科技"]).
                 If empty, returns all finance headlines.
    """
    client = _ensure_client()
    if not client._session:
        try:
            await asyncio.wait_for(client._ready.wait(), timeout=15)
        except TimeoutError:
            logger.warning("  [newsnow] connection timeout")
            return []
    return await client.fetch_headlines(sectors=sectors)
