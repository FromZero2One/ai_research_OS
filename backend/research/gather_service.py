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
        self,
        session: AsyncSession,
        evidence_service: EvidenceService | None = None,
        session_service: SessionService | None = None,
    ) -> None:
        self.session = session
        self.evidence = evidence_service or EvidenceService(session)
        self.sessions = session_service or SessionService(session)

    async def auto_gather(
        self,
        session_id: uuid.UUID,
        use_plan: bool = True,
    ) -> dict:
        """Auto-gather evidence from Knowledge Center and Market Center."""
        from knowledge.service import KnowledgeService
        from market.service.financial_service import FinancialService
        from market.service.price_service import PriceService

        session = await self.sessions.get(session_id)
        question = session.question
        plan = (session.extra_metadata or {}).get(PLAN_KEY)

        search_queries = [question]
        if use_plan and plan:
            # sub_questions 为 ResearchPlanItem 对象（含 text/priority），提取文本
            search_queries.extend(
                _sub_question_texts(plan.get("sub_questions", []))[:5]
            )

        knowledge = KnowledgeService(self.session)
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
                    # 证据质量评分：按文档类型映射引用等级
                    citation_quality=_citation_quality_for_doc(result.doc_type),
                    reliability=_reliability_for_document(result.score, result.doc_type),
                )
                count += 1

        # 2. Market data if company is set
        if session.company_id:
            try:
                from company.service import CompanyService

                company_svc = CompanyService(self.session)
                company = await company_svc.get(session.company_id)

                market_prices = PriceService(self.session)
                market_financials = FinancialService(self.session)

                # 2a. Recent prices
                prices = await market_prices.get_prices(company.ticker, limit=30)
                latest = prices[-1] if prices else None
                if prices and latest:
                    closes = [p.close for p in prices if p.close is not None]
                    range_str = f"High={max(closes):.2f} Low={min(closes):.2f}" if closes else "n/a"
                    price_summary = (
                        f"Recent price data for {company.ticker}:\n"
                        f"Latest: {latest.date} Close={latest.close:.2f} "
                        f"Vol={latest.volume:.0f}\n"
                        f"30d Range: {range_str}"
                    )
                    await self.evidence.add(
                        session_id=session_id,
                        content=price_summary,
                        source_type="market_data",
                        source_id=company.ticker,
                        source_title=f"{company.ticker} Price (30d)",
                        relevance_score=0.7,
                        evidence_type="neutral",
                        # 行情数据可靠性高、新鲜度按最新数据日期计算
                        reliability=0.9,
                        citation_quality="institutional",
                        data_freshness=_hours_since(latest.date),
                    )
                    count += 1

                # 2b. Financial metrics
                try:
                    financials = await market_financials.get_financials(company.ticker)
                    if financials:
                        fin_lines = []
                        for f in financials[:10]:
                            fin_lines.append(
                                f"{f.fiscal_year}-{f.fiscal_period}: "
                                f"{f.metric_name} = {f.metric_value}"
                            )
                        if fin_lines:
                            await self.evidence.add(
                                session_id=session_id,
                                content=(
                                    "Financial metrics for "
                                    + company.ticker
                                    + ":\n"
                                    + "\n".join(fin_lines)
                                ),
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


def _sub_question_texts(items) -> list[str]:
    """从计划子问题（字符串或 ResearchPlanItem 字典）提取纯文本。"""
    texts = []
    for item in items or []:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, dict) and item.get("text"):
            texts.append(item["text"])
    return texts


def _citation_quality_for_doc(doc_type: str | None) -> str:
    """按文档类型映射引用质量等级。"""
    mapping = {
        "sec_10k": "institutional",
        "sec_10q": "institutional",
        "report": "analyst",
        "transcript": "analyst",
        "news_article": "internal",
    }
    return mapping.get(doc_type or "", "internal")


def _reliability_for_document(score: float, doc_type: str | None) -> float:
    """文档证据可靠性 = 检索得分 × 文档类型权重，上限 0.95。"""
    type_weight = {
        "sec_10k": 1.0,
        "sec_10q": 0.95,
        "report": 0.85,
        "transcript": 0.75,
        "markdown": 0.7,
        "pdf": 0.8,
        "news_article": 0.6,
    }.get(doc_type or "", 0.7)
    return round(min(0.95, score * type_weight), 2)


def _hours_since(d) -> int:
    """计算距某日期的小时数（行情/财报数据新鲜度）。"""
    from datetime import datetime
    from datetime import time as dt_time

    ref = datetime.combine(d, dt_time.min)
    return max(0, int((datetime.now() - ref).total_seconds() // 3600))
