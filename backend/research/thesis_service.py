"""Thesis finalization — structured thesis + decision."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.event_service import EventLogger
from core.exceptions import NotFoundError
from research.models import ResearchSession
from research.planner import ResearchPlanner


class ThesisService:
    """Finalize research with structured thesis and decision."""

    def __init__(self, session: AsyncSession, planner: ResearchPlanner | None = None) -> None:
        self.session = session
        self.events = EventLogger(session)
        self.planner = planner or ResearchPlanner()

    async def finalize(
        self,
        session_id: uuid.UUID,
        thesis: str,
        decision: str,
        confidence: float,
    ) -> ResearchSession:
        result = await self.session.execute(
            select(ResearchSession)
            .where(ResearchSession.id == session_id)
            .options(selectinload(ResearchSession.reports))
        )
        session = result.scalar_one_or_none()
        if not session:
            raise NotFoundError("ResearchSession", str(session_id))

        # Find latest final report content
        report_content = ""
        for r in sorted(session.reports, key=lambda x: x.version, reverse=True):
            if r.is_final:
                report_content = r.content or ""
                break
        if not report_content:
            report_content = thesis

        structured = await self.planner.generate_structured_thesis(thesis, decision, report_content)

        session.thesis = thesis
        session.decision = decision
        session.confidence = confidence
        session.status = "completed"
        session.extra_metadata = session.extra_metadata or {}
        session.extra_metadata["structured_thesis"] = structured

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
                "structured_thesis": structured,
            },
        )
        await self.session.refresh(session)
        return session
