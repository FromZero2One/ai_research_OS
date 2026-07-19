"""Document Center service — pipeline: parse → chunk → embed → index."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.embedding import create_embedding
from core.adapters.vector_store import create_vector_store
from core.config import settings
from core.event_service import EventLogger
from core.exceptions import DocumentParsingError, NotFoundError
from document.models import Document, DocumentChunk


class DocumentService:
    """Full document lifecycle: ingest → parse → chunk → embed → index."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)
        self.embedder = create_embedding()
        self.vector_store = create_vector_store()

    # ── CRUD ──────────────────────────────────────────────────────

    async def create(self, **kwargs) -> Document:
        doc = Document(**kwargs)
        self.session.add(doc)
        await self.session.flush()
        await self.session.refresh(doc)
        await self.events.record(
            source="document",
            event_type="document.created",
            entity_type="document",
            entity_id=str(doc.id),
            payload={"title": doc.title, "doc_type": doc.doc_type},
        )
        return doc

    async def get(self, document_id: uuid.UUID) -> Document:
        result = await self.session.execute(
            select(Document).where(Document.id == document_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise NotFoundError("Document", str(document_id))
        return doc

    async def search(
        self,
        query: str | None = None,
        doc_type: str | None = None,
        company_id: uuid.UUID | None = None,
        is_indexed: bool | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Document], int]:
        stmt = select(Document)

        if query:
            stmt = stmt.where(Document.title.ilike(f"%{query}%"))
        if doc_type:
            stmt = stmt.where(Document.doc_type == doc_type)
        if company_id:
            stmt = stmt.where(Document.company_id == company_id)
        if is_indexed is not None:
            stmt = stmt.where(Document.is_indexed == is_indexed)

        # Count
        count_result = await self.session.execute(
            stmt.with_only_columns(Document.id).order_by(None)
        )
        total = len(count_result.all())

        stmt = stmt.order_by(desc(Document.created_at)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def delete(self, document_id: uuid.UUID) -> None:
        doc = await self.get(document_id)
        # Remove vectors from Qdrant if indexed
        if doc.is_indexed:
            chunk_ids = [
                c.embedding_id
                for c in doc.chunks
                if c.embedding_id
            ]
            if chunk_ids:
                await self.vector_store.delete("documents", chunk_ids)

        await self.session.delete(doc)
        await self.events.record(
            source="document",
            event_type="document.deleted",
            entity_type="document",
            entity_id=str(document_id),
        )

    # ── Pipeline: Upload → Parse → Chunk → Embed → Index ─────────

    async def process_upload(
        self,
        file_bytes: bytes,
        filename: str,
        title: str | None = None,
        doc_type: str | None = None,
        company_id: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> Document:
        """Full pipeline: save file → parse → chunk → embed → index."""
        doc_type = doc_type or self._infer_doc_type(filename)
        title = title or Path(filename).stem

        # 1. Save file
        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / f"{uuid.uuid4().hex}_{filename}"
        file_path.write_bytes(file_bytes)

        # 2. Create document record
        doc = await self.create(
            title=title,
            doc_type=doc_type,
            source=filename,
            company_id=company_id,
            file_path=str(file_path),
            file_size_bytes=len(file_bytes),
            mime_type=self._guess_mime(filename),
            extra_metadata=metadata or {},
        )

        # 3. Parse
        raw_text = await self._parse(file_bytes, filename)
        doc.raw_text = raw_text
        await self.session.flush()

        # 4. Chunk
        chunks = self._chunk_text(raw_text)
        for i, chunk_text in enumerate(chunks):
            self.session.add(
                DocumentChunk(
                    document_id=doc.id,
                    chunk_index=i,
                    content=chunk_text,
                    token_count=len(chunk_text.split()),
                )
            )
        await self.session.flush()

        # 5. Embed & Index (batch)
        await self._embed_and_index(doc)

        doc.chunk_count = len(chunks)
        doc.is_indexed = True
        await self.session.flush()
        await self.session.refresh(doc)

        await self.events.record(
            source="document",
            event_type="document.indexed",
            entity_type="document",
            entity_id=str(doc.id),
            payload={
                "title": doc.title,
                "chunks": len(chunks),
                "file_size": len(file_bytes),
            },
        )
        return doc

    async def _parse(self, content: bytes, filename: str) -> str:
        """Parse file content to plain text based on extension."""
        ext = Path(filename).suffix.lower()

        try:
            if ext == ".pdf":
                return await self._parse_pdf(content)
            elif ext in (".md", ".markdown"):
                return content.decode("utf-8", errors="replace")
            elif ext == ".txt":
                return content.decode("utf-8", errors="replace")
            elif ext in (".html", ".htm"):
                return await self._parse_html(content)
            else:
                # Fallback: try plain text
                return content.decode("utf-8", errors="replace")
        except Exception as e:
            raise DocumentParsingError(
                f"Failed to parse {filename}: {e}"
            )

    async def _parse_pdf(self, content: bytes) -> str:
        """Parse PDF using PyMuPDF."""
        import asyncio

        def _sync_parse() -> str:
            import fitz

            doc = fitz.open(stream=content, filetype="pdf")
            texts = []
            for page in doc:
                texts.append(page.get_text())
            doc.close()
            return "\n\n".join(texts)

        return await asyncio.to_thread(_sync_parse)

    async def _parse_html(self, content: bytes) -> str:
        """Strip HTML tags to get plain text."""
        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self._texts = []
                self._skip = False

            def handle_data(self, data):
                if not self._skip:
                    self._texts.append(data.strip())

            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style"):
                    self._skip = True

            def handle_endtag(self, tag):
                if tag in ("script", "style"):
                    self._skip = False

            def get_text(self) -> str:
                return " ".join(t for t in self._texts if t)

        parser = TextExtractor()
        parser.feed(content.decode("utf-8", errors="replace"))
        return parser.get_text()

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks."""
        from document.chunker import chunk_text

        return chunk_text(
            text,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )

    async def _embed_and_index(self, doc: Document) -> None:
        """Generate embeddings for all chunks and index in Qdrant."""
        # Refresh chunks
        result = await self.session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == doc.id)
            .order_by(DocumentChunk.chunk_index)
        )
        chunks = list(result.scalars().all())
        if not chunks:
            return

        # Ensure collection exists
        dimension = self.embedder.dimension
        await self.vector_store.create_collection("documents", dimension)

        # Batch embed
        texts = [c.content for c in chunks]
        vectors = await self.embedder.embed(texts)

        # Upsert to Qdrant
        from core.interfaces import VectorRecord

        records = []
        for chunk, vector in zip(chunks, vectors):
            embedding_id = str(uuid.uuid5(
                doc.id, f"chunk_{chunk.chunk_index}"
            ))
            chunk.embedding_id = embedding_id
            records.append(
                VectorRecord(
                    id=embedding_id,
                    vector=vector,
                    payload={
                        "document_id": str(doc.id),
                        "chunk_index": chunk.chunk_index,
                        "title": doc.title,
                        "doc_type": doc.doc_type,
                        "content": chunk.content[:500],  # preview
                    },
                )
            )

        await self.vector_store.upsert("documents", records)

    # ── Helpers ───────────────────────────────────────────────────

    def _infer_doc_type(self, filename: str) -> str:
        fname = filename.lower()
        if ".pdf" in fname:
            return "pdf"
        if ".md" in fname:
            return "markdown"
        if ".txt" in fname:
            return "text"
        return "other"

    def _guess_mime(self, filename: str) -> str:
        ext = Path(filename).suffix.lower()
        mime_map = {
            ".pdf": "application/pdf",
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".html": "text/html",
            ".htm": "text/html",
        }
        return mime_map.get(ext, "application/octet-stream")
