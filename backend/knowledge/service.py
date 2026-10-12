"""Knowledge Center — Hybrid RAG search.

V1: Dense (Qdrant) + Sparse (BM25) reciprocal rank fusion.
No Knowledge Graph — that's V2.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import jieba
from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.embedding import create_embedding
from core.adapters.reranker import create_reranker
from core.adapters.vector_store import create_vector_store
from core.config import settings
from core.event_service import EventLogger
from core.interfaces import EmbeddingModel, VectorStore
from core.logging import logger
from document.models import Document, DocumentChunk

# Chinese function-word stopwords for BM25. Keeps high-frequency tokens like
# "如何/的/和" from outranking real content terms (e.g. "营收") in the sparse
# index — previously queries like "营收如何" ranked accounting-policy chunks
# full of "如何评估/如何管理" above actual revenue figures.
_BM25_STOPWORDS = {
    "的",
    "了",
    "和",
    "与",
    "及",
    "或",
    "等",
    "如何",
    "什么",
    "怎样",
    "怎么",
    "一个",
    "以及",
    "在",
    "是",
    "有",
    "为",
    "对",
    "中",
    "上",
    "下",
    "之",
    "其",
    "该",
    "本",
    "将",
    "已",
    "不",
    "也",
    "都",
    "而",
    "被",
    "于",
    "从",
    "向",
    "把",
    "让",
    "以",
    "就",
    "并",
    "且",
    "但",
    "因",
    "此",
    "若",
    "则",
    "再",
    "还",
    "要",
    "会",
    "能",
    "可",
    "可以",
    "进行",
    "通过",
    "我们",
    "他们",
    "它们",
}


def _tokenize(text: str) -> list[str]:
    """Tokenize for BM25, dropping Chinese function-word stopwords."""
    return [t for t in jieba.lcut(text) if t.strip() and t not in _BM25_STOPWORDS]


# Short-form → full financial term expansion for the sparse (BM25) query.
# Users ask "营收/净利/不良率/分红", the annual report says "营业收入/净利润/
# 不良贷款率/现金分红" — expanding before BM25 makes short queries hit.
_QUERY_EXPANSION: dict[str, list[str]] = {
    "营收": ["营业收入"],
    "净利": ["净利润"],
    "利润": ["净利润", "利润总额"],
    "分红": ["股利", "现金分红"],
    "股息": ["股利"],
    "不良": ["不良贷款率"],
    "不良率": ["不良贷款率"],
    "拨备": ["拨备覆盖率"],
    "资本充足": ["资本充足率"],
    "资本充足率": ["核心一级资本"],
    "roe": ["净资产收益率"],
    "收益": ["收益率"],
}

ASK_SYSTEM_PROMPT = (
    "你是一名严谨的投资研究助理。根据下面给出的文档片段回答用户的问题。要求：\n"
    "1. 只依据提供的片段回答，不要编造数据；片段中没有的信息明确说“资料中未提及”。\n"
    "2. 引用来源时用 [1]、[2] 等标注对应片段编号。\n"
    "3. 用中文回答，简洁、结构化。\n"
    "4. 数字要整理成易读的格式：关键数据用 **加粗**，多组数据用列表或 Markdown 表格呈现，"
    "并明确标注单位（如 百万元/亿元）与口径（集团 vs 母公司、是否归属于母公司股东）。\n"
    "5. 单位换算必须准确：百万元→亿元 除以 100（例如 257,936 百万元 = 2,579.36 亿元）。"
    "若对换算没有把握，直接保留原文单位（百万元），不要自行换算。\n"
    "6. 不要原样粘贴大段原始表格文本，只提炼对回答问题有用的数字。"
)


def _expand_tokens(tokens: list[str]) -> list[str]:
    """Append synonym terms so short-form query tokens match report terms.

    Expansion terms are tokenized with the same pipeline as the corpus, so the
    added tokens match what BM25 actually indexed (e.g. "不良贷款率" is indexed
    as ["不良贷款", "率"] — adding the raw term would never match).
    """
    extra: list[str] = []
    for tok in tokens:
        for term in _QUERY_EXPANSION.get(tok, []):
            extra.extend(_tokenize(term))
    return tokens + extra


@dataclass
class SearchResult:
    """Unified search result from hybrid retrieval."""

    content: str
    score: float
    document_id: str
    chunk_index: int
    title: str
    doc_type: str
    snippet: str = ""
    highlights: list[str] = field(default_factory=list)


def _make_snippet(content: str, query_tokens: list[str]) -> tuple[str, list[str]]:
    """Build a match-centered snippet + the matched terms for highlighting.

    Shows the window around the first matched term instead of the chunk head,
    so users see *why* the chunk was retrieved.
    """
    lowered = content.lower()
    found = [t for t in query_tokens if t and t.lower() in lowered]
    if found:
        first = min(lowered.find(t.lower()) for t in found)
        # If the match sits inside a Markdown table, start the snippet at the
        # table header so column meaning (集团/母公司, years) is visible.
        header_pos = -1
        pos = 0
        for line in content.splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith("|") and (
                "科目" in stripped or any(y in stripped for y in ("2025年", "2024年"))
            ):
                header_pos = pos
            if pos > first:
                break
            pos += len(line)
        if header_pos != -1 and first - header_pos < 800:
            start = header_pos
        else:
            start = max(0, first - 100)
        end = min(len(content), first + 220)
        snippet = ("…" if start > 0 else "") + content[start:end]
        if end < len(content):
            snippet += "…"
        return snippet, found[:5]
    truncated = content[:220]
    return truncated + ("…" if len(content) > 220 else ""), []


# Module-level BM25 cache (shared across requests, rebuilt on TTL expiry).
# This avoids loading all chunks from DB on every search request.
_bm25_cache: dict[str, BM25Okapi] = {}
_bm25_cache_time: dict[str, float] = {}
BM25_CACHE_TTL = 300  # seconds before rebuild


class KnowledgeService:
    """Hybrid RAG retrieval — dense (vector) + sparse (BM25)."""

    def __init__(
        self,
        session: AsyncSession,
        use_reranker: bool = False,
        embedder: EmbeddingModel | None = None,
        vector_store: VectorStore | None = None,
        reranker=None,
    ) -> None:
        self.session = session
        self.events = EventLogger(session)
        self.embedder = embedder or create_embedding()
        self.vector_store = vector_store or create_vector_store()
        self._reranker = reranker or (create_reranker() if use_reranker else None)

    async def search(
        self,
        query: str,
        top_k: int = 10,
        doc_type: str | None = None,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """Hybrid search: Qdrant (dense) + BM25 (sparse) → RRF fusion."""
        if not query.strip():
            return []

        # Build filter for doc_type
        vector_filter = {"doc_type": doc_type} if doc_type else None

        # 1. Dense search
        query_vector = await self.embedder.embed_query(query)
        dense_results = await self.vector_store.search(
            collection=settings.QDRANT_COLLECTION,
            vector=query_vector,
            top_k=top_k * 2,
            filter_=vector_filter,
        )

        # 2. Sparse search (BM25)
        sparse_results = await self._sparse_search(query, top_k * 2, doc_type)

        # 3. Reciprocal Rank Fusion
        fused = self._rrf_fusion(dense_results, sparse_results, top_k)

        # 4. Enrich with DB content
        enriched = await self._enrich_results(fused)

        # 5. Cross-encoder re-ranking (if available)
        if self._reranker and enriched:
            try:
                docs_for_rerank = [
                    (
                        r.content,
                        r.title,
                        {
                            "document_id": r.document_id,
                            "chunk_index": r.chunk_index,
                            "title": r.title,
                            "doc_type": r.doc_type,
                        },
                    )
                    for r in enriched[: top_k * 3]  # re-rank top 3x
                ]
                reranked = await self._reranker.rerank(query, docs_for_rerank, top_k=top_k)
                enriched = [
                    SearchResult(
                        content=content,
                        score=score,
                        document_id=meta["document_id"],
                        chunk_index=meta["chunk_index"],
                        title=meta["title"],
                        doc_type=meta["doc_type"],
                    )
                    for score, content, meta in reranked
                ]
            except Exception:
                logger.warning("Reranker failed, falling back to RRF")
                pass

        # Log query
        await self.events.record(
            source="knowledge",
            event_type="search.executed",
            payload={
                "query": query[:200],
                "top_k": top_k,
                "results_count": len(enriched),
            },
        )

        # Attach match-centered snippets + highlight terms for display.
        query_tokens = _expand_tokens(_tokenize(query))
        results = enriched[:top_k]
        for r in results:
            r.snippet, r.highlights = _make_snippet(r.content, query_tokens)
        return results

    async def search_by_document(
        self,
        query: str,
        document_id: str,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Search within a single document."""
        query_vector = await self.embedder.embed_query(query)
        vector_results = await self.vector_store.search(
            collection=settings.QDRANT_COLLECTION,
            vector=query_vector,
            top_k=top_k * 2,
            filter_={"document_id": document_id},
        )
        # Fall back to BM25
        fused = [{"id": r.id, "score": r.score or 0.0} for r in vector_results]
        results = await self._enrich_results(fused)
        # If not enough, do direct DB text search
        if len(results) < top_k:
            db_results = await self._db_text_search(query, document_id, top_k)
            existing_ids = {r.document_id for r in results}
            for r in db_results:
                if r.document_id not in existing_ids:
                    results.append(r)
        return results[:top_k]

    async def _sparse_search(
        self, query: str, top_k: int, doc_type: str | None = None
    ) -> list[dict]:
        """BM25 sparse search over all indexed chunks."""
        # Load BM25 index (lazy, cached per session)
        bm25 = await self._get_bm25(settings.QDRANT_COLLECTION)

        if not bm25 or not query:
            return []

        scores = bm25.get_scores(_expand_tokens(_tokenize(query)))
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append(
                    {
                        "id": bm25.ids[idx],
                        "score": float(scores[idx]) / 100.0,  # normalize
                        "payload": bm25.metadata[idx],
                    }
                )
        return results

    async def _get_bm25(self, collection: str):
        """Build BM25 index from database chunks (module-level cache with TTL)."""
        import time as _time

        now = _time.time()
        cache_age = (
            now - _bm25_cache_time.get(collection, 0)
            if collection in _bm25_cache_time
            else float("inf")
        )

        if collection in _bm25_cache and cache_age < BM25_CACHE_TTL:
            return _bm25_cache[collection]

        logger.info(
            "BM25 cache miss for '%s' (age=%.1fs) — rebuilding from DB",
            collection,
            cache_age,
        )

        # Load the full corpus via keyset pagination — no silent truncation.
        chunks: list[DocumentChunk] = []
        last_id = None
        while True:
            stmt = select(DocumentChunk).where(DocumentChunk.embedding_id.isnot(None))
            if last_id is not None:
                stmt = stmt.where(DocumentChunk.id > last_id)
            stmt = stmt.order_by(DocumentChunk.id).limit(5000)
            batch = list((await self.session.execute(stmt)).scalars().all())
            if not batch:
                break
            chunks.extend(batch)
            last_id = batch[-1].id
            max_chunks = settings.BM25_MAX_CHUNKS
            if max_chunks and len(chunks) >= max_chunks:
                logger.warning(
                    "BM25 corpus truncated at %d chunks (BM25_MAX_CHUNKS=%d)",
                    len(chunks),
                    max_chunks,
                )
                break
        if not chunks:
            return None

        tokenized_corpus = [_tokenize(c.content) for c in chunks]
        bm25 = BM25Okapi(tokenized_corpus)
        bm25.ids = [c.embedding_id for c in chunks]
        bm25.metadata = [
            {
                "document_id": str(c.document_id),
                "chunk_index": c.chunk_index,
            }
            for c in chunks
        ]

        _bm25_cache[collection] = bm25  # type: ignore[assignment]
        _bm25_cache_time[collection] = now
        return bm25

    def _rrf_fusion(
        self,
        dense: list,
        sparse: list,
        k: int = 60,
    ) -> list:
        """Reciprocal Rank Fusion — combine dense and sparse results."""
        scores: dict[str, float] = {}

        for rank, result in enumerate(dense):
            doc_id = result.id
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)

        for rank, result in enumerate(sparse):
            doc_id = result["id"]
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return [{"id": doc_id, "score": score} for doc_id, score in ranked]

    async def _enrich_results(self, fused: list[dict]) -> list[SearchResult]:
        """Enrich fused results with full chunk content from DB."""
        if not fused:
            return []

        # Batch query: one IN fetch instead of N individual queries
        embedding_ids = [item["id"] for item in fused]
        result = await self.session.execute(
            select(DocumentChunk, Document)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(DocumentChunk.embedding_id.in_(embedding_ids))
        )
        rows = result.all()

        # Build lookup: embedding_id → (chunk, doc)
        chunk_map: dict[str, tuple] = {}
        for chunk, doc in rows:
            chunk_map[chunk.embedding_id] = (chunk, doc)

        enriched = []
        for item in fused:
            pair = chunk_map.get(item["id"])
            if pair:
                chunk, doc = pair
                enriched.append(
                    SearchResult(
                        content=chunk.content,
                        score=item["score"],
                        document_id=str(doc.id),
                        chunk_index=chunk.chunk_index,
                        title=doc.title,
                        doc_type=doc.doc_type,
                    )
                )
        return enriched

    async def _db_text_search(self, query: str, document_id: str, top_k: int) -> list[SearchResult]:
        """Fallback: direct LIKE search on document chunks."""
        from sqlalchemy import text

        stmt = text("""
            SELECT dc.content, dc.chunk_index, d.title, d.doc_type
            FROM document.document_chunks dc
            JOIN document.documents d ON d.id = dc.document_id
            WHERE dc.document_id = :doc_id
              AND dc.content ILIKE :query
            ORDER BY dc.chunk_index
            LIMIT :limit
        """)
        result = await self.session.execute(
            stmt,
            {
                "doc_id": document_id,
                "query": f"%{query}%",
                "limit": top_k,
            },
        )
        rows = result.all()
        return [
            SearchResult(
                content=row[0],
                score=0.5,
                document_id=document_id,
                chunk_index=row[1],
                title=row[2],
                doc_type=row[3],
            )
            for row in rows
        ]

    async def _get_ask_system_prompt(self) -> str:
        """优先读取数据库 PromptTemplate(name='knowledge_ask')，回退内置常量。

        支持在 AI 中心迭代提示词而无需改代码；模板不存在或查询失败时
        静默回退，保证 ask 永远可用。
        """
        try:
            from ai.models import PromptTemplate

            result = await self.session.execute(
                select(PromptTemplate).where(
                    PromptTemplate.name == "knowledge_ask",
                    PromptTemplate.is_active.is_(True),
                )
            )
            tpl = result.scalar_one_or_none()
            if tpl and tpl.system_prompt:
                return tpl.system_prompt
        except Exception:
            pass
        return ASK_SYSTEM_PROMPT

    async def ask(
        self,
        question: str,
        top_k: int = 5,
        provider: str = "default",
        model: str | None = None,
    ) -> dict:
        """Document Q&A — retrieve top chunks, then answer with citations.

        ``provider`` is "default" (configured LLM, e.g. DeepSeek) or "ollama"
        (local models; ``model`` selects one, falling back to the configured
        Ollama model).
        """
        from core.adapters.llm import OllamaLLM, create_llm
        from core.interfaces import LLM, LLMMessage

        results = await self.search(question, top_k=top_k)
        if not results:
            return {"answer": "知识库中没有找到相关资料。", "sources": []}

        fragments = "\n\n".join(
            f"[{i}] (score {r.score:.2f}) {r.content[:600]}" for i, r in enumerate(results, 1)
        )
        llm: LLM
        if provider == "ollama":
            llm = OllamaLLM(
                base_url=settings.OLLAMA_BASE_URL,
                model=model or settings.OLLAMA_MODEL,
            )
        else:
            llm = create_llm()
        response = await llm.generate(
            messages=[
                LLMMessage(role="system", content=await self._get_ask_system_prompt()),
                LLMMessage(role="user", content=f"问题: {question}\n\n文档片段:\n{fragments}"),
            ],
            temperature=0.2,
            max_tokens=1024,
        )
        sources = [
            {
                "title": r.title,
                "chunk_index": r.chunk_index,
                "score": round(r.score, 4),
                "document_id": str(r.document_id),
                "content": r.content[:300],
            }
            for r in results
        ]
        return {
            "answer": response.content,
            "sources": sources,
            "model": response.model,
        }

    async def list_llm_models(self) -> dict:
        """Return the default LLM and locally available Ollama chat models."""
        default = {
            "provider": settings.LLM_PROVIDER,
            "model": (
                settings.OPENAI_MODEL
                if settings.LLM_PROVIDER == "openai"
                else settings.OLLAMA_MODEL
            ),
        }

        ollama_models: list[str] = []
        try:
            import httpx

            async with httpx.AsyncClient(
                base_url=settings.OLLAMA_BASE_URL,
                timeout=5,
            ) as client:
                resp = await client.get("/api/tags")
                if resp.status_code == 200:
                    for m in resp.json().get("models", []):
                        name = (m or {}).get("name", "")
                        # Skip embedding-only models (they can't chat).
                        if name and not any(
                            tag in name.lower() for tag in ("bge", "embed", "nomic")
                        ):
                            ollama_models.append(name)
        except Exception:
            pass

        return {"default": default, "ollama": ollama_models}
