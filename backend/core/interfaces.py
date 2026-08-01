"""Abstract interfaces (Protocols) for all external adapters.

Core layer defines *what* — implementations live in infrastructure/ or
each module's adapter sub-package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ai.models import AIWorkflow, PromptTemplate
    from market.domain import FinancialMetricEntry
    from research.models import ResearchReport, ResearchSession

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


# ──  Research services  ────────────────────────────────────────────────


@runtime_checkable
class ResearchSessionService(Protocol):
    """Interface for research session lifecycle management."""

    async def create(
        self,
        title: str,
        question: str,
        context: str | None = None,
        company_id: Any | None = None,
        tags: list[str] | None = None,
        auto_plan: bool = True,
    ) -> ResearchSession: ...

    async def get(self, session_id: Any, eager: bool = False) -> ResearchSession: ...

    async def list(
        self,
        status: str | None = None,
        company_id: Any | None = None,
        query: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[ResearchSession], int]: ...

    async def update(self, session_id: Any, **kwargs) -> ResearchSession: ...

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
        self,
        session_id: Any,
        title: str,
        content: str,
        format_: str = "markdown",
        is_final: bool = False,
    ) -> ResearchReport: ...

    async def list(self, session_id: Any) -> list[ResearchReport]: ...

    async def auto_generate(self, session_id: Any, is_final: bool = False) -> ResearchReport: ...


@runtime_checkable
class ResearchGatherService(Protocol):
    """Interface for evidence gathering (knowledge + market data)."""

    async def auto_gather(
        self,
        session_id: Any,
        use_plan: bool = True,
    ) -> Any: ...


@runtime_checkable
class ResearchThesisService(Protocol):
    """Interface for research finalization (thesis + decision)."""

    async def finalize(
        self,
        session_id: Any,
        thesis: str,
        decision: str,
        confidence: float,
    ) -> Any: ...


@runtime_checkable
class TimelineService(Protocol):
    """Interface for cross-session research timeline + report diff."""

    async def get_company_timeline(self, ticker: str) -> dict: ...

    async def get_report_diff(
        self,
        report_id: Any,
        other_version: int,
    ) -> Any: ...

    async def get_session_timeline(self, session_id: Any) -> dict: ...


@runtime_checkable
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


# ── Remaining business services (containerized in B7) ────────────────────


@runtime_checkable
class CompanyService(Protocol):
    """Interface for company profile / thesis / workspace management."""

    async def create(self, ticker: str, name: str, **kwargs) -> Any: ...

    async def get(self, company_id: Any) -> Any: ...

    async def get_by_ticker(self, ticker: str) -> Any | None: ...

    async def search(
        self,
        query: str | None = None,
        sector: str | None = None,
        industry: str | None = None,
        tag: str | None = None,
        is_active: bool | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Any], int]: ...

    async def update(self, company_id: Any, data: dict) -> Any: ...

    async def delete(self, company_id: Any) -> None: ...

    async def get_thesis(self, ticker: str) -> dict | None: ...

    async def get_workspace(self, ticker: str) -> dict | None: ...


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


@runtime_checkable
class AIService(Protocol):
    """Interface for prompt management and LLM orchestration."""

    async def create_template(self, **kwargs) -> PromptTemplate: ...

    async def get_template(self, template_id: str) -> PromptTemplate: ...

    async def update_template(self, template_id: str, **kwargs) -> PromptTemplate: ...

    async def delete_template(self, template_id: str) -> None: ...

    async def list_templates(self) -> list[PromptTemplate]: ...

    async def generate(
        self,
        prompt_name: str,
        variables: dict | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> dict: ...

    async def summarize(
        self,
        text: str,
        max_length: int = 500,
        format_: str = "paragraph",
    ) -> dict: ...

    async def extract(self, text: str, schema: dict) -> dict: ...

    async def create_workflow(self, **kwargs) -> AIWorkflow: ...

    async def execute_workflow(self, workflow_id: str, input_data: dict) -> Any: ...


@runtime_checkable
class DashboardService(Protocol):
    """Interface for aggregated dashboard data."""

    async def get_dashboard(self) -> dict[str, Any]: ...

    async def get_market_overview(self) -> list[dict[str, Any]]: ...

    async def get_latest_brief(self) -> dict[str, Any] | None: ...

    async def get_watchlist_summary(self) -> list[dict[str, Any]]: ...
