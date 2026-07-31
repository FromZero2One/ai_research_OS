"""Knowledge Center — Hybrid RAG: dense + sparse retrieval.

Facade:
    KnowledgeFacade — exposes the KnowledgeService so callers can use one
    entry point.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.service import KnowledgeService


class KnowledgeFacade:
    """Aggregation facade over the knowledge service."""

    def __init__(self, session: AsyncSession) -> None:
        self.search_service = KnowledgeService(session)
