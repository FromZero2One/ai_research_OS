"""
Fallback — MySQL 无数据时，依次尝试：

  1. 本地 akshare_mcp（subprocess → uv run）
  2. 云端 akshare_mcp（HTTP MCP → 8.137.104.120:8088）

Usage:
    python fallback_client.py query_stock 600519
    python fallback_client.py search_stocks 茅台
"""

from __future__ import annotations

import asyncio
import httpx
import json
import os
import subprocess
import sys

AKSHARE_MCP_DIR = os.getenv("AKSHARE_MCP_DIR", "/home/wsm/codes/akshare_mcp")
CLOUD_MCP_URL = os.getenv("CLOUD_MCP_URL", "http://8.137.104.120:8088/mcp")


# ═══════════════════════════════════════════════════════════════════════
#  第 2 层: 本地 akshare（subprocess → uv run）
# ═══════════════════════════════════════════════════════════════════════


def _run_akshare(code: str) -> str | None:
    """Run akshare Python code in akshare_mcp venv and return stdout."""
    env = os.environ.copy()
    env["ALL_PROXY"] = ""
    env["all_proxy"] = ""
    env["no_proxy"] = "localhost,127.0.0.0/8,::1"
    try:
        result = subprocess.run(
            ["uv", "run", "--directory", AKSHARE_MCP_DIR, "python", "-c", code],
            capture_output=True, text=True, timeout=60, env=env,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except Exception:
        return None


def _query_local(symbol: str) -> dict | None:
    """本地 akshare: 查名称/行业/K线。"""
    code = f"""
import json, sys
import akshare as ak
try:
    df = ak.stock_info_a_code_name()
    match = df[df['code'] == '{symbol}']
    name = str(match.iloc[0]['name']).strip() if len(match) else None
    sector = None
    try:
        df_f = ak.stock_yjbb_em(date='')
        row = df_f[df_f['股票代码'] == '{symbol}']
        if len(row):
            sector = str(row.iloc[0].get('所处行业', '')) or None
    except: pass
    has_kline = False
    try:
        df_k = ak.stock_zh_a_hist(symbol='{symbol}', period='daily')
        has_kline = len(df_k) > 0
    except: pass
    print("__R__:" + json.dumps(
        {{"symbol": "{symbol}", "name": name, "sector": sector, "has_kline": has_kline}},
        ensure_ascii=False))
except Exception as e:
    print("__E__:" + str(e), file=sys.stderr)
"""
    stdout = _run_akshare(code)
    if not stdout:
        return None
    for line in stdout.splitlines():
        if line.startswith("__R__:"):
            return json.loads(line[6:])
    return None


def _search_local(query: str, limit: int = 20) -> list[dict]:
    """本地 akshare: 搜索股票。"""
    code = f"""
import json, sys
import akshare as ak
try:
    df = ak.stock_info_a_code_name()
    q = '{query}'.lower()
    results = []
    for _, row in df.iterrows():
        code = str(row['code'])
        name = str(row['name']).strip()
        if q in code.lower() or q in name.lower():
            results.append({{"symbol": code, "name": name}})
            if len(results) >= {limit}:
                break
    print("__R__:" + json.dumps(results, ensure_ascii=False))
except Exception as e:
    print("__E__:" + str(e), file=sys.stderr)
"""
    stdout = _run_akshare(code)
    if not stdout:
        return []
    for line in stdout.splitlines():
        if line.startswith("__R__:"):
            return json.loads(line[6:])
    return []


# ═══════════════════════════════════════════════════════════════════════
#  第 3 层: 云端 akshare_mcp（HTTP MCP Client）
# ═══════════════════════════════════════════════════════════════════════

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent


def _parse_df_table(text: str) -> list[dict]:
    """粗糙解析 pandas DataFrame 文本表格 → list[dict]。

    FastMCP 会把 DataFrame 序列化成这种格式:
        "   股票代码  股票简称  ...  所处行业\n0  600519  贵州茅台  ...  白酒Ⅱ\n"
    只取第一行数据行（我们只查单只股票）。
    """
    lines = text.strip().split("\n")
    if len(lines) < 2:
        return []

    # 表头: "   股票代码  股票简称  ...  所处行业"
    header_line = lines[0]
    headers = [h for h in header_line.split("  ") if h.strip()]
    # 清理表头空格
    headers = [h.strip() for h in headers]

    # 数据行: "0  600519  贵州茅台  ...  白酒Ⅱ"
    results = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = [p for p in line.replace("...", "").split("  ") if p.strip()]
        # 跳过行号
        if parts and parts[0].isdigit():
            parts = parts[1:]
        if len(parts) == len(headers):
            results.append(dict(zip(headers, parts)))
        elif len(parts) > 0:
            # 不完美匹配也尽量返回
            row = {}
            for i, h in enumerate(headers):
                row[h] = parts[i] if i < len(parts) else ""
            results.append(row)
    return results


async def _call_cloud_tool(tool_name: str, args: dict) -> list[dict]:
    """通过 HTTP MCP 调用云端 akshare_mcp 的工具。"""
    # 清除代理 env，httpx 会读取 all_proxy
    old_all = os.environ.pop("all_proxy", None)
    old_ALL = os.environ.pop("ALL_PROXY", None)
    try:
        http_client = httpx.AsyncClient(verify=False)
        try:
            async with streamable_http_client(CLOUD_MCP_URL, http_client=http_client) as (read, write, _get_id):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, args)
                    rows = []
                    for c in result.content:
                        if isinstance(c, TextContent):
                            rows.extend(_parse_df_table(c.text))
                    return rows
        finally:
            await http_client.aclose()
    except Exception as e:
        print(f"  [cloud] {tool_name} error: {e}", file=sys.stderr)
        return []
    finally:
        # 恢复代理 env
        if old_all is not None:
            os.environ["all_proxy"] = old_all
        if old_ALL is not None:
            os.environ["ALL_PROXY"] = old_ALL


