"""Abstract interfaces (Protocols) for all external adapters.

Core layer defines *what* — implementations live in infrastructure/ or
each module's adapter sub-package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from market.domain import FinancialMetricEntry

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

    async def upsert(self, collection: str, records: list[VectorRecord]) -> None: ...

    async def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 10,
        score_threshold: float | None = None,
        filter_: dict | None = None,
    ) -> list[VectorRecord]: ...

    async def delete(self, collection: str, ids: list[str]) -> None: ...

    async def create_collection(self, collection: str, dimension: int) -> None: ...


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
        metric: str | None = None,
        fiscal_year: int | None = None,
    ) -> list[FinancialMetricEntry]: ...

    async def upsert_financials(self, ticker: str, metrics: list[FinancialMetricEntry]) -> int: ...


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


# ──  Knowledge  ────────────────────────────────────────────────────────


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


@runtime_checkable
class ScreenerService(Protocol):
    """Interface for the LLM stock screener orchestration."""

    async def trigger_run(self, params: dict) -> Any:
        """手动触发一次筛选（presets 模式）；已有进行中运行时返回 None。"""
        ...


# ── Remaining business services (containerized in B7) ────────────────────


@runtime_checkable
class CompanyService(Protocol):
    """Interface for read-only company lookup (CRUD/thesis retired)."""

    async def search(
        self,
        query: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Any], int]: ...


@runtime_checkable
class DocumentService(Protocol):
    """Interface for document lifecycle: ingest → parse → chunk → embed → index."""

    async def process_upload(
        self,
        file_bytes: bytes,
        filename: str,
        title: str | None = None,
        doc_type: str | None = None,
        company_id: Any | None = None,
    ) -> Any: ...

    async def create(self, **kwargs) -> Any: ...

    async def get(self, document_id: Any) -> Any: ...

    async def search(
        self,
        query: str | None = None,
        doc_type: str | None = None,
        company_id: Any | None = None,
        is_indexed: bool | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Any], int]: ...

    async def delete(self, document_id: Any) -> None: ...


# ── Remaining business services (containerized in B7) ────────────────────
