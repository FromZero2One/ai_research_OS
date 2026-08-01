"""Qdrant vector store adapter."""

from __future__ import annotations

from typing import Any, cast

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    MatchValue,
    PointStruct,
    VectorParams,
)
from qdrant_client.models import (
    Filter as QdrantFilter,
)

from core.config import settings
from core.interfaces import VectorRecord, VectorStore


class QdrantVectorStore:
    """Qdrant-backed vector store."""

    def __init__(
        self,
        host: str = settings.QDRANT_HOST,
        port: int = settings.QDRANT_PORT,
        prefer_grpc: bool = settings.QDRANT_PREFER_GRPC,
    ) -> None:
        self._client = AsyncQdrantClient(host=host, port=port, prefer_grpc=prefer_grpc)

    async def upsert(self, collection: str, records: list[VectorRecord]) -> None:
        points = [PointStruct(id=r.id, vector=r.vector, payload=r.payload) for r in records]
        await self._client.upsert(collection_name=collection, points=points)

    async def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 10,
        score_threshold: float | None = None,
        filter_: dict | None = None,
    ) -> list[VectorRecord]:
        # Searching a collection that was never created (e.g. fresh Qdrant or
        # an empty test environment) raises a gRPC NotFound — treat it as "no
        # results" instead of a 500.
        collections = await self._client.get_collections()
        if collection not in {c.name for c in collections.collections}:
            return []

        qdrant_filter = None
        if filter_:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filter_.items()
            ]
            qdrant_filter = QdrantFilter(must=cast(list[Any], conditions))

        result = await self._client.query_points(
            collection_name=collection,
            query=vector,
            limit=top_k,
            score_threshold=score_threshold,
            query_filter=qdrant_filter,
        )
        return [
            VectorRecord(
                id=str(p.id),
                vector=[],
                payload=p.payload or {},
                score=p.score,
            )
            for p in result.points
        ]

    async def delete(self, collection: str, ids: list[str]) -> None:
        await self._client.delete(
            collection_name=collection,
            points_selector=cast(Any, ids),
        )

    async def create_collection(self, collection: str, dimension: int) -> None:
        collections = await self._client.get_collections()
        existing = {c.name for c in collections.collections}
        if collection not in existing:
            await self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
            )


def create_vector_store() -> VectorStore:
    """Create a new Qdrant vector store instance."""
    return QdrantVectorStore()
