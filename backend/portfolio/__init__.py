"""Portfolio Center — watchlists, holdings, investment journal.

Facade:
    PortfolioFacade — aggregates the sub-services (watchlist, holding,
    journal) so callers can use one entry point.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from portfolio.service.holding_service import HoldingService
from portfolio.service.journal_service import JournalService
from portfolio.service.watchlist_service import WatchlistService


class PortfolioFacade:
    """Aggregation facade over the portfolio sub-services."""

    def __init__(self, session: AsyncSession) -> None:
        self.watchlists = WatchlistService(session)
        self.holdings = HoldingService(session)
        self.journal = JournalService(session)
