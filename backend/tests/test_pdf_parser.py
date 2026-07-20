"""Tests for PDF parser adapter — PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.adapters.pdf_parser import (
    PDFEncryptedError,
    PDFParserError,
    PDFScannedError,
    PyMuPDFParser,
)

TEST_DATA = Path(__file__).resolve().parent / "test_data"


@pytest.fixture
def parser() -> PyMuPDFParser:
    return PyMuPDFParser()


class TestPDFParser:
    """Core PDF parsing functionality."""

    async def test_parse_basic_pdf(self, parser: PyMuPDFParser):
        content = (TEST_DATA / "sample_report.pdf").read_bytes()
        result = await parser.parse(content, "sample_report.pdf")

        assert "NVIDIA" in result.text
        assert "revenue" in result.text.lower()
        assert result.metadata["pages"] == 3
        assert result.metadata["format"] == "PDF"
        assert result.chunks is not None
        assert len(result.chunks) == 3
        assert "[Page 1]" in result.text
        assert "[Page 2]" in result.text
        assert "[Page 3]" in result.text

    async def test_parse_single_page(self, parser: PyMuPDFParser):
        content = (TEST_DATA / "single_page.pdf").read_bytes()
        result = await parser.parse(content, "single_page.pdf")

        assert "Single page document" in result.text
        assert result.metadata["pages"] == 1
        assert "[Page 1]" in result.text
        # Single page: chunks should be None (not worth splitting)
        assert result.chunks is None

    async def test_supported_extensions(self, parser: PyMuPDFParser):
        assert parser.supported_extensions() == {".pdf"}

    async def test_empty_content(self, parser: PyMuPDFParser):
        result = await parser.parse(b"", "empty.pdf")
        assert result.text == ""
        assert "error" in result.metadata

    async def test_metadata_extraction(self, parser: PyMuPDFParser):
        content = (TEST_DATA / "sample_report.pdf").read_bytes()
        result = await parser.parse(content, "sample_report.pdf")

        assert result.metadata["page_count"] == 3
        assert "page_metadata" in result.metadata
        pages = result.metadata["page_metadata"]
        assert len(pages) == 3
        assert pages[0]["page"] == 1
        assert pages[1]["page"] == 2


class TestPDFParserErrors:
    """Error handling for edge cases."""

    async def test_encrypted_pdf(self, parser: PyMuPDFParser):
        content = (TEST_DATA / "encrypted.pdf").read_bytes()
        with pytest.raises(PDFEncryptedError, match="password-protected"):
            await parser.parse(content, "encrypted.pdf")

    async def test_empty_page_raises_scanned_error(self, parser: PyMuPDFParser):
        """A page with no text should raise PDFScannedError."""
        content = (TEST_DATA / "empty_page.pdf").read_bytes()
        with pytest.raises(PDFScannedError, match="scanned"):
            await parser.parse(content, "empty_page.pdf")

    async def test_invalid_content(self, parser: PyMuPDFParser):
        with pytest.raises(PDFParserError, match="Invalid|corrupted"):
            await parser.parse(b"not a pdf content", "invalid.pdf")


class TestPDFParserIntegration:
    """Integration: parser output feeds into document pipeline."""

    async def test_page_metadata_structure(self, parser: PyMuPDFParser):
        content = (TEST_DATA / "sample_report.pdf").read_bytes()
        result = await parser.parse(content, "sample_report.pdf")

        for pm in result.metadata["page_metadata"]:
            assert "page" in pm
            assert "text_length" in pm
            assert "headings" in pm

    async def test_text_length_per_page(self, parser: PyMuPDFParser):
        content = (TEST_DATA / "sample_report.pdf").read_bytes()
        result = await parser.parse(content, "sample_report.pdf")

        # Total text length should be sum of page lengths
        total = sum(pm["text_length"] for pm in result.metadata["page_metadata"])
        assert total > 0
        assert len(result.text) >= total

    async def test_chunk_boundaries(self, parser: PyMuPDFParser):
        content = (TEST_DATA / "sample_report.pdf").read_bytes()
        result = await parser.parse(content, "sample_report.pdf")

        assert "chunk_boundaries" in result.metadata
        boundaries = result.metadata["chunk_boundaries"]
        assert len(boundaries) >= 2  # At least 2 boundaries for 3 pages
