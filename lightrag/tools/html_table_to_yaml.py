from __future__ import annotations

import argparse
import os
import re
from typing import List, Optional, Tuple

import yaml
from bs4 import BeautifulSoup

from lightrag.utils import logger

# Match HTML <table> blocks (non-greedy), including newlines
TABLE_REGEX = re.compile(r"<table\b[\s\S]*?</table>", re.IGNORECASE)


def _cell_text(cell) -> str:
    # Return inner text preserving visible content; avoid normalization.
    # Strip leading/trailing whitespace, collapse internal whitespace lightly.
    # Keep currency/decimals as-is by not casting.
    text = cell.get_text(separator=" ", strip=True)
    return text


def _extract_headers(table_tag) -> Tuple[List[str], Optional[int]]:
    # Prefer thead headers; support multi-row header with colspans
    thead = table_tag.find("thead")
    if thead:
        trs = thead.find_all("tr", recursive=False)
        if trs:
            # If multi-row header, flatten hierarchical headers
            if len(trs) >= 2:
                # Build segments from first header row
                segments = []  # list of (start_index, colspan, text)
                base_headers: List[str] = []
                start_idx = 0
                for cell in trs[0].find_all(["th", "td"], recursive=False):
                    text = _cell_text(cell)
                    colspan_attr = cell.get("colspan")
                    colspan = (
                        int(colspan_attr)
                        if colspan_attr and str(colspan_attr).isdigit()
                        else 1
                    )
                    segments.append((start_idx, colspan, text))
                    for _ in range(colspan):
                        base_headers.append(text)
                    start_idx += colspan

                # Prepare columns list: list of header parts per column
                columns: List[List[str]] = [[h] for h in base_headers]

                # Process second header row: distribute cells over segments with colspan>1
                subcells = trs[1].find_all(["th", "td"], recursive=False)
                sub_idx = 0
                for seg_start, seg_len, _ in segments:
                    if seg_len > 1:
                        for j in range(seg_len):
                            if sub_idx < len(subcells):
                                sub_text = _cell_text(subcells[sub_idx])
                                columns[seg_start + j].append(sub_text)
                                sub_idx += 1
                            else:
                                # No subheader provided; keep base only
                                pass

                # Compose final header names by joining parts with ': '
                headers = [
                    ": ".join([p for p in parts if p != ""]) if parts else ""
                    for parts in columns
                ]
                # Fallback names for empty headers (avoid YAML empty keys)
                headers = [
                    (
                        ("Row" if i == 0 else f"Column {i + 1}")
                        if (h.strip() == "")
                        else h
                    )
                    for i, h in enumerate(headers)
                ]
                return headers, None
            else:
                # Single-row header
                tr = trs[0]
                headers = []
                for th in tr.find_all(["th", "td"], recursive=False):
                    headers.append(_cell_text(th))
                # Fallback names for empty headers
                headers = [
                    (
                        ("Row" if i == 0 else f"Column {i + 1}")
                        if (h.strip() == "")
                        else h
                    )
                    for i, h in enumerate(headers)
                ]
                return headers, None

    # Fallback: first row in table
    first_tr = table_tag.find("tr")
    if first_tr:
        headers = []
        for cell in first_tr.find_all(["th", "td"], recursive=False):
            headers.append(_cell_text(cell))
        # Return header row index so we can skip it when reading tbody-less tables
        all_trs = table_tag.find_all("tr")
        try:
            header_index = all_trs.index(first_tr)
        except ValueError:
            header_index = 0
        return headers, header_index

    return [], None


def _row_cells(
    tr, expected_cols: int, carry_first_value: Optional[str] = None
) -> List[str]:
    # Include th with scope="row" (or any th) as first value if present;
    # otherwise, use carry_first_value when provided (for rowspan propagation).
    cells: List[str] = []
    row_ths = tr.find_all("th", recursive=False)
    first_value: Optional[str] = None
    if row_ths:
        row_scoped = None
        for th in row_ths:
            if th.get("scope", "").lower() == "row":
                row_scoped = th
                break
        if row_scoped is None:
            row_scoped = row_ths[0]
        first_value = _cell_text(row_scoped)
    elif carry_first_value is not None:
        first_value = carry_first_value

    if first_value is not None:
        cells.append(first_value)

    for td in tr.find_all("td", recursive=False):
        colspan = td.get("colspan")
        span = int(colspan) if colspan and str(colspan).isdigit() else 1
        value = _cell_text(td)
        for _ in range(span):
            cells.append(value)
    if expected_cols is not None:
        if len(cells) < expected_cols:
            cells += [""] * (expected_cols - len(cells))
        elif len(cells) > expected_cols:
            cells = cells[:expected_cols]
    return cells


