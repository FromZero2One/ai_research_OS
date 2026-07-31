"""Portfolio Center sub-services.

Re-exports the focused services so callers can do::

    from portfolio.service import WatchlistService, HoldingService, JournalService
"""

from __future__ import annotations

from portfolio.service.holding_service import HoldingService
from portfolio.service.journal_service import JournalService
from portfolio.service.watchlist_service import WatchlistService

# Backward-compatible alias: the old monolithic PortfolioService most commonly
# surfaced watchlist operations; map it to WatchlistService for drop-in compat.
# (No DeprecationWarning here: this module is imported on every container
# access, so a warning would spam logs.)
PortfolioService = WatchlistService  # noqa: F401

__all__ = [
    "WatchlistService",
    "HoldingService",
    "JournalService",
    "PortfolioService",
]
