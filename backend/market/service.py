"""
DEPRECATED: MarketService has been split into focused services.

Use the new imports instead:
    from market.price_service import PriceService
    from market.financial_service import FinancialService
    from market.search_service import SearchService
    from market.profile_service import ProfileService
    from market.news_service import NewsService
    from market.akshare_executor import is_a_stock, run_akshare, tx_symbol
"""

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "market.service is deprecated — import from the specific submodules "
    "(price_service, financial_service, search_service, profile_service, "
    "news_service, akshare_executor)",
    DeprecationWarning,
    stacklevel=2,
)

from market.price_service import PriceService as MarketService  # noqa: F401
from market.akshare_executor import is_a_stock  # noqa: F401
