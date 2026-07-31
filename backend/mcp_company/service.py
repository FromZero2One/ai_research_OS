"""MCP Company tools — call backend services directly, no HTTP self-calls.

These are the same tools previously implemented in mcp-company/server.py,
but now they import and call backend service functions directly.

Usage:
    from mcp_company.service import create_company, search_stocks, import_stocks
"""

from __future__ import annotations

from core.database import managed_session
from core.exceptions import DuplicateError
from core.logging import logger
from core.task_manager import run_in_background

# ── Tool implementations ──────────────────────────────────────────────────


async def create_company(symbol: str) -> str:
    """创建公司：查股票信息 → 创建公司 → 刷新财务数据。

    参数:
        symbol: 股票代码（如 600519、000001）
    """
    from company.service import CompanyService
    from market.service.profile_service import ProfileService
    from market.service.search_service import SearchService

    async with managed_session() as session:
        search_svc = SearchService(session)
        profile_svc = ProfileService(session)
        company_svc = CompanyService(session)

        # 1. Try to get stock info via profile
        info = await profile_svc.get_stock_profile(symbol)
        name = info.get("name", "") if info else ""
        sector = info.get("sector", "") if info else ""
        tags = info.get("tags", []) if info else []

        if not name:
            # No profile — try searching
            hint = await _search_hint(symbol, search_svc)
            return hint if hint else f"未找到股票代码 {symbol}"

        # 2. Create company (handles duplicate detection)
        try:
            company = await company_svc.create(
                ticker=symbol,
                name=name,
                sector=sector,
                tags=tags,
            )
        except DuplicateError:
            return f"ℹ️ 公司 {symbol} ({name}) 已存在"

        # 3. Fire background refresh (profile + financials)
        await run_in_background("background_refresh", symbol, {"ticker": symbol})

        tags_str = ", ".join(tags) if tags else "无"
        return (
            f"✅ 已创建公司:\n"
            f"   · 代码: {company.ticker}\n"
            f"   · 名称: {company.name}\n"
            f"   · 行业: {sector or '未知'}\n"
            f"   · 标签: {tags_str}"
        )


async def search_stocks(query: str, limit: int = 10) -> str:
    """搜索后端股票数据库。

    参数:
        query: 搜索关键词（代码或名称）
        limit: 返回结果数量上限
    """
    from market.service.search_service import SearchService

    async with managed_session() as session:
        svc = SearchService(session)
        results = await svc.search_stocks(query, limit)

    if not results:
        return f"未找到匹配 '{query}' 的股票"

    lines = [f"找到 {len(results)} 只股票:"]
    for s in results:
        lines.append(f"  {s.get('symbol', '?'):>8s}  {s.get('name', '?')}")
    return "\n".join(lines)


async def import_stocks(limit: int = 50) -> str:
    """批量导入 akshare 股票到公司中心。

    参数:
        limit: 本次导入数量上限（默认 50）
    """
    from company.service import CompanyService
    from market.service.search_service import SearchService

    async with managed_session() as session:
        search_svc = SearchService(session)
        company_svc = CompanyService(session)

        # 1. Get available symbols
        symbols = await search_svc.list_available_symbols(limit)
        if not symbols:
            return "后端无股票数据"

        created = 0
        skipped = 0
        errors: list[str] = []
        results_list: list[str] = []

        for entry in symbols:
            symbol = entry.get("symbol", "") if isinstance(entry, dict) else str(entry)
            name = entry.get("name", "") if isinstance(entry, dict) else ""

            if not symbol:
                continue

            try:
                company = await company_svc.create(
                    ticker=symbol,
                    name=name or symbol,
                )
                created += 1
                results_list.append(f"✅ {symbol} {company.name}")
            except DuplicateError:
                skipped += 1
            except Exception as e:
                errors.append(f"❌ {symbol}: {str(e)[:80]}")

        # Fire background refresh for new companies
        if created > 0:
            for ticker in [r.split(" ")[1] for r in results_list]:
                await run_in_background("background_refresh", f"batch_{ticker}", {"ticker": ticker})

        lines = [
            f"导入完成: 成功 {created}, 跳过(已存在) {skipped}",
            *(["", "新增:"] + results_list[:10] if created > 0 else []),
            *([f"... 还有 {created - 10} 只未显示" if created > 10 else ""]),
            *([""] + errors if errors else []),
        ]
        return "\n".join(line for line in lines if line)


# ── Helpers ───────────────────────────────────────────────────────────────


async def _search_hint(symbol: str, search_svc=None) -> str:
    """搜索相似股票代码，返回提示信息。"""
    from market.service.search_service import SearchService

    if search_svc is None:
        async with managed_session() as session:
            search_svc = SearchService(session)

    try:
        results = await search_svc.search_stocks(symbol, limit=5)
        if results:
            hints = ", ".join(f"{s['symbol']}({s['name']})" for s in results)
            return f"未找到 {symbol}。你是不是想找: {hints}"
    except Exception:
        pass
    return ""


async def _run_background_refresh(payload: dict) -> dict | None:
    """Registered handler for 'background_refresh' tasks."""
    ticker = payload.get("ticker", "")
    if not ticker:
        return None
    try:
        async with managed_session() as session:
            from market.service.profile_service import ProfileService
            from market.service.financial_service import FinancialService

            profile_svc = ProfileService(session)
            fin_svc = FinancialService(session)

            await profile_svc.fetch_and_store_company_profile(ticker)
            await fin_svc.ingest_financials(ticker)

            logger.info("  [mcp] background refresh complete for %s", ticker)
            return {"ticker": ticker, "status": "ok"}
    except Exception as e:
        logger.warning("  [mcp] background refresh failed for %s: %s", ticker, e)
        raise


from core.task_manager import register_handler  # noqa: E402

register_handler("background_refresh", _run_background_refresh)
