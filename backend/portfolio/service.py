"""
DEPRECATED: PortfolioService has been split into focused services.

Use the new imports instead:
    from portfolio.service import WatchlistService, HoldingService, JournalService
    # or from the individual submodules:
    from portfolio.service.watchlist_service import WatchlistService
    from portfolio.service.holding_service import HoldingService
    from portfolio.service.journal_service import JournalService
"""
# Imports below intentionally happen after the deprecation warning.
# ruff: noqa: E402

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "portfolio.service is deprecated — import from the specific submodules "
    "(portfolio.service.watchlist_service, holding_service, journal_service)",
    DeprecationWarning,
    stacklevel=2,
)

from portfolio.service.holding_service import HoldingService  # noqa: F401
from portfolio.service.journal_service import JournalService  # noqa: F401
from portfolio.service.watchlist_service import WatchlistService  # noqa: F401

# Backward-compatible alias: PortfolioService -> watchlist service was the most
# used aggregate; map it to the watchlist service for drop-in compatibility.
PortfolioService = WatchlistService  # noqa: F401
