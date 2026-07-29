"""Evidence gathering — auto-collect from Knowledge Center and Market Center."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import logger
from research.evidence_service import EvidenceService
from research.planner import PLAN_KEY
from research.session_service import SessionService


class GatherService:
    """Orchestrates automatic evidence gathering from various sources."""

    def __init__(
        self, session: AsyncSession,
        evidence_service: EvidenceService | None = None,
        session_service: SessionService | None = None,
    ) -> None:
        self.session = session
        self.evidence = evidence_service or EvidenceService(session)
        self.sessions = session_service or SessionService(session)

    async def auto_gather(
        self,
        session_id: uuid.UUID,
        db: AsyncSession,
        use_plan: bool = True,
    ) -> dict:
        """Auto-gather evidence from Knowledge Center and Market Center."""
        from knowledge.service import KnowledgeService
        from market.price_service import PriceService
        from market.financial_service import FinancialService

        session = await self.sessions.get(session_id)
        question = session.question
        plan = (session.extra_metadata or {}).get(PLAN_KEY)

        search_queries = [question]
        if use_plan and plan:
            search_queries.extend(plan.get("sub_questions", [])[:5])

        knowledge = KnowledgeService(db)
        seen_sources: set[str] = set()
        count = 0

        # 1. Knowledge base search
        for query in search_queries:
            results = await knowledge.search(query, top_k=3)
            for result in results:
                dedup_key = f"{result.document_id}:{result.chunk_index}"
                if dedup_key in seen_sources:
                    continue
                seen_sources.add(dedup_key)

                evidence_type = EvidenceService.classify(result.content, query)
                await self.evidence.add(
                    session_id=session_id,
                    content=result.content[:2000],
                    source_type="document",
                    source_id=result.document_id,
                    source_title=result.title,
                    relevance_score=result.score,
                    evidence_type=evidence_type,
                )
                count += 1

        # 2. Market data if company is set
        if session.company_id:
            try:
                from company.service import CompanyService

                company_svc = CompanyService(db)
                company = await company_svc.get(session.company_id)

                market_prices = PriceService(db)
                market_financials = FinancialService(db)

                # 2a. Recent prices
                prices = await market_prices.get_prices(company.ticker, limit=30)
                latest = prices[-1] if prices else None
                if prices and latest:
                    price_summary = (
                        f"Recent price data for {company.ticker}:\n"
                        f"Latest: {latest.date} Close={latest.close:.2f} "
                        f"Vol={latest.volume:.0f}\n"
                        f"30d Range: High={max(p.close for p in prices):.2f} "
                        f"Low={min(p.close for p in prices):.2f}"
                    )
                    await self.evidence.add(
                        session_id=session_id,
                        content=price_summary,
                        source_type="market_data",
                        source_id=company.ticker,
                        source_title=f"{company.ticker} Price (30d)",
                        relevance_score=0.7,
                        evidence_type="neutral",
                    )
                    count += 1

                # 2b. Financial metrics
                try:
                    financials = await market_financials.get_financials(company.ticker)
                    if financials:
                        fin_lines = []
                        from market.models import FinancialMetric
                        for f in financials[:10]:
                            fin_lines.append(
                                f"{f.fiscal_year}-{f.fiscal_period}: "
                                f"{f.metric_name} = {f.metric_value}"
                            )
                        if fin_lines:
                            await self.evidence.add(
                                session_id=session_id,
                                content="Financial metrics for " + company.ticker + ":\n" + "\n".join(fin_lines),
                                source_type="market_data",
                                source_id=company.ticker,
                                source_title=f"{company.ticker} Financials",
                                relevance_score=0.8,
                                evidence_type="neutral",
                            )
                            count += 1
                except Exception:
                    logger.warning("Failed to fetch financials during auto-gather")
                    pass
            except Exception:
                logger.warning("Failed to fetch company/market data during auto-gather")
                pass

        return {
            "session_id": str(session_id),
            "evidences_added": count,
            "searched_queries": len(search_queries),
        }
