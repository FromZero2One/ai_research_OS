"""给已索引切片回填 Qdrant payload.company_id（一次性修复：跨公司证据污染）。"""

import psycopg2

from _db import connect
from qdrant_client import QdrantClient

from core.config import settings


conn = connect()
cur = conn.cursor()
cur.execute(
    "SELECT id, company_id, title FROM document.documents "
    "WHERE company_id IS NOT NULL AND is_indexed"
)
docs = cur.fetchall()

client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
total = 0
for doc_id, company_id, title in docs:
    cur.execute(
        "SELECT embedding_id FROM document.document_chunks "
        "WHERE document_id=%s AND embedding_id IS NOT NULL",
        (doc_id,),
    )
    ids = [r[0] for r in cur.fetchall()]
    if not ids:
        continue
    client.set_payload(
        collection_name=settings.QDRANT_COLLECTION,
        payload={"company_id": str(company_id)},
        points=ids,
    )
    total += len(ids)
    print(f"{title}: {len(ids)} points", flush=True)

print(f"done: {len(docs)} docs, {total} points")
conn.close()
