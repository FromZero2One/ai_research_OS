"""Research Center service — the core workflow engine.

This is the most important module in the system. The flow:

  Question → Evidence Gathering → Analysis → Report → Thesis → Decision
"""

from __future__ import annotations

import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.event_service import EventLogger
from core.exceptions import NotFoundError
from research.models import ResearchEvidence, ResearchReport, ResearchSession


class ResearchService:
    """Research workflow orchestration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)

    # ── Sessions ──────────────────────────────────────────────────

    async def create_session(
        self,
        title: str,
        question: str,
        context: str | None = None,
        company_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
    ) -> ResearchSession:
        session = ResearchSession(
            title=title,
            question=question,
            context=context,
            company_id=company_id,
            status="draft",
            tags=tags,
        )
        self.session.add(session)
        await self.session.flush()
        await self.session.refresh(session)

        await self.events.record(
            source="research",
            event_type="research.started",
            entity_type="research_session",
            entity_id=str(session.id),
            payload={
                "title": title,
                "question": question[:200],
                "company_id": str(company_id) if company_id else None,
            },
        )
        return session

    async def get_session(
        self, session_id: uuid.UUID, eager: bool = False
    ) -> ResearchSession:
        stmt = select(ResearchSession).where(ResearchSession.id == session_id)
        if eager:
            stmt = stmt.options(
                selectinload(ResearchSession.evidences),
                selectinload(ResearchSession.reports),
            )
        result = await self.session.execute(stmt)
        session = result.scalar_one_or_none()
        if not session:
            raise NotFoundError("ResearchSession", str(session_id))
        return session

    async def list_sessions(
        self,
        status: str | None = None,
        company_id: uuid.UUID | None = None,
        query: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[ResearchSession], int]:
        stmt = select(ResearchSession)

        if status:
            stmt = stmt.where(ResearchSession.status == status)
        if company_id:
            stmt = stmt.where(ResearchSession.company_id == company_id)
        if query:
            stmt = stmt.where(
                ResearchSession.title.ilike(f"%{query}%")
                | ResearchSession.question.ilike(f"%{query}%")
            )

        # Count
        count_result = await self.session.execute(
            stmt.with_only_columns(ResearchSession.id).order_by(None)
        )
        total = len(count_result.all())

        stmt = stmt.order_by(desc(ResearchSession.created_at)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def update_session(
        self, session_id: uuid.UUID, **kwargs
    ) -> ResearchSession:
        session = await self.get_session(session_id)

        for key, val in kwargs.items():
            if val is not None and hasattr(session, key):
                setattr(session, key, val)

        await self.session.flush()

        # Log significant transitions
        if "status" in kwargs and kwargs["status"]:
            await self.events.record(
                source="research",
                event_type=f"research.{kwargs['status']}",
                entity_type="research_session",
                entity_id=str(session.id),
                payload={"title": session.title},
            )

        await self.session.refresh(session)
        return session

    async def delete_session(self, session_id: uuid.UUID) -> None:
        session = await self.get_session(session_id)
        await self.session.delete(session)

    # ── Evidence ──────────────────────────────────────────────────

    async def add_evidence(
        self, session_id: uuid.UUID, **kwargs
    ) -> ResearchEvidence:
        # Verify session exists
        session = await self.get_session(session_id)
        if session.status == "completed":
            # Allow adding evidence but don't change status
            pass

        evidence = ResearchEvidence(session_id=session_id, **kwargs)
        self.session.add(evidence)

        # Auto-transition to researching if still in draft
        if session.status == "draft":
            session.status = "researching"

        await self.session.flush()
        await self.session.refresh(evidence)

        await self.events.record(
            entity_type="research_evidence",
            entity_id=str(evidence.id),
            payload={
                "session_id": str(session_id),
                "source_type": kwargs.get("source_type"),
                "evidence_type": kwargs.get("evidence_type"),
            },
        )
        return evidence

    async def get_evidences(
        self, session_id: uuid.UUID
    ) -> list[ResearchEvidence]:
        result = await self.session.execute(
            select(ResearchEvidence)
            .where(ResearchEvidence.session_id == session_id)
            .order_by(ResearchEvidence.created_at.desc())
        )
        return list(result.scalars().all())

    async def remove_evidence(self, evidence_id: uuid.UUID) -> None:
        result = await self.session.execute(
            select(ResearchEvidence).where(ResearchEvidence.id == evidence_id)
        )
        evidence = result.scalar_one_or_none()
        if not evidence:
            raise NotFoundError("ResearchEvidence", str(evidence_id))
        await self.session.delete(evidence)

    # ── Reports ───────────────────────────────────────────────────

    async def create_report(
        self,
        session_id: uuid.UUID,
        title: str,
        content: str,
        format_: str = "markdown",
        is_final: bool = False,
    ) -> ResearchReport:
        session = await self.get_session(session_id)

        # Determine version
        result = await self.session.execute(
            select(ResearchReport)
            .where(ResearchReport.session_id == session_id)
            .order_by(ResearchReport.version.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        version = (latest.version + 1) if latest else 1

        report = ResearchReport(
            session_id=session_id,
            title=title,
            content=content,
            format=format_,
            version=version,
            is_final=is_final,
        )
        self.session.add(report)

        if is_final:
            session.status = "completed"

        await self.session.flush()
        await self.session.refresh(report)

        await self.events.record(
            entity_type="research_report",
            entity_id=str(report.id),
            payload={
                "session_id": str(session_id),
                "title": title,
                "version": version,
                "is_final": is_final,
            },
        )
        return report

    async def get_reports(
        self, session_id: uuid.UUID
    ) -> list[ResearchReport]:
        result = await self.session.execute(
            select(ResearchReport)
            .where(ResearchReport.session_id == session_id)
            .order_by(ResearchReport.version.desc())
        )
        return list(result.scalars().all())

    async def finalize_thesis(
        self,
        session_id: uuid.UUID,
        thesis: str,
        decision: str,
        confidence: float,
    ) -> ResearchSession:
        """Finalize the research with a thesis and decision."""
        session = await self.get_session(session_id)
        session.thesis = thesis
        session.decision = decision
        session.confidence = confidence
        session.status = "completed"

        await self.session.flush()

        await self.events.record(
            source="research",
            event_type="research.completed",
            entity_type="research_session",
            entity_id=str(session.id),
            payload={
                "title": session.title,
                "decision": decision,
                "confidence": confidence,
            },
        )
        await self.session.refresh(session)
        return session

    # ── AI-Assisted Research (V1) ─────────────────────────────────

    async def auto_gather_evidence(
        self,
        session_id: uuid.UUID,
        db: AsyncSession,
    ) -> int:
        """Auto-gather evidence from Knowledge Center and Market Center.

        Uses the question to search indexed documents and market data,
        then adds relevant findings as evidence.
        """
        from knowledge.service import KnowledgeService
        from market.service import MarketService

        session = await self.get_session(session_id)
        question = session.question

        count = 0

        # 1. Search knowledge base
        knowledge = KnowledgeService(db)
        search_results = await knowledge.search(question, top_k=5)
        for result in search_results:
            await self.add_evidence(
                session_id=session_id,
                content=result.content[:2000],
                source_type="document",
                source_id=result.document_id,
                source_title=result.title,
                relevance_score=result.score,
                evidence_type="supporting",
            )
            count += 1

        # 2. Get market data if company is set
        if session.company_id:
            from company.service import CompanyService

            company_svc = CompanyService(db)
            company = await company_svc.get(session.company_id)

            market = MarketService(db)
            prices = await market.get_prices(company.ticker, limit=30)
            if prices:
                price_summary = "\n".join(
                    f"{p.date}: Open={p.open}, Close={p.close}, Vol={p.volume}"
                    for p in prices[:10]
                )
                await self.add_evidence(
                    session_id=session_id,
                    content=f"Recent price data for {company.ticker}:\n{price_summary}",
                    source_type="market_data",
                    source_id=company.ticker,
                    source_title=f"{company.ticker} Price Data",
                    relevance_score=0.8,
                    evidence_type="supporting",
                )
                count += 1

        return count
