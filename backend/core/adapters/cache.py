"""Cache adapter — Redis-backed."""

from __future__ import annotations

import json
from functools import lru_cache

import redis.asyncio as aioredis

from core.config import settings
from core.interfaces import Cache


class RedisCache:
    """Redis-backed cache implementation."""

    def __init__(self, url: str = settings.REDIS_URL) -> None:
        self._client: aioredis.Redis | None = None
        self._url = url

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = await aioredis.from_url(
                self._url, decode_responses=True
            )
        return self._client

    async def get(self, key: str) -> str | None:
        client = await self._get_client()
        return await client.get(key)

    async def set(
        self, key: str, value: str, ttl: int | None = None
    ) -> None:
        client = await self._get_client()
        ttl = ttl or settings.REDIS_TTL
        await client.set(key, value, ex=ttl)  # type: ignore[arg-type]

    async def delete(self, key: str) -> None:
        client = await self._get_client()
        await client.delete(key)

    async def exists(self, key: str) -> bool:
        client = await self._get_client()
        return bool(await client.exists(key))

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # Helper: struct cache
    async def get_struct(self, key: str) -> dict | None:
        raw = await self.get(key)
        return json.loads(raw) if raw else None

    async def set_struct(self, key: str, value: dict, ttl: int | None = None) -> None:
        await self.set(key, json.dumps(value), ttl)


@lru_cache(maxsize=1)
def create_cache() -> RedisCache:
    return RedisCache()
