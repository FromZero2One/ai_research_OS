"""Structured table extraction from financial-statement PDF pages.

The annual reports this project ingests (e.g. Chinese bank annual reports)
render financial tables without ruling lines, so pdfplumber's line-based
``extract_table`` fails. Instead we reconstruct tables from word coordinates:

  - rows   = words grouped by vertical position (top)
  - columns = words grouped by horizontal position (x-center), anchored on
    the year-header row (e.g. 2025年 / 2024年)
  - group headers (e.g. 中国银行集团 / 中国银行) are read from the row above
    the year header and mapped to the columns they span

The output is a Markdown table with explicit per-column scope labels, so the
downstream text/embedding/LLM pipeline never loses the "集团 vs 母公司" columns.
"""

from __future__ import annotations

from collections import defaultdict

_YEAR_TOKENS = ("2025年", "2024年", "2023年", "2022年", "2021年", "2020年", "2019年")


def _merge_negative_fragments(words: list[dict]) -> list[dict]:
    """Join "(560,202" + ")" into "(560,202)"."""
    merged: list[dict] = []
    i = 0
    while i < len(words):
        w = words[i]
        if w["text"].startswith("(") and not w["text"].endswith(")") and i + 1 < len(words):
            nxt = words[i + 1]
            if (
                nxt["text"] == ")"
                and abs(nxt["x0"] - w["x1"]) < 8
                and abs(nxt["top"] - w["top"]) < 3
            ):
                merged.append({**w, "text": w["text"] + ")", "x1": nxt["x1"]})
                i += 2
                continue
        merged.append(w)
        i += 1
    return merged


def _group_rows(words: list[dict], tolerance: float = 7.0) -> list[list[dict]]:
    rows: list[list[dict]] = []
    current: list[dict] = []
    current_top: float | None = None
    for w in sorted(words, key=lambda x: (x["top"], x["x0"])):
        if current_top is None or abs(w["top"] - current_top) <= tolerance:
            current.append(w)
            if current_top is None:
                current_top = w["top"]
        else:
            rows.append(current)
            current = [w]
            current_top = w["top"]
    if current:
        rows.append(current)
    return rows


def extract_tables_from_page(page) -> list[dict]:
    """Reconstruct tabular structure from a pdfplumber page.

    Returns a list of table dicts::
        {
          "headers": [{"label": "中国银行集团", "colspan": 2}, ...],
          "subheaders": ["附注", "2025年", "2024年", "2025年", "2024年"],
          "rows": [{"label": "一、营业收入", "values": ["658,310", ...]}, ...],
        }
    Empty list when the page has no recognizable financial table.
    """
    words = _merge_negative_fragments(page.extract_words())
    if len(words) < 20:
        return []

    rows = _group_rows(words)
    # Locate the header row: the row with the most year tokens (>= 2) among
    # the first 20 rows. Narrative lines can contain a single "2025年" — those
    # are ignored, and tables that start lower on the page are still found.
    header_idx: int | None = None
    best_count = 0
    for ri, r in enumerate(rows[:20]):
        count = sum(1 for w in r if w["text"] in _YEAR_TOKENS)
        if count > best_count:
            best_count = count
            header_idx = ri
    if header_idx is None or best_count < 2:
        return []

    header = rows[header_idx]
    year_words = [w for w in header if w["text"] in _YEAR_TOKENS]
    label_threshold = min(w["x0"] for w in year_words) - 20

    # Column anchors: every header word to the right of the label column —
    # year tokens AND other data columns (e.g. "变动", "变动比率").
    # Drop unit-annotation words (e.g. "单位：百万元人民币（百分比除外）")
    # that may land in the header row — they are notes, not columns.
    def _is_unit_note(text: str) -> bool:
        return "单位" in text or "百万元" in text or "除外" in text

    anchors = sorted(
        [w for w in header if w["x0"] >= label_threshold and not _is_unit_note(w["text"])],
        key=lambda w: w["x0"],
    )
    if len(anchors) < 2:
        return []
    col_centers = [(w["x0"] + w["x1"]) / 2 for w in anchors]

    def col_of(w: dict) -> int:
        cx = (w["x0"] + w["x1"]) / 2
        if cx < label_threshold:
            return 0
        return min(range(len(col_centers)), key=lambda c: abs(col_centers[c] - cx)) + 1

    # Group headers from the row above the year header.
    group_headers: list[dict] = []
    if header_idx > 0:
        for w in rows[header_idx - 1]:
            if w["x1"] < label_threshold:
                continue
            # Columns the group header physically spans (its x-range ± small pad).
            span = sum(1 for c in col_centers if w["x0"] - 15 <= c <= w["x1"] + 15)
            if span:
                group_headers.append({"label": w["text"], "colspan": span})
    if not group_headers:
        # Single entity (no group header) — all columns belong to one group.
        group_headers = [{"label": "", "colspan": len(col_centers)}]

    subheaders = [w["text"] for w in header]
    if len(subheaders) != len(col_centers) + 1:
        subheaders = ["科目"] + [w["text"] for w in anchors]

    table_rows: list[dict] = []
    for r in rows[header_idx + 1 :]:
        cells: dict[int, list[str]] = defaultdict(list)
        for w in r:
            cells[col_of(w)].append(w["text"])
        label = " ".join(cells.get(0, [])).strip()
        values = [" ".join(cells.get(i + 1, [])).strip() for i in range(len(col_centers))]
        if not label and not any(values):
            continue
        table_rows.append({"label": label, "values": values})

    if len(table_rows) < 5:
        return []
    return [
        {
            "headers": group_headers,
            "subheaders": subheaders,
            "rows": table_rows,
        }
    ]


def table_to_markdown(table: dict) -> str:
    """Serialize a reconstructed table into a readable Markdown table.

    Group scopes are folded into each column header ("集团 2025年"), so the
    text alone never loses the 集团/母公司 distinction.
    """
    headers = table.get("headers") or []
    subheaders = table.get("subheaders") or []
    ncols = len(subheaders) - 1
    if ncols <= 0:
        return ""

    # Map each group header's colspan to per-column scope labels.
    scopes: list[str] = []
    for g in headers:
        for _ in range(max(g.get("colspan", 1), 1)):
            scopes.append(g.get("label", ""))
    while len(scopes) < ncols:
        scopes.append("")
    scopes = scopes[:ncols]

    col_names = []
    for i in range(ncols):
        year = subheaders[i + 1] if i + 1 < len(subheaders) else ""
        scope = scopes[i]
        col_names.append(f"{scope} {year}".strip() if scope else year)

    lines = ["| 科目 | " + " | ".join(col_names) + " |"]
    lines.append("| --- | " + " | ".join(["---"] * ncols) + " |")
    for row in table.get("rows", []):
        cells = [row.get("label", "")] + list(row.get("values", []))
        cells = cells[: ncols + 1]
        while len(cells) < ncols + 1:
            cells.append("")
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return "\n".join(lines)
