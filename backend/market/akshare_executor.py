"""Shared utilities for akshare subprocess execution and data parsing."""

from __future__ import annotations

import os as _os
import re as _re
import subprocess as _sp
from datetime import date as _date

# Only safe symbol characters may reach the akshare subprocess.
# Defense in depth: even though tickers are now passed as environment
# variables (data, never code), reject anything unusual up front so no
# other consumer can be tricked into embedding a hostile value.
_SAFE_TICKER_RE = _re.compile(r"^[A-Za-z0-9._\-]{1,20}$")


def is_a_stock(ticker: str) -> bool:
    """Check if ticker is a Chinese A-stock (all digits, 6 chars)."""
    return ticker.strip().isdigit() and len(ticker.strip()) == 6


def build_akshare_env(ticker: str) -> dict[str, str]:
    """Build env vars for the akshare subprocess — pass ticker as data, never code.

    The child code reads ``os.environ["AKSHARE_TICKER"]`` instead of having the
    value interpolated into source, which makes code injection impossible.
    The allowlist below is defense in depth: unsupported characters raise
    ``ValueError`` so callers can fall back to the next data layer.
    """
    if not isinstance(ticker, str) or not _SAFE_TICKER_RE.match(ticker):
        raise ValueError(f"Unsafe ticker for akshare subprocess: {ticker!r}")
    return {"AKSHARE_TICKER": ticker}


def run_akshare(code: str, env_args: dict[str, str] | None = None) -> str | None:
    """Run akshare Python code in akshare_mcp venv and return stdout.

    ``env_args`` values are exported to the child as ``AKSHARE_<KEY>``
    environment variables — never embedded in ``code``.
    """
    AKSHARE_MCP_DIR = _os.getenv("AKSHARE_MCP_DIR", "/home/wsm/codes/akshare_mcp")
    env = {
        "HOME": _os.environ.get("HOME", ""),
        "PATH": _os.environ.get("PATH", ""),
        "USER": _os.environ.get("USER", ""),
        "NO_PROXY": "localhost,127.0.0.0/8,::1",
        "no_proxy": "localhost,127.0.0.0/8,::1",
    }
    if env_args:
        env.update({f"AKSHARE_{k}": v for k, v in env_args.items()})
    try:
        result = _sp.run(
            ["uv", "run", "--directory", AKSHARE_MCP_DIR, "python", "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except Exception:
        return None


def tx_symbol(ticker: str) -> str:
    """Convert 6-digit A-stock code to Tencent format (sz/sh prefix)."""
    return f"sh{ticker}" if ticker.startswith("6") else f"sz{ticker}"


def to_float(v) -> float | None:
    """Safely convert value to float."""
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def parse_mcp_table(text: str) -> list[dict]:
    """Parse pandas DataFrame text table → list[dict]."""
    lines = text.strip().split("\n")
    if len(lines) < 2:
        return []
    header_line = lines[0]
    headers = [h.strip() for h in header_line.split("  ") if h.strip()]
    results = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = [p for p in line.split("  ") if p.strip()]
        if parts and parts[0].isdigit():
            parts = parts[1:]
        if len(parts) == len(headers):
            results.append(dict(zip(headers, parts)))
        elif len(parts) > 0:
            row = {}
            for i, h in enumerate(headers):
                row[h] = parts[i] if i < len(parts) else ""
            results.append(row)
    return results


async def fetch_prices_via_mcp_cloud(ticker: str) -> list[dict]:
    """Layer 3: call cloud MCP server's stock_zh_a_hist tool."""
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.types import TextContent

    CLOUD_MCP_URL = "http://8.137.104.120:8088/mcp"
    http_client = httpx.AsyncClient(verify=False, timeout=30)
    try:
        async with streamable_http_client(CLOUD_MCP_URL, http_client=http_client) as (
            read,
            write,
            _get_id,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "stock_zh_a_hist",
                    {
                        "symbol": ticker,
                        "period": "daily",
                        "adjust": "",
                    },
                )
                rows = []
                for c in result.content:
                    if isinstance(c, TextContent):
                        rows.extend(parse_mcp_table(c.text))
                if not rows:
                    return []

                prices = []
                for r in rows:
                    date_str = r.get("日期", "")
                    if not date_str:
                        continue
                    prices.append(
                        {
                            "date": _date.fromisoformat(str(date_str)[:10]),
                            "open": to_float(r.get("开盘")),
                            "high": to_float(r.get("最高")),
                            "low": to_float(r.get("最低")),
                            "close": to_float(r.get("收盘")),
                            "volume": to_float(r.get("成交量", 0)) or 0,
                        }
                    )
                return prices
    finally:
        await http_client.aclose()


async def fetch_news_via_mcp_cloud(ticker: str) -> list[dict]:
    """Fetch news via cloud MCP server's stock_news_em tool."""
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.types import TextContent

    CLOUD_MCP_URL = "http://8.137.104.120:8088/mcp"
    http_client = httpx.AsyncClient(verify=False, timeout=15)
    try:
        async with streamable_http_client(CLOUD_MCP_URL, http_client=http_client) as (
            read,
            write,
            _get_id,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("stock_news_em", {"symbol": ticker})
                news = []
                for c in result.content:
                    if isinstance(c, TextContent):
                        parsed = _parse_news_table_from_mcp(c.text)
                        news.extend(parsed)
                if news:
                    return news
    finally:
        await http_client.aclose()
    return []


def _parse_news_table_from_mcp(text: str) -> list[dict]:
    """Parse pandas DataFrame text from MCP into list of news dicts."""
    lines = text.strip().split("\n")
    if len(lines) < 2:
        return []
    header_idx = -1
    for i, line in enumerate(lines):
        if "新闻标题" in line:
            header_idx = i
            break
    if header_idx < 0:
        return []
    results = []
    for line in lines[header_idx + 1 :]:
        if not line.strip() or "---" in line:
            continue
        parts = [p.strip() for p in line.split() if p.strip()]
        if len(parts) >= 3:
            results.append(
                {
                    "title": parts[1] if len(parts) > 1 else "",
                    "content": parts[2][:300] if len(parts) > 2 else "",
                    "publish_time": parts[3] if len(parts) > 3 else "",
                    "source": parts[4] if len(parts) > 4 else "",
                    "url": parts[5] if len(parts) > 5 else "",
                }
            )
    return results
