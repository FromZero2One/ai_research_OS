"""Re-embed all existing chunks with real Ollama embeddings (fix zero-vector issue).

Embeds in batches, validates that real (non-zero) vectors came back, writes
new points under content-derived IDs, then removes the old zero-vector points.

Usage:
    PYTHONPATH=. python scripts/reembed.py
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from core.proxy_cleanup import clean_proxy_env

clean_proxy_env()

from core.adapters.embedding import create_embedding  # noqa: E402
from core.adapters.vector_store import create_vector_store  # noqa: E402
from core.config import settings  # noqa: E402
from core.database import async_session_factory  # noqa: E402
from core.interfaces import VectorRecord  # noqa: E402
from core.logging import configure_logging, logger  # noqa: E402
from document.models import Document, DocumentChunk  # noqa: E402
from document.service import embed_chunks_safely  # noqa: E402

EMBED_BATCH_SIZE = 32


async def reembed() -> dict:
    configure_logging()
    embedder = create_embedding()
    vector_store = create_vector_store()

    async with async_session_factory() as session:
        docs = {str(d.id): d for d in (await session.execute(select(Document))).scalars().all()}
        result = await session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.embedding_id.isnot(None))
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        )
        chunks = list(result.scalars().all())
        logger.info("Found %d chunks to re-embed", len(chunks))

        old_ids: list[str] = []
        updated = 0
        skipped = 0
        for start in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[start : start + EMBED_BATCH_SIZE]
            vectors = await embed_chunks_safely(embedder, [c.content or "" for c in batch])

            records = []
            for chunk, vector in zip(batch, vectors):
                if vector is None:
                    logger.warning(
                        "  Un-embeddable chunk %s (doc %s) — skipping",
                        chunk.id,
                        chunk.document_id,
                    )
                    skipped += 1
                    old_ids.append(str(chunk.embedding_id))
                    chunk.embedding_id = None
                    continue

                old_ids.append(str(chunk.embedding_id))
                new_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.content or ""))
                doc = docs.get(str(chunk.document_id))
                records.append(
                    VectorRecord(
                        id=new_id,
                        vector=vector,
                        payload={
                            "document_id": str(chunk.document_id),
                            "chunk_index": chunk.chunk_index,
                            "title": doc.title if doc else "",
                            "doc_type": doc.doc_type if doc else "",
                            "content": (chunk.content or "")[:500],
                        },
                    )
                )
                chunk.embedding_id = new_id
                updated += 1

            if records:
                await vector_store.upsert(settings.QDRANT_COLLECTION, records)
            logger.info("  Re-embedded batch %d-%d", start + 1, start + len(batch))

        # Remove the old (zero-vector) points now that replacements are in place.
        if old_ids:
            await vector_store.delete(settings.QDRANT_COLLECTION, old_ids)
            logger.info("Deleted %d old zero-vector points", len(old_ids))

        await session.commit()
        logger.info("Re-embedding complete: %d chunks, %d skipped", updated, skipped)
        return {"chunks": updated, "skipped": skipped, "deleted_old_points": len(old_ids)}


async def main() -> None:
    print(await reembed())


if __name__ == "__main__":
    asyncio.run(main())
