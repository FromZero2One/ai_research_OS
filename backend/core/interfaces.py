"""Abstract interfaces (Protocols) for all external adapters.

Core layer defines *what* — implementations live in infrastructure/ or
each module's adapter sub-package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


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


# ──  Market sub-services  ──────────────────────────────────────────────

@runtime_checkable
class PriceService(Protocol):
    """Interface for stock price queries and ingestion."""

    async def get_prices(
        self,
        ticker: str,
        start_date: Any | None = None,
        end_date: Any | None = None,
        limit: int = 100,
    ) -> list[Any]: ...

    async def fetch_and_store_prices(
        self, ticker: str, provider: str = "akshare"
    ) -> tuple[int, list[str]]: ...

    async def upsert_prices(self, ticker: str, prices: list[dict]) -> int: ...


@runtime_checkable
class NewsService(Protocol):
    """Interface for news fetching."""

    async def fetch_news(self, ticker: str) -> tuple[list[dict], str]: ...


@runtime_checkable
class FinancialService(Protocol):
    """Interface for financial metrics queries and ingestion."""

    async def get_financials(
        self,
        ticker: str,
        fiscal_year: int | None = None,
        fiscal_quarter: int | None = None,
    ) -> list[Any]: ...

    async def upsert_financials(
        self, ticker: str, metrics: list[Any]
    ) -> int: ...


@runtime_checkable
class ProfileService(Protocol):
    """Interface for company profile / stock info."""

    async def get_stock_info(self, ticker: str) -> dict | None: ...

    async def get_stock_profile(self, ticker: str) -> dict | None: ...


@runtime_checkable
class SearchService(Protocol):
    """Interface for stock search and symbol listing."""

    async def search_stocks(self, query: str, limit: int = 20) -> list[dict]: ...

    async def list_available_symbols(self, limit: int = 100) -> list[dict]: ...


# ──  Research services  ────────────────────────────────────────────────

@runtime_checkable
class ResearchSessionService(Protocol):
    """Interface for research session lifecycle management."""

    async def create(self, title: str, question: str, **kwargs) -> Any: ...

    async def get(self, session_id: Any, eager: bool = False) -> Any: ...

    async def list(
        self, status: str | None = None, **kwargs
    ) -> tuple[list[Any], int]: ...

    async def update(self, session_id: Any, **kwargs) -> Any: ...

    async def delete(self, session_id: Any) -> None: ...

    async def generate_plan(self, session_id: Any) -> dict: ...

    async def get_plan(self, session_id: Any) -> dict | None: ...


@runtime_checkable
class ResearchEvidenceService(Protocol):
    """Interface for research evidence management."""

    async def add(self, session_id: Any, **kwargs) -> Any: ...

    async def list(self, session_id: Any) -> list[Any]: ...

    async def remove(self, evidence_id: Any) -> None: ...


@runtime_checkable
class ResearchReportService(Protocol):
    """Interface for research report generation."""

    async def create(
        self, session_id: Any, title: str, content: str, **kwargs
    ) -> Any: ...

    async def list(self, session_id: Any) -> list[Any]: ...

    async def auto_generate(self, session_id: Any, **kwargs) -> Any: ...


@runtime_checkable
class WatchlistService(Protocol):
    """Interface for watchlist CRUD and item management."""

    async def create_watchlist(
        self, name: str, description: str | None = None
    ) -> Any: ...

    async def get_watchlist(self, watchlist_id: Any) -> Any: ...

    async def list_watchlists(self) -> list[Any]: ...

    async def delete_watchlist(self, watchlist_id: Any) -> None: ...

    async def update_watchlist(self, watchlist_id: Any, **kwargs) -> Any: ...

    async def add_to_watchlist(
        self, watchlist_id: Any, ticker: str, **kwargs
    ) -> Any: ...

    async def remove_from_watchlist(self, item_id: Any) -> None: ...


@runtime_checkable
class HoldingService(Protocol):
    """Interface for holding (position) management."""

    async def add_holding(self, ticker: str, shares: float, **kwargs) -> Any: ...

    async def get_holdings(self, active_only: bool = True) -> list[Any]: ...

    async def update_holding(self, holding_id: Any, **kwargs) -> Any: ...

    async def close_holding(self, holding_id: Any) -> Any: ...


@runtime_checkable
class JournalService(Protocol):
    """Interface for investment journal management."""

    async def create_journal_entry(self, **kwargs) -> Any: ...

    async def list_journal(
        self,
        entry_type: str | None = None,
        ticker: str | None = None,
        limit: int = 50,
    ) -> list[Any]: ...

    async def get_journal_entry(self, entry_id: Any) -> Any: ...


@runtime_checkable
class KnowledgeService(Protocol):
    """Interface for hybrid RAG retrieval (dense + sparse)."""

    async def search(
        self,
        query: str,
        top_k: int = 10,
        doc_type: str | None = None,
        min_score: float = 0.0,
    ) -> list[Any]: ...

    async def search_by_document(
        self,
        query: str,
        document_id: str,
        top_k: int = 5,
    ) -> list[Any]: ...

