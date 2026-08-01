"""Evidence CRUD — add, list, remove, and classify."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.event_service import EventLogger
from core.exceptions import NotFoundError
from research.models import ResearchEvidence


class EvidenceService:
    """Manage research evidence items."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)

    async def add(self, session_id: uuid.UUID, **kwargs) -> ResearchEvidence:
        # Verify session exists
        from research.models import ResearchSession

        result = await self.session.execute(
            select(ResearchSession).where(ResearchSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise NotFoundError("ResearchSession", str(session_id))

        evidence = ResearchEvidence(session_id=session_id, **kwargs)
        self.session.add(evidence)

        if session.status == "draft":
            session.status = "researching"

        await self.session.flush()
        await self.session.refresh(evidence)

        await self.events.record(
            source="research",
            event_type="evidence.added",
            entity_type="research_evidence",
            entity_id=str(evidence.id),
            payload={
                "session_id": str(session_id),
                "source_type": kwargs.get("source_type"),
                "evidence_type": kwargs.get("evidence_type"),
            },
        )
        return evidence

    async def list(self, session_id: uuid.UUID) -> list[ResearchEvidence]:
        result = await self.session.execute(
            select(ResearchEvidence)
            .where(ResearchEvidence.session_id == session_id)
            .order_by(ResearchEvidence.created_at.desc())
        )
        return list(result.scalars().all())

    async def remove(self, evidence_id: uuid.UUID) -> None:
        result = await self.session.execute(
            select(ResearchEvidence).where(ResearchEvidence.id == evidence_id)
        )
        evidence = result.scalar_one_or_none()
        if not evidence:
            raise NotFoundError("ResearchEvidence", str(evidence_id))
        await self.session.delete(evidence)

    @staticmethod
    def classify(content: str, query: str) -> str:
        """Simple heuristic to classify evidence type.

        V1: keyword-based. V2+ will use LLM for nuanced classification.
        """
        content_lower = content.lower()
        positive_words = {
            "growth",
            "increase",
            "profit",
            "record",
            "strong",
            "positive",
            "expanded",
            "leadership",
            "advantage",
            "opportunity",
        }
        negative_words = {
            "decline",
            "decrease",
            "loss",
            "risk",
            "threat",
            "weak",
            "challenge",
            "uncertainty",
            "regulation",
            "competition",
        }

        pos_count = sum(1 for w in positive_words if w in content_lower)
        neg_count = sum(1 for w in negative_words if w in content_lower)

        if pos_count > neg_count + 1:
            return "supporting"
        elif neg_count > pos_count + 1:
            return "opposing"
        return "neutral"
