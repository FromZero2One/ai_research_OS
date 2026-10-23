"""全市场快照交易日缓存单测 — 同一交易日第二次 run 直接复用，不重新拉取。"""

from __future__ import annotations

import json
from typing import Any

import pytest

import screener.screening as screening
from core.interfaces import LLMResponse

SPOT = [
    {"ticker": "600519", "name": "贵州茅台", "price": 1500.0, "turnover": 0.3, "market_cap": 1.88e12},
]


class FakeCache:
    """内存版 cache 接口（对齐 core.cache 的 get/set 语义）。"""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        self.store[key] = value
        self.set_calls.append((key, value, ttl or 0))


@pytest.fixture
def cache(monkeypatch):
    c = FakeCache()
    monkeypatch.setattr(screening, "_get_cache", lambda: c)
    return c


class TestSpotCache:
    async def test_second_call_same_day_uses_cache(self, cache, monkeypatch):
        """同交易日第二次调用命中缓存：fetch 只执行一次。"""
        calls = 0

        async def _fetch():
            nonlocal calls
            calls += 1
            return list(SPOT)

        monkeypatch.setattr(screening, "_fetch_market_spot_raw", _fetch)

        first = await screening.fetch_market_spot()
        second = await screening.fetch_market_spot()

        assert calls == 1
        assert second == first == SPOT

    async def test_cache_payload_roundtrip(self, cache, monkeypatch):
        """缓存 payload 序列化/反序列化后数据一致（含 None 字段）。"""
        rows = [{"ticker": "600519", "name": "贵州茅台", "price": 1500.0,
                 "turnover": None, "market_cap": None}]

        async def _fetch():
            return rows

        monkeypatch.setattr(screening, "_fetch_market_spot_raw", _fetch)

        first = await screening.fetch_market_spot()
        second = await screening.fetch_market_spot()
        assert second == first
        assert second[0]["turnover"] is None

    async def test_corrupted_cache_falls_back_to_fetch(self, cache, monkeypatch):
        """缓存内容损坏时静默回源，不抛异常。"""
        calls = 0

        async def _fetch():
            nonlocal calls
            calls += 1
            return list(SPOT)

        monkeypatch.setattr(screening, "_fetch_market_spot_raw", _fetch)
        # 预置一个损坏的缓存值（fetch_market_spot 计算出同 key）
        key = screening._spot_cache_key()
        cache.store[key] = "not-json{{"

        out = await screening.fetch_market_spot()
        assert calls == 1
        assert out == SPOT

    async def test_cache_failure_does_not_break_fetch(self, monkeypatch):
        """Redis 故障时降级为直接拉取（缓存是加分项）。"""

        class BrokenCache:
            async def get(self, key):
                raise ConnectionError("redis down")

            async def set(self, key, value, ttl=None):
                raise ConnectionError("redis down")

        monkeypatch.setattr(screening, "_get_cache", lambda: BrokenCache())
        calls = 0

        async def _fetch():
            nonlocal calls
            calls += 1
            return list(SPOT)

        monkeypatch.setattr(screening, "_fetch_market_spot_raw", _fetch)

        out = await screening.fetch_market_spot()
        assert calls == 1
        assert out == SPOT

    async def test_force_refresh_bypasses_cache(self, cache, monkeypatch):
        """force_refresh=True 跳过读缓存但仍回写。"""
        calls = 0

        async def _fetch():
            nonlocal calls
            calls += 1
            return list(SPOT)

        monkeypatch.setattr(screening, "_fetch_market_spot_raw", _fetch)

        await screening.fetch_market_spot()
        second = await screening.fetch_market_spot(force_refresh=True)

        assert calls == 2
        assert second == SPOT
