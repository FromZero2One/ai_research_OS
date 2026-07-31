"""Market Center — structured financial data ingestion and storage.

Facade:
    MarketFacade — aggregates the sub-services (price, news, financial,
    profile, search) so callers can use one entry point. Each sub-service
    exposes a small Protocol defined in ``core.interfaces``.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from market.service.financial_service import FinancialService
from market.service.news_service import NewsService
from market.service.price_service import PriceService
from market.service.profile_service import ProfileService
from market.service.search_service import SearchService


class MarketFacade:
    """Aggregation facade over the market sub-services."""

    def __init__(self, session: AsyncSession) -> None:
        self.price = PriceService(session)
        self.news = NewsService(session)
        self.financial = FinancialService(session)
        self.profile = ProfileService(session)
        self.search = SearchService(session)