def parse_html_table_to_rows(table_html: str) -> Tuple[List[str], List[List[str]]]:
    soup = BeautifulSoup(table_html, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError("No <table> found in provided HTML chunk")

    # Detect nested tables
    if table.find("table") is not None:
        logger.warning("Nested table detected; skipping conversion for this table.")
        raise ValueError("Nested table not supported")

    headers, header_index = _extract_headers(table)
    expected_cols = len(headers) if headers else None

    rows: List[List[str]] = []
    tbody = table.find("tbody")
    current_row_value: Optional[str] = None
    remaining_rowspan: int = 0
    if tbody:
        trs = tbody.find_all("tr")
        for tr in trs:
            # Check for a row header in this row
            row_th = None
            for th in tr.find_all("th", recursive=False):
                if th.get("scope", "").lower() == "row":
                    row_th = th
                    break
            if row_th is not None:
                current_row_value = _cell_text(row_th)
                rs_attr = row_th.get("rowspan")
                remaining_rowspan = (
                    (int(rs_attr) - 1) if rs_attr and str(rs_attr).isdigit() else 0
                )
                rows.append(_row_cells(tr, expected_cols, carry_first_value=None))
            else:
                carry = current_row_value if remaining_rowspan > 0 else None
                rows.append(_row_cells(tr, expected_cols, carry_first_value=carry))
                if remaining_rowspan > 0:
                    remaining_rowspan -= 1
    else:
        all_trs = table.find_all("tr")
        for i, tr in enumerate(all_trs):
            if header_index is not None and i == header_index:
                continue
            # Check for a row header
            row_th = None
            for th in tr.find_all("th", recursive=False):
                if th.get("scope", "").lower() == "row":
                    row_th = th
                    break
            if row_th is not None:
                current_row_value = _cell_text(row_th)
                rs_attr = row_th.get("rowspan")
                remaining_rowspan = (
                    (int(rs_attr) - 1) if rs_attr and str(rs_attr).isdigit() else 0
                )
                rows.append(_row_cells(tr, expected_cols, carry_first_value=None))
            else:
                carry = current_row_value if remaining_rowspan > 0 else None
                rows.append(_row_cells(tr, expected_cols, carry_first_value=carry))
                if remaining_rowspan > 0:
                    remaining_rowspan -= 1

    return headers, rows


def table_to_yaml_stream(headers: List[str], rows: List[List[str]]) -> str:
    # Build a fenced YAML block with '---' per row (YAML stream)
    parts = ["```yaml"]
    for r in rows:
        parts.append("---")
        mapping = {}
        for i, h in enumerate(headers):
            mapping[h] = r[i] if i < len(r) else ""
        parts.append(
            yaml.safe_dump(mapping, allow_unicode=True, sort_keys=False).rstrip()
        )
    parts.append("```")
    return "\n".join(parts)


def replace_tables_in_markdown(md_text: str) -> str:
    # Replace each HTML table occurrence with a fenced YAML stream
    new_text = md_text
    offset = 0
    for match in list(TABLE_REGEX.finditer(md_text)):
        start, end = match.span()
        chunk = md_text[start:end]
        try:
            headers, rows = parse_html_table_to_rows(chunk)
            if not headers or not rows:
                logger.info("Table has no headers/rows; skipping conversion.")
                continue
            yaml_block = table_to_yaml_stream(headers, rows)
        except ValueError:
            logger.warning("Skipping a table that could not be converted.")
            continue

        adj_start = start + offset
        adj_end = end + offset
        new_text = new_text[:adj_start] + yaml_block + new_text[adj_end:]
        offset += len(yaml_block) - (end - start)

    return new_text


def process_path(
    path: str, in_place: bool = True, backup_suffix: Optional[str] = ".bak"
) -> None:
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for name in files:
                if name.lower().endswith(".md"):
                    process_path(
                        os.path.join(root, name),
                        in_place=in_place,
                        backup_suffix=backup_suffix,
                    )
        return

    with open(path, "r", encoding="utf-8") as f:
        original = f.read()

    transformed = replace_tables_in_markdown(original)
    if transformed == original:
        logger.info(f"No HTML tables converted in {path}.")
        return

    if in_place:
        if backup_suffix:
            backup_path = f"{path}{backup_suffix}"
            try:
                with open(backup_path, "w", encoding="utf-8") as bf:
                    bf.write(original)
            except Exception as e:
                logger.warning(f"Failed to write backup {backup_path}: {e}")
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as tf:
            tf.write(transformed)
        os.replace(tmp_path, path)
        logger.info(f"Converted HTML tables to YAML in-place: {path}")
    else:
        print(transformed)


def main():
    parser = argparse.ArgumentParser(
        description="Convert HTML tables in Markdown files to YAML streams (--- per row), in-place."
    )
    parser.add_argument("paths", nargs="+", help="File(s) or directory(ies) to process")
    parser.add_argument(
        "--no-in-place",
        action="store_true",
        help="Do not write back; print transformed content to stdout",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Disable writing a .bak backup when in-place",
    )
    parser.add_argument(
        "--backup-suffix", default=".bak", help="Backup suffix (default .bak)"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel("DEBUG")

    backup_suffix = None if args.no_backup else (args.backup_suffix or ".bak")

    for p in args.paths:
        process_path(p, in_place=not args.no_in_place, backup_suffix=backup_suffix)


if __name__ == "__main__":
    main()
