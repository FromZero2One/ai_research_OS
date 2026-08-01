"""
DEPRECATED: MarketService has been split into focused services.

Use the new imports instead:
    from market.service.price_service import PriceService
    from market.service.financial_service import FinancialService
    from market.service.search_service import SearchService
    from market.service.profile_service import ProfileService
    from market.service.news_service import NewsService
    from market.akshare_executor import is_a_stock, run_akshare, tx_symbol
"""
# Imports below intentionally happen after the deprecation warning.
# ruff: noqa: E402

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "market.service is deprecated — import from the specific submodules "
    "(service.price_service, service.financial_service, service.search_service, "
    "service.profile_service, service.news_service, akshare_executor)",
    DeprecationWarning,
    stacklevel=2,
)

from market.akshare_executor import is_a_stock  # noqa: F401
from market.service.price_service import PriceService as MarketService  # noqa: F401
