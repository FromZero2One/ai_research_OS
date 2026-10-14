"""Document Center service — pipeline: parse → chunk → embed → index."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.adapters.embedding import create_embedding
from core.adapters.pdf_parser import (
    PDFEncryptedError,
    PDFParserError,
    PDFScannedError,
    PyMuPDFParser,
)
from core.adapters.vector_store import create_vector_store
from core.config import settings
from core.event_service import EventLogger
from core.exceptions import DocumentParsingError, NotFoundError
from core.interfaces import DocumentParser, EmbeddingModel, VectorStore
from core.logging import logger
from document.models import Document, DocumentChunk


async def embed_chunks_safely(
    embedder: EmbeddingModel,
    texts: list[str],
    batch_size: int = 32,
) -> list[list[float] | None]:
    """Embed texts in batches, isolating provider failures per text.

    Some inputs make bge-m3 produce NaN (Ollama returns HTTP 500), and the
    adapter converts any failed request into zero vectors — which would poison
    the whole batch. This helper retries failing texts individually with
    control characters stripped, and returns ``None`` for texts that still
    cannot be embedded (callers skip those chunks instead of indexing zeros).
    """
    out: list[list[float] | None] = [None] * len(texts)

    def _cleaned(t: str) -> str:
        return "".join(ch for ch in t if ch.isprintable() or ch in "\n\t")

    async def _embed_one(text: str) -> list[float] | None:
        try:
            vec = (await embedder.embed([text]))[0]
            if any(vec):
                return vec
        except Exception:
            pass
        cleaned = _cleaned(text)
        if cleaned != text:
            try:
                vec = (await embedder.embed([cleaned]))[0]
                if any(vec):
                    return vec
            except Exception:
                pass
        return None

    for start in range(0, len(texts), batch_size):
        batch = list(range(start, min(start + batch_size, len(texts))))
        try:
            vectors = await embedder.embed([texts[i] for i in batch])
        except Exception:
            vectors = [[0.0]] * len(batch)
        for i, vec in zip(batch, vectors):
            if any(vec):
                out[i] = vec
            else:
                out[i] = await _embed_one(texts[i])
    return out


class DocumentService:
    """Full document lifecycle: ingest → parse → chunk → embed → index."""

    def __init__(
        self,
        session: AsyncSession,
        embedder: EmbeddingModel | None = None,
        vector_store: VectorStore | None = None,
        pdf_parser: DocumentParser | None = None,
    ) -> None:
        self.session = session
        self.events = EventLogger(session)
        self.embedder = embedder or create_embedding()
        self.vector_store = vector_store or create_vector_store()
        self.pdf_parser = pdf_parser or PyMuPDFParser()

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
            select(Document)
            .options(selectinload(Document.chunks))
            .where(Document.id == document_id)
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
        count_stmt = stmt.with_only_columns(func.count(Document.id)).order_by(None)
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(desc(Document.created_at)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def delete(self, document_id: uuid.UUID) -> None:
        doc = await self.get(document_id)
        # Remove vectors from Qdrant if indexed
        if doc.is_indexed:
            chunk_ids = [c.embedding_id for c in doc.chunks if c.embedding_id]
            if chunk_ids:
                await self.vector_store.delete(settings.QDRANT_COLLECTION, chunk_ids)

        await self.session.delete(doc)
        await self.events.record(
            source="document",
            event_type="document.deleted",
            entity_type="document",
            entity_id=str(document_id),
        )

    # ── Pipeline: Upload → Parse → Chunk → Embed → Index ─────────

    # ── Upload (two-phase: create row, then index in background) ──────────

    async def create_from_upload(
        self,
        file_bytes: bytes,
        filename: str,
        title: str | None = None,
        doc_type: str | None = None,
        company_id: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> Document:
        """Save the file and create the document row — no parsing/indexing.

        Indexing runs separately (``index_document``) via the background task
        worker so large PDFs don't block the upload request.
        """
        doc_type = doc_type or self._infer_doc_type(filename)
        title = title or Path(filename).stem

        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / f"{uuid.uuid4().hex}_{filename}"
        file_path.write_bytes(file_bytes)

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
        self._set_progress(doc, "queued", "等待索引...")
        await self.session.flush()
        return doc

    async def index_document(self, document_id: uuid.UUID) -> Document:
        """Run parse → chunk → embed → index, tracking progress per step."""
        doc = await self.get(document_id)
        self._set_progress(doc, "parsing", "正在解析文档...")
        await self.session.flush()

        file_bytes = Path(doc.file_path).read_bytes() if doc.file_path else b""
        raw_text = await self._parse(file_bytes, doc.source or "")
        doc.raw_text = raw_text
        await self.session.flush()

        self._set_progress(doc, "chunking", "正在分块...")
        await self.session.flush()
        chunks = self._chunk_text(raw_text)
        from document.content_classifier import classify_chunk

        for i, chunk_text in enumerate(chunks):
            self.session.add(
                DocumentChunk(
                    document_id=doc.id,
                    chunk_index=i,
                    content=chunk_text,
                    content_type=classify_chunk(chunk_text),
                    token_count=len(chunk_text.split()),
                )
            )
        await self.session.flush()

        if chunks:
            self._set_progress(doc, "embedding", f"正在嵌入 {len(chunks)} 个切片...")
            await self.session.flush()
            await self._embed_and_index(doc)

        doc.chunk_count = len(chunks)
        doc.is_indexed = True
        self._set_progress(doc, "completed", "索引完成", chunks=len(chunks))
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
                "file_size": doc.file_size_bytes,
            },
        )
        return doc

    async def process_upload(
        self,
        file_bytes: bytes,
        filename: str,
        title: str | None = None,
        doc_type: str | None = None,
        company_id: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> Document:
        """Synchronous convenience: create + index in one call (tests/scripts)."""
        doc = await self.create_from_upload(
            file_bytes=file_bytes,
            filename=filename,
            title=title,
            doc_type=doc_type,
            company_id=company_id,
            metadata=metadata,
        )
        return await self.index_document(doc.id)

    # ── Indexing progress ────────────────────────────────────────────────

    def _set_progress(self, doc: Document, step: str, message: str, **extra) -> None:
        # Build a NEW dict: JSONB columns don't detect in-place mutation, so
        # reassigning the same object would silently drop the update.
        meta = dict(doc.extra_metadata or {})
        meta["indexing"] = {"step": step, "message": message, **extra}
        doc.extra_metadata = meta

    async def get_indexing_status(self, document_id: uuid.UUID) -> dict:
        doc = await self.get(document_id)
        prog = (doc.extra_metadata or {}).get("indexing") or {}
        return {
            "id": str(doc.id),
            "is_indexed": doc.is_indexed,
            "chunk_count": doc.chunk_count,
            "step": prog.get("step", "queued"),
            "message": prog.get("message", ""),
            "error": prog.get("error"),
        }

    async def set_indexing_error(self, document_id: uuid.UUID, error: str) -> None:
        doc = await self.get(document_id)
        meta = dict(doc.extra_metadata or {})
        meta["indexing"] = {
            "step": "error",
            "message": f"索引失败: {error[:200]}",
            "error": error[:500],
        }
        doc.extra_metadata = meta

    async def _parse(self, content: bytes, filename: str) -> str:
        """Parse file content to plain text based on extension."""
        ext = Path(filename).suffix.lower()

        try:
            if ext == ".pdf":
                return await self._parse_pdf_with_tables(content)
            elif ext in (".md", ".markdown"):
                return content.decode("utf-8", errors="replace")
            elif ext == ".txt":
                return content.decode("utf-8", errors="replace")
            elif ext in (".html", ".htm"):
                return await self._parse_html(content)
            else:
                # Fallback: try plain text
                return content.decode("utf-8", errors="replace")
        except PDFEncryptedError:
            raise DocumentParsingError(f"Cannot parse {filename}: PDF is password-protected")
        except PDFScannedError:
            raise DocumentParsingError(
                f"Cannot parse {filename}: PDF appears to be a scanned document "
                "(OCR not supported in V1)"
            )
        except PDFParserError as e:
            raise DocumentParsingError(f"Failed to parse PDF {filename}: {e}")
        except (UnicodeDecodeError, ValueError) as e:
            raise DocumentParsingError(f"Failed to parse {filename}: {e}")

    async def _parse_pdf_with_tables(self, content: bytes) -> str:
        """Parse a PDF page by page, reconstructing financial tables.

        Pages with a recognizable table (year header + numeric columns) are
        replaced by a Markdown table with explicit scope labels (集团/母公司),
        so chunking, embedding and LLM reading never lose the column groups.
        Falls back to the PyMuPDF parser if pdfplumber is unavailable or fails.
        """
        import io

        try:
            import pdfplumber

            from document.table_extractor import (
                extract_tables_from_page,
                table_to_markdown,
            )
        except ImportError:
            result = await self.pdf_parser.parse(content, "")
            return result.text

        try:
            pages_text: list[str] = []
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    tables = extract_tables_from_page(page)
                    if tables:
                        pages_text.append(table_to_markdown(tables[0]))
                    else:
                        pages_text.append(page.extract_text() or "")
            return "\n\n".join(pages_text)
        except Exception as e:
            logger.warning("  [document] pdfplumber parse failed (%s) — falling back", e)
            result = await self.pdf_parser.parse(content, "")
            return result.text

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

        # Batch embed first — this auto-discovers the real dimension
        # from the Ollama (or other provider) response, isolating texts the
        # provider cannot embed (e.g. NaN-producing pages) instead of indexing
        # zero vectors.
        texts = [c.content for c in chunks]
        vectors = await embed_chunks_safely(self.embedder, texts)

        indexed = [(chunk, vec) for chunk, vec in zip(chunks, vectors) if vec is not None]
        skipped = len(chunks) - len(indexed)
        if not indexed:
            raise DocumentParsingError(
                f"Embedding failed for '{doc.title}' — provider returned no usable vectors"
            )
        if skipped:
            logger.warning(
                "  [document] %s: %d/%d chunks un-embeddable, skipped",
                doc.title,
                skipped,
                len(chunks),
            )

        # Now create the collection with the (now-correct) dimension.
        # If the collection already exists, this is a no-op.
        dimension = self.embedder.dimension
        await self.vector_store.create_collection(settings.QDRANT_COLLECTION, dimension)

        # Upsert to Qdrant
        from core.interfaces import VectorRecord

        records = []
        for chunk, vector in indexed:
            embedding_id = str(uuid.uuid5(doc.id, f"chunk_{chunk.chunk_index}"))
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
                        "content_type": chunk.content_type,
                        "content": chunk.content[:500],  # preview
                    },
                )
            )

        if records:
            await self.vector_store.upsert(settings.QDRANT_COLLECTION, records)

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
