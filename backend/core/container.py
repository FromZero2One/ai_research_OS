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

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces import (
    FinancialService as FinancialServiceProtocol,
    HoldingService as HoldingServiceProtocol,
    JournalService as JournalServiceProtocol,
    KnowledgeService as KnowledgeServiceProtocol,
    NewsService as NewsServiceProtocol,
    PriceService as PriceServiceProtocol,
    ProfileService as ProfileServiceProtocol,
    ResearchEvidenceService as ResearchEvidenceServiceProtocol,
    ResearchReportService as ResearchReportServiceProtocol,
    ResearchSessionService as ResearchSessionServiceProtocol,
    SearchService as SearchServiceProtocol,
    WatchlistService as WatchlistServiceProtocol,
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
        self._freshness: "FreshnessService | None" = None
        self._session: ResearchSessionServiceProtocol | None = None
        self._evidence: ResearchEvidenceServiceProtocol | None = None
        self._report: ResearchReportServiceProtocol | None = None
        self._watchlist: WatchlistServiceProtocol | None = None
        self._holding: HoldingServiceProtocol | None = None
        self._journal: JournalServiceProtocol | None = None
        self._knowledge: KnowledgeServiceProtocol | None = None

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
    def freshness_service(self) -> "FreshnessService":
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
    def watchlist_service(self) -> WatchlistServiceProtocol:
        if self._watchlist is None:
            from portfolio.service.watchlist_service import WatchlistService
            self._watchlist = WatchlistService(self.session)
        return self._watchlist

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
            self._knowledge = KnowledgeService(self.session)
        return self._knowledge


# Sentinel/helper type for anything the container can provide.
ServiceLike = Protocol


def create_container(session: AsyncSession) -> Container:
    """Build a container bound to the given session."""
    return Container(session)