async def _query_cloud(symbol: str) -> dict | None:
    """云端 akshare: 查名称/行业/K线。"""
    # Step 1: stock_yjbb_em → 名称 + 行业
    name = None
    sector = None
    rows = await _call_cloud_tool("stock_yjbb_em", {"date": ""})
    for row in rows:
        if row.get("股票代码") == symbol:
            name = row.get("股票简称")
            sector = row.get("所处行业")
            break

    if not name:
        return None

    # Step 2: stock_zh_a_hist → K线状态
    has_kline = False
    klines = await _call_cloud_tool("stock_zh_a_hist", {
        "symbol": symbol, "period": "daily", "adjust": "qfq",
    })
    has_kline = len(klines) > 0

    return {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "has_kline": has_kline,
    }


async def _search_cloud(query: str, limit: int = 20) -> list[dict]:
    """云端 akshare: 搜索股票。"""
    rows = await _call_cloud_tool("stock_yjbb_em", {"date": ""})
    q = query.lower()
    results = []
    for row in rows:
        code = str(row.get("股票代码", ""))
        name = row.get("股票简称", "")
        if q in code.lower() or q in name.lower():
            results.append({"symbol": code, "name": name})
            if len(results) >= limit:
                break
    return results


# ═══════════════════════════════════════════════════════════════════════
#  统一入口
# ═══════════════════════════════════════════════════════════════════════


def query_stock(symbol: str) -> dict | None:
    """三层降级: MySQL → 本地 akshare → 云端 akshare。"""
    # 第 2 层: 本地
    result = _query_local(symbol)
    if result and result.get("name"):
        result["_source"] = "local_akshare"
        return result

    # 第 3 层: 云端
    result = asyncio.run(_query_cloud(symbol))
    if result and result.get("name"):
        result["_source"] = "cloud_akshare"
        return result

    return None


def search_stocks(query: str, limit: int = 20) -> list[dict]:
    """搜索: MySQL → 本地 akshare → 云端 akshare。"""
    # 第 2 层: 本地
    results = _search_local(query, limit)
    if results:
        return results

    # 第 3 层: 云端
    return asyncio.run(_search_cloud(query, limit))


def main():
    if len(sys.argv) < 3:
        print("Usage: fallback_client.py <command> <args...>")
        print("Commands: query_stock <symbol>, search_stocks <query> [limit]")
        sys.exit(1)

    command = sys.argv[1]
    if command == "query_stock":
        result = query_stock(sys.argv[2])
        print(json.dumps(result, ensure_ascii=False) if result else "null")
    elif command == "search_stocks":
        query = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 20
        results = search_stocks(query, limit)
        print(json.dumps(results, ensure_ascii=False))
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
