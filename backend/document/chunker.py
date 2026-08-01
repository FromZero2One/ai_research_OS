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

    if chunk_size < 1:
        return [text]

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    table_spans = _table_spans(text)

    while start < len(text):
        end = _find_chunk_end(text, start, chunk_size)

        # Keep a Markdown table whole: if the current window touches a table,
        # extend through the table end (header stays with its rows).
        table_end = None
        for t_start, t_end in table_spans:
            if t_start <= start < t_end:
                table_end = t_end
                break
        if table_end is not None and table_end > end:
            end = table_end

        if end <= start:
            break  # Safety: no forward progress (should not happen with valid size)

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Reached the tail — the final chunk already covers the rest.
        if end >= len(text):
            break

        if table_end is not None and end == table_end:
            # Table finished — continue after it without overlap re-processing.
            start = end
        else:
            # Move start, accounting for overlap.
            next_start = end - chunk_overlap
            # Guarantee forward progress even with degenerate overlap settings.
            start = next_start if next_start > start else start + 1

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


def _table_spans(text: str, max_table_size: int = 8000) -> list[tuple[int, int]]:
    """Ranges of contiguous Markdown table blocks (lines starting with '|').

    Financial tables are reconstructed as Markdown; splitting one across two
    chunks would separate the header row from its data rows and make the
    result unreadable. Keep each table in a single chunk (capped).
    """
    spans: list[tuple[int, int]] = []
    start: int | None = None
    pos = 0
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("|"):
            if start is None:
                start = pos
        else:
            if start is not None:
                spans.append((start, pos))
                start = None
        pos += len(line)
    if start is not None:
        spans.append((start, len(text)))
    return [(s, min(e, s + max_table_size)) for s, e in spans]
