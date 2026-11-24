"""Screener 领域异常。"""

from __future__ import annotations


class ScreenerDiffError(Exception):
    """变化日报参数非法（如基线与当前运行相同）。"""
