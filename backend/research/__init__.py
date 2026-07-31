"""Research Center — the core user workflow: question → evidence → report → decision.

Facade:
    ResearchFacade — aggregates the sub-services (session, evidence, report)
    so callers can use one entry point.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from research.evidence_service import EvidenceService
from research.report_service import ReportService
from research.session_service import SessionService


class ResearchFacade:
    """Aggregation facade over the research sub-services."""

    def __init__(self, session: AsyncSession) -> None:
        self.sessions = SessionService(session)
        self.evidence = EvidenceService(session)
        self.reports = ReportService(session)
