"""Qdrant vector store adapter."""

from __future__ import annotations

from functools import lru_cache

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter as QdrantFilter,
    FieldCondition,
    MatchValue,
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
        self._client = AsyncQdrantClient(
            host=host, port=port, prefer_grpc=prefer_grpc
        )

    async def upsert(
        self, collection: str, records: list[VectorRecord]
    ) -> None:
        points = [
            PointStruct(id=r.id, vector=r.vector, payload=r.payload)
            for r in records
        ]
        await self._client.upsert(
            collection_name=collection, points=points
        )

    async def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 10,
        score_threshold: float | None = None,
        filter_: dict | None = None,
    ) -> list[VectorRecord]:
        qdrant_filter = None
        if filter_:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filter_.items()
            ]
            qdrant_filter = QdrantFilter(must=conditions)

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
            points_selector=ids,
        )

    async def create_collection(
        self, collection: str, dimension: int
    ) -> None:
        collections = await self._client.get_collections()
        existing = {c.name for c in collections.collections}
        if collection not in existing:
            await self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(
                    size=dimension, distance=Distance.COSINE
                ),
            )


@lru_cache(maxsize=1)
def create_vector_store() -> VectorStore:
    return QdrantVectorStore()
