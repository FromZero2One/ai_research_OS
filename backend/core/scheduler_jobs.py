"""Scheduled job registry — re-exports from focused modules.

Implementation lives in:
    - ``core.market_sync``      → market_data_update
    - ``core.brief_generator``  → morning_brief (+ prompts, thresholds)
    - ``core.news_fetcher``     → news fetching helpers
    - ``core.observation_engine`` → observation_cycle

This module is kept as a thin compat shim so ``api.app`` wiring and any
existing imports keep working unchanged.
"""

from __future__ import annotations

from core.brief_generator import (
    FOCUS_THRESHOLD_CHANGE,
    FOCUS_THRESHOLD_DAYS,
    OVERVIEW_PROMPT,
    STOCK_BRIEF_PROMPT,
    morning_brief,
)
from core.market_sync import market_data_update

__all__ = [
    "FOCUS_THRESHOLD_CHANGE",
    "FOCUS_THRESHOLD_DAYS",
    "OVERVIEW_PROMPT",
    "STOCK_BRIEF_PROMPT",
    "market_data_update",
    "morning_brief",
]
