"""Remove Qdrant points that no longer belong to any document in PostgreSQL.

Orphan points accumulate when documents are deleted outside the document API
(e.g. a database wipe) or when older test runs shared the same Qdrant
collection. They pollute dense retrieval: unrelated chunks (other companies,
old test uploads) rank ahead of real content.

Usage:
    PYTHONPATH=. python scripts/cleanup_vectors.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from core.config import settings
from core.proxy_cleanup import clean_proxy_env

clean_proxy_env()

from qdrant_client import AsyncQdrantClient  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from document.models import Document  # noqa: E402


async def main() -> None:
    async with async_session_factory() as session:
        rows = (await session.execute(select(Document.id))).scalars().all()
    valid_ids = {str(doc_id) for doc_id in rows}
    print(f"valid documents in PostgreSQL: {len(valid_ids)}")

    client = AsyncQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    collection = settings.QDRANT_COLLECTION
    try:
        collections = await client.get_collections()
        if collection not in {c.name for c in collections.collections}:
            print(f"collection '{collection}' does not exist — nothing to clean")
            return

        orphan_ids: list[str] = []
        scanned = 0
        next_offset: object | None = None
        while True:
            batch = await client.scroll(
                collection_name=collection,
                limit=1000,
                with_payload=True,
                with_vectors=False,
                offset=next_offset,
            )
            points, next_offset = batch
            if not points:
                break
            for point in points:
                scanned += 1
                doc_id = (point.payload or {}).get("document_id")
                if not doc_id or str(doc_id) not in valid_ids:
                    orphan_ids.append(point.id)
            if next_offset is None:
                break

        print(f"scanned {scanned} points, {len(orphan_ids)} orphans")
        if orphan_ids:
            await client.delete(
                collection_name=collection,
                points_selector=orphan_ids,
            )
            print(f"deleted {len(orphan_ids)} orphan points")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
