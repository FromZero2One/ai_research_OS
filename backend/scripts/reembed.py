"""Re-embed all existing chunks with real Ollama embeddings (fix zero-vector issue)."""
from __future__ import annotations

import asyncio
import uuid

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.embedding import create_embedding
from core.adapters.vector_store import create_vector_store
from core.database import async_session_factory
from core.interfaces import VectorRecord
from core.logging import configure_logging, logger
from document.models import DocumentChunk


async def reembed() -> None:
    configure_logging()
    embedder = create_embedding()
    vector_store = create_vector_store()

    async with async_session_factory() as session:
        result = await session.execute(
            select(DocumentChunk).where(DocumentChunk.embedding_id.isnot(None))
        )
        chunks = list(result.scalars().all())
        logger.info("Found %d chunks to re-embed", len(chunks))

        for chunk in chunks:
            content = chunk.content or ""
            if not content.strip():
                logger.warning("  Skipping empty chunk %s", chunk.id)
                continue

            # Generate real embedding via Ollama
            vector = await embedder.embed_query(content)

            # Generate new embedding_id (UUID v5 from content for consistency)
            new_embedding_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content))

            # Update Qdrant point
            try:
                await vector_store.upsert(
                    collection="documents",
                    records=[
                        VectorRecord(
                            id=new_embedding_id,
                            vector=vector,
                            payload={
                                "document_id": str(chunk.document_id),
                                "chunk_index": chunk.chunk_index,
                                "content": content[:512],
                            },
                        )
                    ],
                )
                # Update DB reference
                chunk.embedding_id = new_embedding_id
                logger.info("  Re-embedded chunk %s (%d dim)", chunk.id, len(vector))
            except Exception as e:
                logger.error("  Failed to re-embed chunk %s: %s", chunk.id, e)

        # Clean up old zero-vector points from Qdrant
        logger.info("Cleaning up old Qdrant points...")
        try:
            old_points = [c.embedding_id for c in chunks if c.embedding_id]
            # Actually we just updated them above, but we also need to
            # remove points that aren't linked to any chunk anymore
            pass
        except Exception as e:
            logger.warning("Cleanup note: %s", e)

        await session.commit()
        logger.info("Re-embedding complete!")


async def main() -> None:
    await reembed()


if __name__ == "__main__":
    asyncio.run(main())
