"""PDF document parser — PyMuPDF adapter with page metadata and error handling.

Implements the DocumentParser Protocol from core.interfaces.
Supports: text extraction, page metadata, headings detection, encrypted PDF handling.
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz

from core.interfaces import DocumentParser, ParsedDocument


class PDFParserError(Exception):
    """Base exception for PDF parsing failures."""


class PDFEncryptedError(PDFParserError):
    """Raised when the PDF is password-protected."""


class PDFScannedError(PDFParserError):
    """Raised when the PDF appears to be a scanned document (no extractable text)."""


class PyMuPDFParser(DocumentParser):
    """PDF parser using PyMuPDF (fitz).

    Extracts:
    - Full text with page markers
    - Per-page metadata (page number, text length)
    - Document info (title, author, subject)
    - Heading candidates (based on font size / bold)
    """

    MIN_TEXT_LENGTH = 50
    """Minimum total text length to consider a PDF as non-scanned."""

    HEADING_FONT_THRESHOLD = 1.2
    """Font size ratio relative to average to classify as heading."""

    async def parse(self, content: bytes, filename: str) -> ParsedDocument:
        """Parse PDF content and return structured text with metadata.

        Args:
            content: Raw PDF file bytes.
            filename: Original filename (used for file-type checks).

        Returns:
            ParsedDocument with text, metadata, and page-level chunks.

        Raises:
            PDFEncryptedError: If the PDF requires a password.
            PDFScannedError: If no extractable text is found.
            PDFParserError: For other parsing failures.
        """
        if not content:
            return ParsedDocument(text="", metadata={"pages": 0, "error": "Empty file"})

        try:
            doc = await self._open_pdf(content)
        except fitz.FileDataError as e:
            raise PDFParserError(f"Invalid or corrupted PDF file: {e}") from e

        # Check encryption
        if doc.is_encrypted:
            doc.close()
            raise PDFEncryptedError("PDF is password-protected and cannot be parsed")

        # Extract document-level metadata
        meta = self._extract_metadata(doc)

        # Extract pages
        pages_text: list[str] = []
        page_metadata: list[dict] = []
        total_text_length = 0

        for page_num in range(len(doc)):
            page = doc[page_num]

            # Get text blocks with positioning
            blocks = page.get_text("dict", sort=True)["blocks"]
            page_text_parts: list[str] = []
            headings: list[str] = []

            page_text = page.get_text("text", sort=True)
            page_text_length = len(page_text.strip())
            total_text_length += page_text_length

            # Extract structured blocks for heading detection
            font_sizes = []
            for block in blocks:
                if block["type"] == 0:  # text block
                    for line in block["lines"]:
                        for span in line["spans"]:
                            font_sizes.append(span["size"])

            # Detect headings based on font size
            if font_sizes:
                avg_font = sum(font_sizes) / len(font_sizes)
                for block in blocks:
                    if block["type"] == 0:
                        block_text = ""
                        block_max_font = 0
                        for line in block["lines"]:
                            for span in line["spans"]:
                                block_text += span["text"]
                                block_max_font = max(block_max_font, span["size"])

                        if (block_max_font > avg_font * self.HEADING_FONT_THRESHOLD
                            and len(block_text.strip()) < 200):
                            headings.append(block_text.strip())

            page_metadata.append({
                "page": page_num + 1,
                "text_length": page_text_length,
                "headings": headings,
            })
            pages_text.append(page_text)

        doc.close()

        # Check if this is a scanned PDF
        if total_text_length < self.MIN_TEXT_LENGTH and len(doc) > 0:
            raise PDFScannedError(
                f"PDF appears to be scanned (only {total_text_length} chars extracted "
                f"from {len(doc)} pages). OCR not supported in V1."
            )

        # Build full text with page markers
        full_text_parts: list[str] = []
        for i, (pt, pm) in enumerate(zip(pages_text, page_metadata)):
            header = f"[Page {pm['page']}]"
            if pm["headings"]:
                header += f" — {' / '.join(pm['headings'])}"
            full_text_parts.append(f"{header}\n{pt.strip()}")

        full_text = "\n\n".join(full_text_parts)

        # Split pages as natural chunks
        chunk_boundaries = self._find_chunk_boundaries(full_text)

        return ParsedDocument(
            text=full_text,
            metadata={
                **meta,
                "pages": len(pages_text),
                "total_text_length": total_text_length,
                "page_metadata": page_metadata,
                "chunk_boundaries": chunk_boundaries,
                "parser": "pymupdf",
            },
            chunks=pages_text if len(pages_text) > 1 else None,
        )

    async def _open_pdf(self, content: bytes) -> fitz.Document:
        """Open a PDF document from bytes, running in a thread."""
        import asyncio
        return await asyncio.to_thread(fitz.open, stream=content, filetype="pdf")

    def _extract_metadata(self, doc: fitz.Document) -> dict:
        """Extract document-level metadata from PDF."""
        meta = doc.metadata or {}
        return {
            "title": meta.get("title", "") or "",
            "author": meta.get("author", "") or "",
            "subject": meta.get("subject", "") or "",
            "keywords": meta.get("keywords", "") or "",
            "producer": meta.get("producer", "") or "",
            "creator": meta.get("creator", "") or "",
            "format": "PDF",
            "page_count": len(doc),
        }

    def _find_chunk_boundaries(self, text: str) -> list[int]:
        """Find natural chunk boundaries based on page markers."""
        boundaries = []
        for match in re.finditer(r"\n\[Page (\d+)\]", text):
            boundaries.append(match.start())
        return boundaries

    def supported_extensions(self) -> set[str]:
        return {".pdf"}
