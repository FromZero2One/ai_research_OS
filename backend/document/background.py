"""后台文档索引协程（task_manager 退役后直跑模式，逻辑原样平移自 tasks.py）。"""

from __future__ import annotations

import uuid

from core.logging import logger


async def index_document_bg(document_id: str) -> None:
    """Index a document (parse → chunk → embed → index) in the background."""
    document_uuid = uuid.UUID(document_id)
    from core.container import create_container
    from core.database import managed_session

    async with managed_session() as session:
        svc = create_container(session).document_service
        try:
            doc = await svc.index_document(document_uuid)
            await session.commit()
            logger.info("  [document] indexed %s (%s chunks)", document_uuid, doc.chunk_count)
        except Exception as e:
            try:
                await svc.set_indexing_error(document_uuid, str(e))
                await session.commit()
            except Exception:
                pass
            logger.error("  [document] index failed %s: %s", document_uuid, e, exc_info=True)
