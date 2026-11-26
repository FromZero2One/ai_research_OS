"""检查某只票的知识检索是否命中（company_id 关联 + 实际返回片段数）。

用法（backend 目录，后端无需运行，需 Ollama）：
    .venv\\Scripts\\python -X utf8 tools/check_kb_hit.py 002602 "行业渗透率 排名"
"""
import asyncio
import sys

from sqlalchemy import func, select

import company.models  # noqa: F401
import document.models  # noqa: F401
import market.models  # noqa: F401
import screener.models  # noqa: F401
from core.container import create_container
from core.database import managed_session
from document.models import Document, DocumentChunk

TICKER = sys.argv[1] if len(sys.argv) > 1 else "002602"
QUERY = sys.argv[2] if len(sys.argv) > 2 else "行业渗透率 市场排名 主营业务"


async def main() -> None:
    async with managed_session() as session:
        container = create_container(session)
        target = (
            await session.execute(
                select(company.models.Company).where(company.models.Company.ticker == TICKER)
            )
        ).scalar_one_or_none()
        if target is None:
            print("公司不存在:", TICKER)
            return
        print("公司匹配:", str(target.id), target.name, target.ticker)
        cid = target.id

        rows = (
            await session.execute(
                select(
                    Document.id,
                    Document.title,
                    Document.is_indexed,
                    Document.company_id,
                    func.count(DocumentChunk.id),
                )
                .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
                .where(Document.company_id == cid)
                .group_by(Document.id)
            )
        ).all()
        print("该公司文档:")
        for did, title, indexed, company_id, chunks in rows:
            print(
                f"  {str(did)[:8]} indexed={indexed} chunks={chunks} "
                f"company_id={company_id} {title}"
            )

        results = await container.knowledge_service.search(
            QUERY, top_k=3, company_id=str(cid)
        )
        print(f"\n检索命中: {len(results)} 条")
        for r in results:
            text = (getattr(r, "content", "") or "")[:160].replace("\n", " ")
            score = getattr(r, "score", None)
            doc_id = str(getattr(r, "document_id", ""))[:8]
            print(f"  score={score} doc={doc_id} {text}")


asyncio.run(main())
