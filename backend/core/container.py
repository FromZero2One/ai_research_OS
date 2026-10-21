"""Dependency injection container.

A tiny, explicit DI container. The container owns construction of
services and their dependencies, so routes/facades request services by
dependency without wiring them by hand. For a small local app, an
explicit ``Container`` class beats a full DI framework: it is greppable,
has no magic, and keeps the graph in one place.

Lifecycle:
    - ``create_container(session)`` builds a container bound to one DB
      session. Routes obtain it via ``request.app.state.container`` (set in
      app lifespan) and call ``container.price_service`` etc.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from market.ratio_service import RatioService
    from market.service.freshness_service import FreshnessService

from core.interfaces import (
    AIService as AIServiceProtocol,
)
from core.interfaces import (
    CompanyService as CompanyServiceProtocol,
)
from core.interfaces import (
    DashboardService as DashboardServiceProtocol,
)
from core.interfaces import (
    DocumentService as DocumentServiceProtocol,
)
from core.interfaces import (
    FinancialService as FinancialServiceProtocol,
)
from core.interfaces import (
    HoldingService as HoldingServiceProtocol,
)
from core.interfaces import (
    JournalService as JournalServiceProtocol,
)
from core.interfaces import (
    KnowledgeService as KnowledgeServiceProtocol,
)
from core.interfaces import (
    NewsService as NewsServiceProtocol,
)
from core.interfaces import (
    PriceService as PriceServiceProtocol,
)
from core.interfaces import (
    ProfileService as ProfileServiceProtocol,
)
from core.interfaces import (
    ResearchEvidenceService as ResearchEvidenceServiceProtocol,
)
from core.interfaces import (
    ResearchGatherService as ResearchGatherServiceProtocol,
)
from core.interfaces import (
    ResearchReportService as ResearchReportServiceProtocol,
)
from core.interfaces import (
    ResearchSessionService as ResearchSessionServiceProtocol,
)
from core.interfaces import (
    ResearchThesisService as ResearchThesisServiceProtocol,
)
from core.interfaces import (
    SearchService as SearchServiceProtocol,
)
from core.interfaces import (
    ScreenerService as ScreenerServiceProtocol,
)
from core.interfaces import (
    TimelineService as TimelineServiceProtocol,
)


class Container:
    """Service graph — one per request/session scope."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        # Lazily built on first access.
        self._price: PriceServiceProtocol | None = None
        self._news: NewsServiceProtocol | None = None
        self._financial: FinancialServiceProtocol | None = None
        self._profile: ProfileServiceProtocol | None = None
        self._search: SearchServiceProtocol | None = None
        self._freshness: FreshnessService | None = None
        self._session: ResearchSessionServiceProtocol | None = None
        self._evidence: ResearchEvidenceServiceProtocol | None = None
        self._report: ResearchReportServiceProtocol | None = None
        self._gather: ResearchGatherServiceProtocol | None = None
        self._thesis: ResearchThesisServiceProtocol | None = None
        self._timeline: TimelineServiceProtocol | None = None
        self._holding: HoldingServiceProtocol | None = None
        self._journal: JournalServiceProtocol | None = None
        self._knowledge: KnowledgeServiceProtocol | None = None
        self._company: CompanyServiceProtocol | None = None
        self._document: DocumentServiceProtocol | None = None
        self._ai: AIServiceProtocol | None = None
        self._dashboard: DashboardServiceProtocol | None = None
        self._ratio: "RatioService | None" = None
        self._screener: ScreenerServiceProtocol | None = None

    @property
    def price_service(self) -> PriceServiceProtocol:
        if self._price is None:
            from market.service.price_service import PriceService

            self._price = PriceService(self.session)
        return self._price

    @property
    def news_service(self) -> NewsServiceProtocol:
        if self._news is None:
            from market.service.news_service import NewsService

            self._news = NewsService(self.session)
        return self._news

    @property
    def financial_service(self) -> FinancialServiceProtocol:
        if self._financial is None:
            from market.service.financial_service import FinancialService

            self._financial = FinancialService(self.session)
        return self._financial

    @property
    def profile_service(self) -> ProfileServiceProtocol:
        if self._profile is None:
            from market.service.profile_service import ProfileService

            self._profile = ProfileService(self.session)
        return self._profile

    @property
    def search_service(self) -> SearchServiceProtocol:
        if self._search is None:
            from market.service.search_service import SearchService

            self._search = SearchService(self.session)
        return self._search

    @property
    def freshness_service(self) -> FreshnessService:
        if self._freshness is None:
            from market.service.freshness_service import FreshnessService

            self._freshness = FreshnessService(self.session)
        return self._freshness

    @property
    def research_session_service(self) -> ResearchSessionServiceProtocol:
        if self._session is None:
            from research.session_service import SessionService

            self._session = SessionService(self.session)
        return self._session

    @property
    def research_evidence_service(self) -> ResearchEvidenceServiceProtocol:
        if self._evidence is None:
            from research.evidence_service import EvidenceService

            self._evidence = EvidenceService(self.session)
        return self._evidence

    @property
    def research_report_service(self) -> ResearchReportServiceProtocol:
        if self._report is None:
            from research.report_service import ReportService

            self._report = ReportService(self.session)
        return self._report

    @property
    def research_gather_service(self) -> ResearchGatherServiceProtocol:
        if self._gather is None:
            from research.gather_service import GatherService

            self._gather = GatherService(self.session)
        return self._gather

    @property
    def research_thesis_service(self) -> ResearchThesisServiceProtocol:
        if self._thesis is None:
            from research.thesis_service import ThesisService

            self._thesis = ThesisService(self.session)
        return self._thesis

    @property
    def timeline_service(self) -> TimelineServiceProtocol:
        if self._timeline is None:
            from research.timeline_service import TimelineService

            self._timeline = TimelineService(self.session)
        return self._timeline

    @property
    def holding_service(self) -> HoldingServiceProtocol:
        if self._holding is None:
            from portfolio.service.holding_service import HoldingService

            self._holding = HoldingService(self.session)
        return self._holding

    @property
    def journal_service(self) -> JournalServiceProtocol:
        if self._journal is None:
            from portfolio.service.journal_service import JournalService

            self._journal = JournalService(self.session)
        return self._journal

    @property
    def knowledge_service(self) -> KnowledgeServiceProtocol:
        if self._knowledge is None:
            from knowledge.service import KnowledgeService

            # Cross-encoder re-ranker improves precision on top of hybrid RRF;
            # search falls back to RRF automatically if the model is missing.
            self._knowledge = KnowledgeService(self.session, use_reranker=True)
        return self._knowledge

    @property
    def company_service(self) -> CompanyServiceProtocol:
        if self._company is None:
            from company.service import CompanyService

            self._company = CompanyService(self.session)
        return self._company

    @property
    def document_service(self) -> DocumentServiceProtocol:
        if self._document is None:
            from document.service import DocumentService

            self._document = DocumentService(self.session)
        return self._document

    @property
    def ai_service(self) -> AIServiceProtocol:
        if self._ai is None:
            from ai.service import AIService

            self._ai = AIService(self.session)
        return self._ai

    @property
    def dashboard_service(self) -> DashboardServiceProtocol:
        if self._dashboard is None:
            from dashboard.service import DashboardService

            self._dashboard = DashboardService(self.session)
        return self._dashboard

    @property
    def screener_service(self) -> ScreenerServiceProtocol:
        if self._screener is None:
            from screener.service import ScreenerService

            self._screener = ScreenerService(self.session)
        return self._screener

    @property
    def ratio_service(self) -> "RatioService":
        if self._ratio is None:
            from market.ratio_service import RatioService

            self._ratio = RatioService(self.session)
        return self._ratio


def create_container(session: AsyncSession) -> Container:
    """Build a container bound to the given session."""
    return Container(session)
