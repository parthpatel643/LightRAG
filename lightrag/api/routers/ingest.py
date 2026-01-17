"""
Hybrid ingestion API: accepts mixed files and URLs with lineage manifest,
produces validated documents for temporal-legal ingestion.
"""

import json
from datetime import datetime
from typing import List, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator

from lightrag import LightRAG
from lightrag.api.utils_api import get_combined_auth_dependency
from lightrag.lightrag import DocumentInput, DocumentMetadata
from lightrag.utils import generate_track_id, sanitize_text_for_encoding

router = APIRouter(prefix="/ingest", tags=["ingest"])


class ManifestItem(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    type: Literal["file", "url"]
    url: Optional[str] = None
    # Optional hints; ingestion will infer when missing
    effectiveDate: Optional[datetime] = None
    docType: Optional[str] = None
    # Optional explicit sequence within a batch (1-based). When provided,
    # backend will respect this order to assign order_index.
    sequence: Optional[int] = Field(default=None, ge=1)
    skipSSLVerify: Optional[bool] = Field(
        default=False, description="Skip SSL verification for internal URLs"
    )

    @field_validator("docType", mode="after")
    @classmethod
    def _strip_doc_type(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if isinstance(v, str) else v


class IngestManifest(BaseModel):
    items: List[ManifestItem]

    @field_validator("items", mode="after")
    @classmethod
    def _validate_items(cls, items: List[ManifestItem]) -> List[ManifestItem]:
        if not items:
            raise ValueError("Manifest must include at least one item")
        return items


class IngestResponse(BaseModel):
    status: Literal["success", "partial_success", "failure"]
    message: str
    track_id: str


async def _fetch_url_content(url: str, verify: bool) -> bytes:
    timeout = httpx.Timeout(20.0)
    async with httpx.AsyncClient(timeout=timeout, verify=verify) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def _extract_text_from_pdf_bytes(file_bytes: bytes) -> str:
    from io import BytesIO

    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(BytesIO(file_bytes))
    content = ""
    for page in reader.pages:
        content += (page.extract_text() or "") + "\n"
    return content


def _infer_doc_type(first_page_text: str) -> str:
    t = first_page_text.lower()
    if "amendment" in t:
        return "amendment"
    if "addendum" in t:
        return "addendum"
    if "rate sheet" in t or "rate schedule" in t or "pricing sheet" in t:
        return "rate-sheet"
    if "service agreement" in t:
        return "service-agreement"
    return "unknown"


def _parse_date_str(s: str) -> Optional[datetime]:
    from datetime import datetime

    s = s.strip()
    fmts = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%b %Y",
        "%B %Y",
    ]
    for f in fmts:
        try:
            dt = datetime.strptime(s, f)
            # Normalize month-only to first day
            if f in ("%b %Y", "%B %Y"):
                dt = dt.replace(day=1)
            return dt
        except Exception:
            continue
    return None


def _extract_effective_periods(
    first_page_text: str,
) -> list[dict[str, Optional[datetime]]]:
    import re

    txt = first_page_text
    periods: list[dict[str, Optional[datetime]]] = []

    # Range forms: "effective from <date> to <date>"
    range_pat = re.compile(
        r"(?i)effective\s+(?:date\s*)?(?:from)\s+([^\n,;]+?)\s+(?:to|through)\s+([^\n,;]+)"
    )
    for m in range_pat.finditer(txt):
        d1 = _parse_date_str(m.group(1))
        d2 = _parse_date_str(m.group(2))
        if d1 or d2:
            periods.append({"start": d1, "end": d2})

    # Single effective date: "effective (on|as of) <date>" or "effective date: <date>"
    single_pat = re.compile(
        r"(?i)effective(?:\s+date)?(?:\s*[:\-]|\s+(?:on|as\s+of))\s+([^\n,;]+)"
    )
    for m in single_pat.finditer(txt):
        d = _parse_date_str(m.group(1))
        if d:
            periods.append({"start": d, "end": None})

    return periods


async def _extract_text_from_upload(file: UploadFile) -> str:
    filename = file.filename or "uploaded"
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    data = await file.read()

    # Basic handling: PDF vs UTF-8 text
    if ext == "pdf":
        return await _extract_text_from_pdf_bytes(data)
    else:
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise HTTPException(
                status_code=400, detail=f"Unsupported encoding for {filename}: {e}"
            )


def create_ingest_routes(rag: LightRAG, api_key: Optional[str] = None):
    combined_auth = get_combined_auth_dependency(api_key)

    @router.post(
        "/batch", response_model=IngestResponse, dependencies=[Depends(combined_auth)]
    )
    async def ingest_batch(
        files: List[UploadFile] = File(default=[]), manifest: str = Form(...)
    ):
        try:
            parsed = json.loads(manifest)
            manifest_model = IngestManifest(**parsed)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid manifest: {e}")

        # Map uploads by filename for quick lookup
        upload_map = {f.filename: f for f in (files or []) if f and f.filename}

        # Collect documents and their ordering hints
        doc_records: List[tuple[DocumentInput, Optional[int], Optional[datetime]]] = []
        errors: List[str] = []

        # Build documents from manifest
        for item in manifest_model.items:
            text: Optional[str] = None
            file_path_hint = None

            if item.type == "file":
                up = upload_map.get(item.name)
                if not up:
                    errors.append(
                        f"Missing uploaded file for manifest item: {item.name}"
                    )
                    continue
                text = await _extract_text_from_upload(up)
                file_path_hint = item.name
            else:
                if not item.url:
                    errors.append(f"URL missing for manifest item: {item.name}")
                    continue
                verify = not bool(item.skipSSLVerify)
                try:
                    content_bytes = await _fetch_url_content(item.url, verify=verify)
                    # Heuristic: try PDF first, else UTF-8
                    if item.url.lower().endswith(".pdf"):
                        text = await _extract_text_from_pdf_bytes(content_bytes)
                    else:
                        try:
                            text = content_bytes.decode("utf-8")
                        except UnicodeDecodeError:
                            # Fallback: still attempt PDF; if fails, error out
                            try:
                                text = await _extract_text_from_pdf_bytes(content_bytes)
                            except Exception:
                                raise HTTPException(
                                    status_code=400,
                                    detail=f"Unsupported content from URL: {item.url}",
                                )
                    file_path_hint = item.url
                except Exception as e:
                    errors.append(f"Failed to fetch URL {item.url}: {e}")
                    continue

            if text is None or not text.strip():
                errors.append(f"Empty content for {item.name}")
                continue

            # Sanitize, infer first-page details, build metadata and document
            clean_text = sanitize_text_for_encoding(text)
            first_page = clean_text.splitlines()
            first_page_text = "\n".join(
                first_page[:100]
            )  # heuristically treat first ~100 lines as page 1

            inferred_type = item.docType or _infer_doc_type(first_page_text)
            periods = _extract_effective_periods(first_page_text)
            # Primary effective_date: earliest start among periods, else manifest hint
            primary_eff = None
            if periods:
                starts = [p.get("start") for p in periods if p.get("start")]
                if starts:
                    primary_eff = min(starts)
            if not primary_eff and item.effectiveDate:
                primary_eff = item.effectiveDate

            metadata = DocumentMetadata(
                doc_type=inferred_type,
                effective_date=primary_eff,
                effective_periods=periods if periods else None,
                source_url=file_path_hint,
            )
            doc = DocumentInput(text=clean_text, metadata=metadata)
            doc_records.append((doc, item.sequence, primary_eff))

        if not doc_records:
            raise HTTPException(status_code=400, detail="No valid documents to ingest")

        # Assign internal order_index:
        # - Prefer explicit 'sequence' from manifest when provided
        # - Fallback to ascending primary effective_date per batch
        has_explicit_seq = any(seq is not None for (_, seq, _) in doc_records)
        if has_explicit_seq:
            # Sort by sequence; items without sequence go last, keeping their relative order via effective_date
            doc_records.sort(
                key=lambda rec: (
                    rec[1] if rec[1] is not None else float("inf"),
                    rec[2] or datetime.max,
                )
            )
        else:
            # Fallback: sort by primary effective_date, None goes last
            doc_records.sort(key=lambda rec: (rec[2] or datetime.max))

        documents: List[DocumentInput] = [rec[0] for rec in doc_records]
        for idx, d in enumerate(documents, start=1):
            d.metadata.order_index = idx

        # Insert into LightRAG
        track_id = generate_track_id("ingest")
        await rag.ainsert(documents=documents, track_id=track_id)

        status = (
            "success" if not errors else ("partial_success" if documents else "failure")
        )
        msg = (
            "Ingestion started"
            if not errors
            else f"Ingestion started with warnings: {errors[:3]}"
            + ("..." if len(errors) > 3 else "")
        )
        return IngestResponse(status=status, message=msg, track_id=track_id)

    return router
