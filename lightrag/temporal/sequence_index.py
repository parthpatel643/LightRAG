"""Sequence-index bookkeeping derived from ``doc_status`` metadata.

The sequence index of a document lives in ``doc_status.metadata`` (carried over
every status transition). There is deliberately **no** separate counter or lock
row: the next index is ``max(existing) + 1``, computed while the caller holds
the workspace-scoped ``enqueue_serialize`` lock (see
``LightRAG.apipeline_enqueue_documents``), which is the one cross-process lock
that already serialises enqueue. Deriving the value from the data means a
refused or duplicate enqueue can never burn an index and no backend has to
store a row that lacks the doc-status schema.
"""

from __future__ import annotations

import re
from typing import Any

from ..base import DocStatusStorage
from ..utils import logger

_PAGE_SIZE = 200
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _coerce_index(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        index = int(value)
    except (TypeError, ValueError):
        return None
    return index if index > 0 else None


async def collect_sequence_dates(doc_status: DocStatusStorage) -> dict[int, str]:
    """Map every known ``sequence_index`` to its ``effective_date``.

    Duplicate-attempt rows are skipped: they describe a refused upload, not a
    version. When two rows share an index (a failed upload retried) a real date
    wins over ``"unknown"``.
    """
    dates: dict[int, str] = {}
    page = 1
    while True:
        docs, total = await doc_status.get_docs_paginated(
            page=page, page_size=_PAGE_SIZE, sort_field="created_at", sort_direction="asc"
        )
        for _doc_id, doc in docs:
            metadata = getattr(doc, "metadata", None) or {}
            if metadata.get("is_duplicate"):
                continue
            index = _coerce_index(metadata.get("sequence_index"))
            if index is None:
                continue
            date = str(metadata.get("effective_date") or "unknown")
            if index not in dates or dates[index] == "unknown":
                dates[index] = date
        if not docs or page * _PAGE_SIZE >= total:
            break
        page += 1
    return dates


async def allocate_sequence_indices(doc_status: DocStatusStorage, count: int) -> list[int]:
    """Return ``count`` consecutive unused indices.

    MUST be called under the workspace ``enqueue_serialize`` lock, after dedupe
    and before the new rows are written.
    """
    if count <= 0:
        raise ValueError(f"count must be > 0, got {count}")
    known = await collect_sequence_dates(doc_status)
    start = max(known, default=0) + 1
    return list(range(start, start + count))


def resolve_cutoff_sequence(
    sequence_dates: dict[int, str], reference_date: str | None
) -> int | None:
    """Highest sequence index in force on ``reference_date`` (``None`` = no cutoff).

    Documents are ordered by sequence. A document whose date is unknown
    inherits the date of the nearest preceding dated document, and a leading
    run of undated documents (the base) is always in force. Returns ``0`` when
    the reference date predates every dated document.
    """
    if not reference_date:
        return None
    if not _ISO_DATE_RE.match(reference_date):
        logger.warning(
            f"Ignoring reference_date {reference_date!r}: expected YYYY-MM-DD"
        )
        return None

    cutoff = 0
    carried: str | None = None
    for index in sorted(sequence_dates):
        date = sequence_dates[index]
        if _ISO_DATE_RE.match(date):
            carried = date
        if carried is None or carried <= reference_date:
            cutoff = index
        else:
            break
    return cutoff
