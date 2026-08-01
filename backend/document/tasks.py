"""Background document indexing task handler."""

from __future__ import annotations

import uuid

from core.logging import logger
from core.task_manager import register_handler


async def _run_document_index(payload: dict) -> dict | None:
    """Index a document (parse → chunk → embed → index) in the worker."""
    document_id = uuid.UUID(payload["document_id"])
    from core.container import create_container
    from core.database import managed_session

    async with managed_session() as session:
        svc = create_container(session).document_service
        try:
            doc = await svc.index_document(document_id)
            await session.commit()
            logger.info("  [document] indexed %s (%s chunks)", document_id, doc.chunk_count)
            return {"document_id": str(document_id), "chunks": doc.chunk_count}
        except Exception as e:
            try:
                await svc.set_indexing_error(document_id, str(e))
                await session.commit()
            except Exception:
                pass
            logger.error("  [document] index failed %s: %s", document_id, e, exc_info=True)
            raise  # re-raise so TaskRecord tracks the failure


register_handler("document_index", _run_document_index)
