"""Text chunker — semantic-aware splitting with overlap.

Pure Python, no framework dependency. Easy to swap with LangChain later
when document volume justifies it.
"""

from __future__ import annotations

import re


def chunk_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[str]:
    """Split text into chunks with overlap, respecting paragraph boundaries.

    Strategy:
    1. Prefer splitting at paragraph breaks (\n\n)
    2. Fall back to sentence boundaries (。.!?；\n)
    3. Last resort: word boundary
    """
    if not text.strip():
        return []

    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = _find_chunk_end(text, start, chunk_size)

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move start, accounting for overlap
        start = end - chunk_overlap
        if start < 0:
            start = 0

        # Safety: prevent infinite loop on tiny chunks
        if start >= len(text) or (len(chunks) > 1 and start >= chunks[-2].count("") - 1):
            break

    return chunks


def _find_chunk_end(text: str, start: int, chunk_size: int) -> int:
    """Find the best end position for a chunk starting at `start`."""
    if start + chunk_size >= len(text):
        return len(text)

    end = start + chunk_size
    window = text[start:end]

    # 1. Try paragraph break (working backwards from end)
    para_break = window.rfind("\n\n")
    if para_break > chunk_size // 2:  # only if meaningful length
        return start + para_break

    # 2. Try sentence boundary
    for sep in ("。", ".", "！", "?", "\n"):
        idx = window.rfind(sep)
        if idx > chunk_size // 2:
            return start + idx + len(sep)

    # 3. Word boundary
    space_idx = window.rfind(" ")
    if space_idx > chunk_size // 2:
        return start + space_idx

    # 4. Hard cut
    return start + chunk_size
