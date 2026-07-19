"""Abstract interfaces (Protocols) for all external adapters.

Core layer defines *what* — implementations live in infrastructure/ or
each module's adapter sub-package.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


# ──  Embedding  ──────────────────────────────────────────────────────

@runtime_checkable
class EmbeddingModel(Protocol):
    """Interface for text embedding models."""

    @property
    def dimension(self) -> int: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


# ──  Vector Store  ───────────────────────────────────────────────────

@dataclass
class VectorRecord:
    id: str
    vector: list[float]
    payload: dict
    score: float | None = None


@runtime_checkable
class VectorStore(Protocol):
    """Interface for vector databases (Qdrant, etc.)."""

    async def upsert(
        self, collection: str, records: list[VectorRecord]
    ) -> None: ...

    async def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 10,
        score_threshold: float | None = None,
        filter_: dict | None = None,
    ) -> list[VectorRecord]: ...

    async def delete(self, collection: str, ids: list[str]) -> None: ...

    async def create_collection(
        self, collection: str, dimension: int
    ) -> None: ...


# ──  LLM  ────────────────────────────────────────────────────────────

@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict | None = None


@runtime_checkable
class LLM(Protocol):
    """Interface for large language models."""

    @property
    def model_name(self) -> str: ...

    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> LLMResponse: ...

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        schema: dict,
        temperature: float = 0.3,
    ) -> dict: ...


# ──  Document Parser  ────────────────────────────────────────────────

@dataclass
class ParsedDocument:
    text: str
    metadata: dict
    chunks: list[str] | None = None


@runtime_checkable
class DocumentParser(Protocol):
    """Interface for parsing raw documents into text."""

    async def parse(self, content: bytes, filename: str) -> ParsedDocument: ...

    def supported_extensions(self) -> set[str]: ...


# ──  Market Data Provider  ───────────────────────────────────────────

@dataclass
class MarketPrice:
    symbol: str
    price: float
    volume: float
    timestamp: str
    high: float | None = None
    low: float | None = None
    open_: float | None = None
    close: float | None = None


@runtime_checkable
class MarketDataProvider(Protocol):
    """Interface for external market data sources."""

    async def get_prices(
        self, symbols: list[str]
    ) -> dict[str, MarketPrice]: ...

    async def get_financials(
        self, symbol: str
    ) -> dict: ...

    async def search_symbols(self, query: str) -> list[dict]: ...


# ──  Cache  ──────────────────────────────────────────────────────────

@runtime_checkable
class Cache(Protocol):
    """Interface for cache backends (Redis, in-memory, etc.)."""

    async def get(self, key: str) -> str | None: ...

    async def set(
        self, key: str, value: str, ttl: int | None = None
    ) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...
