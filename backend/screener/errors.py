"""Screener 领域异常。"""

from __future__ import annotations


class ScreenerCancelled(Exception):
    """用户请求取消运行；由编排层转成 cancelled 状态。"""
