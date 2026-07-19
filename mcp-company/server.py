"""
company-mcp-server: 公司中心 MCP 服务

通过 akshare MySQL 查询股票信息，自动创建到 AI Research OS 的公司中心。

工具:
  create_company  — 按股票代码创建公司（查 akshare MySQL 获取详细信息）
  search_stocks   — 搜索 akshare 中的股票
  import_stocks   — 批量导入股票到公司中心
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any

import pymysql

# ── 配置 ───────────────────────────────────────────────────────────────

AKSHARE_MYSQL = {
    "host": os.getenv("AKSHARE_DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("AKSHARE_DB_PORT", "3306")),
    "user": os.getenv("AKSHARE_DB_USER", "root"),
    "password": os.getenv("AKSHARE_DB_PASSWORD", "root"),
    "database": os.getenv("AKSHARE_DB_NAME", "akshare"),
    "charset": "utf8mb4",
}

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


# ── MySQL 查询 ─────────────────────────────────────────────────────────

def query_stock(symbol: str) -> dict | None:
    """查 akshare MySQL 获取一只股票的信息。"""
    conn = pymysql.connect(**AKSHARE_MYSQL)
    try:
        with conn.cursor() as cur:
            # 查名称
            cur.execute(
                "SELECT stock_name FROM stock_name_entity WHERE symbol = %s LIMIT 1",
                (symbol,),
            )
            row = cur.fetchone()
            if not row:
                return None
            name = row[0]

            # 查估值数据（用于行业判断）
            sector = None
            cur.execute(
                "SELECT `所处行业` FROM stock_yjbb_em WHERE `股票代码` = %s LIMIT 1",
                (symbol,),
            )
            row = cur.fetchone()
            if row:
                sector = row[0]

            # 查是否有 K 线数据
            cur.execute(
                "SELECT COUNT(*) FROM stock_zh_a_hist WHERE symbol = %s",
                (symbol,),
            )
            has_kline = cur.fetchone()[0] > 0

            return {
                "symbol": symbol,
                "name": name,
                "sector": sector,
                "has_kline": has_kline,
            }
    finally:
        conn.close()


def search_stocks_db(query: str, limit: int = 20) -> list[dict]:
    """搜索 akshare MySQL 中的股票。"""
    conn = pymysql.connect(**AKSHARE_MYSQL)
    try:
        with conn.cursor() as cur:
            like = f"%{query}%"
            cur.execute(
                "SELECT symbol, stock_name FROM stock_name_entity "
                "WHERE symbol LIKE %s OR stock_name LIKE %s LIMIT %s",
                (like, like, limit),
            )
            return [
                {"symbol": r[0], "name": r[1]} for r in cur.fetchall()
            ]
    finally:
        conn.close()


def list_all_stocks(limit: int = 100, offset: int = 0) -> list[dict]:
    """列出 akshare MySQL 中的股票。"""
    conn = pymysql.connect(**AKSHARE_MYSQL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT symbol, stock_name FROM stock_name_entity "
                "ORDER BY symbol LIMIT %s OFFSET %s",
                (limit, offset),
            )
            return [
                {"symbol": r[0], "name": r[1]} for r in cur.fetchall()
            ]
    finally:
        conn.close()


# ── 调用后端 API ──────────────────────────────────────────────────────

def call_api(method: str, path: str, body: dict | None = None) -> dict:
    """调用 AI Research OS 的后端 API。"""
    url = f"{BACKEND_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()[:200]
        raise RuntimeError(f"API {method} {path} 失败: {e.code} {error_body}")


# ── MCP 工具实现 ──────────────────────────────────────────────────────

def create_company(symbol: str) -> str:
    """创建公司：查 akshare MySQL → 调用后端 API。

    参数:
        symbol: 股票代码（如 600519、000001）
    """
    # 1. 查 akshare MySQL
    info = query_stock(symbol)
    if not info:
        stocks = search_stocks_db(symbol, limit=5)
        if stocks:
            hints = ", ".join(f"{s['symbol']}({s['name']})" for s in stocks)
            return f"未找到 {symbol}。你是不是想找: {hints}"
        return f"未找到股票代码 {symbol}"

    # 2. 构造公司数据
    tags = []
    if info["sector"]:
        # 从行业名称提取标签
        sector = info["sector"].replace("Ⅱ", "").replace("Ⅰ", "")
        tags.append(sector[:10])
    if info["has_kline"]:
        tags.append("kline")

    body = {
        "ticker": info["symbol"],
        "name": info["name"],
        "sector": info["sector"] or "",
        "tags": tags,
    }

    # 3. 调用后端
    result = call_api("POST", "/api/v1/companies", body)
    return (
        f"✅ 已创建公司:\n"
        f"   · 代码: {info['symbol']}\n"
        f"   · 名称: {info['name']}\n"
        f"   · 行业: {info['sector'] or '未知'}\n"
        f"   · 标签: {', '.join(tags) if tags else '无'}\n"
        f"   · 有 K 线数据: {'是' if info['has_kline'] else '否'}"
    )


def search_stocks(query: str, limit: int = 10) -> str:
    """搜索 akshare 股票数据库。

    参数:
        query: 搜索关键词（代码或名称）
        limit: 返回结果数量上限
    """
    stocks = search_stocks_db(query, limit)
    if not stocks:
        return f"未找到匹配 '{query}' 的股票"

    lines = [f"找到 {len(stocks)} 只股票:"]
    for s in stocks:
        # 查是否有 K 线数据
        info = query_stock(s["symbol"])
        has_data = "📊" if info and info["has_kline"] else ""
        lines.append(f"  {s['symbol']:>8s}  {s['name']}  {has_data}")
    return "\n".join(lines)


def import_stocks(limit: int = 50) -> str:
    """批量导入 akshare 股票到公司中心。

    参数:
        limit: 本次导入数量上限（默认 50）
    """
    stocks = list_all_stocks(limit=limit)
    if not stocks:
        return "akshare 数据库中暂无股票数据"

    created = 0
    skipped = 0
    errors = []
    results = []

    for s in stocks:
        try:
            info = query_stock(s["symbol"])
            tags = []
            if info and info["sector"]:
                sector = info["sector"].replace("Ⅱ", "").replace("Ⅰ", "")
                tags.append(sector[:10])

            body = {
                "ticker": s["symbol"],
                "name": s["name"],
                "sector": (info["sector"] or "") if info else "",
                "tags": tags,
            }
            call_api("POST", "/api/v1/companies", body)
            created += 1
            results.append(f"✅ {s['symbol']} {s['name']}")
        except RuntimeError as e:
            if "already exists" in str(e) or "duplicate" in str(e).lower():
                skipped += 1
            else:
                errors.append(f"❌ {s['symbol']}: {str(e)[:80]}")

    lines = [
        f"导入完成: 成功 {created}, 跳过(已存在) {skipped}",
        *(["", "新增:"] + results[:10] if created > 0 else []),
        *([f"... 还有 {created - 10} 只未显示" if created > 10 else ""]),
        *([""] + errors if errors else []),
    ]
    return "\n".join(line for line in lines if line)


# ── MCP 入口 ───────────────────────────────────────────────────────────

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import Tool, TextContent
import mcp.server.stdio


async def main():
    server = Server("company-mcp-server")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="create_company",
                description="按股票代码创建公司（从 akshare 获取详细信息）",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "股票代码，如 600519, 000001, 601398",
                        },
                    },
                    "required": ["symbol"],
                },
            ),
            Tool(
                name="search_stocks",
                description="搜索 akshare 数据库中的股票",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词（代码或名称）",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回结果数量上限",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="import_stocks",
                description="批量导入 akshare 股票到公司中心",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "本次导入数量上限",
                            "default": 50,
                        },
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            if name == "create_company":
                result = create_company(arguments["symbol"])
            elif name == "search_stocks":
                result = search_stocks(
                    arguments["query"],
                    arguments.get("limit", 10),
                )
            elif name == "import_stocks":
                result = import_stocks(arguments.get("limit", 50))
            else:
                raise ValueError(f"未知工具: {name}")

            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=f"错误: {e}")]

    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(
            read,
            write,
            InitializationOptions(
                server_name="company-mcp-server",
                server_version="0.1.0",
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
