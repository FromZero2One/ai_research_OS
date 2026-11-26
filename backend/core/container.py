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
    from market.service.freshness_service import FreshnessService

from core.interfaces import (
    CompanyService as CompanyServiceProtocol,
)
from core.interfaces import (
    DocumentService as DocumentServiceProtocol,
)
from core.interfaces import (
    FinancialService as FinancialServiceProtocol,
)
from core.interfaces import (
    KnowledgeService as KnowledgeServiceProtocol,
)
from core.interfaces import (
    PriceService as PriceServiceProtocol,
)
from core.interfaces import (
    ProfileService as ProfileServiceProtocol,
)
from core.interfaces import (
    ScreenerService as ScreenerServiceProtocol,
)
from core.interfaces import (
    SearchService as SearchServiceProtocol,
)


class Container:
    """Service graph — one per request/session scope."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        # Lazily built on first access.
        self._price: PriceServiceProtocol | None = None
        self._financial: FinancialServiceProtocol | None = None
        self._profile: ProfileServiceProtocol | None = None
        self._search: SearchServiceProtocol | None = None
        self._freshness: FreshnessService | None = None
        self._knowledge: KnowledgeServiceProtocol | None = None
        self._company: CompanyServiceProtocol | None = None
        self._document: DocumentServiceProtocol | None = None
        self._screener: ScreenerServiceProtocol | None = None

    @property
    def price_service(self) -> PriceServiceProtocol:
        if self._price is None:
            from market.service.price_service import PriceService

            self._price = PriceService(self.session)
        return self._price

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
    def knowledge_service(self) -> KnowledgeServiceProtocol:
        if self._knowledge is None:
            import importlib.util

            from knowledge.service import KnowledgeService

            # Cross-encoder re-ranker improves precision on top of hybrid RRF, but
            # it needs sentence-transformers + a cached model. Without them every
            # search wastes time on a failed model load, so gate on availability.
            has_reranker = (
                importlib.util.find_spec("sentence_transformers") is not None
            )
            self._knowledge = KnowledgeService(
                self.session, use_reranker=has_reranker
            )
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
    def screener_service(self) -> ScreenerServiceProtocol:
        if self._screener is None:
            from screener.service import ScreenerService

            self._screener = ScreenerService(self.session)
        return self._screener


def create_container(session: AsyncSession) -> Container:
    """Build a container bound to the given session."""
    return Container(session)
