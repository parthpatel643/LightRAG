"""
Document Sequencing API Routes

Provides endpoints for managing document sequences and temporal ordering.
This enables temporal RAG queries by maintaining document version history.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from lightrag.api.routers.document_routes import (
    pipeline_index_file,
    sanitize_filename,
)
from lightrag.api.utils_api import get_combined_auth_dependency
from lightrag.api.config import global_args
from lightrag.temporal.data_prep import ContractSequencer
from lightrag.utils import generate_track_id, logger

_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
_UNSEQUENCEABLE_STATUSES = {"processed", "processing", "parsing", "analyzing"}


class DocumentSequenceUpdate(BaseModel):
    """Model for updating a single document's sequence"""

    document_id: str = Field(..., description="Document ID to update")
    sequence_index: int = Field(..., ge=1, description="New sequence index (1-based)")
    doc_type: Optional[str] = Field(
        None, description="Document type (base, amendment, etc.)"
    )
    effective_date: Optional[str] = Field(
        None, pattern=_DATE_PATTERN, description="Effective date (YYYY-MM-DD)"
    )


class BatchSequenceUpdate(BaseModel):
    """Model for updating multiple documents' sequences"""

    updates: List[DocumentSequenceUpdate] = Field(
        ..., description="List of sequence updates"
    )


class SequenceResponse(BaseModel):
    """Response model for sequence operations"""

    status: str
    message: str
    updated_count: int = 0


class BatchUploadSequencedRequest(BaseModel):
    """Request model for batch upload with sequencing"""

    order: List[str] = Field(..., description="Ordered list of filenames")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Additional metadata"
    )


def create_sequencing_routes(rag: Any, api_key: Optional[str] = None):
    """
    Create document sequencing routes with RAG instance injection.

    Args:
        rag: LightRAG instance
        api_key: Optional API key for authentication

    Returns:
        APIRouter with all sequencing endpoints
    """
    router = APIRouter(prefix="/documents", tags=["documents", "sequencing"])
    combined_auth = get_combined_auth_dependency(api_key)

    async def _apply_sequence_update(update: DocumentSequenceUpdate) -> None:
        """Validate and persist one sequence/date/type update (raises HTTPException)."""
        doc = await rag.doc_status.get_by_id(update.document_id)
        if doc is None:
            raise HTTPException(
                status_code=404, detail=f"Document not found: {update.document_id}"
            )
        metadata = dict(doc.get("metadata") or {})
        status = getattr(doc.get("status"), "value", doc.get("status"))
        status = str(status or "").lower()
        current_index = metadata.get("sequence_index")

        if update.sequence_index != current_index:
            # The index is baked into the graph ([vN] entity names) and into
            # every chunk at processing time; rewriting it on the status row
            # alone would leave the graph disagreeing with doc_status.
            if status in _UNSEQUENCEABLE_STATUSES:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Document {update.document_id} is {status}; its sequence "
                        "index is part of the knowledge graph and cannot be changed "
                        "in place. Use /documents/{id}/replace or delete and "
                        "re-upload it."
                    ),
                )
            from lightrag.temporal.sequence_index import collect_sequence_dates

            if update.sequence_index in await collect_sequence_dates(rag.doc_status):
                raise HTTPException(
                    status_code=409,
                    detail=f"Sequence index {update.sequence_index} is already in use",
                )
            metadata["sequence_index"] = update.sequence_index
        if update.doc_type:
            metadata["doc_type"] = update.doc_type
        if update.effective_date:
            metadata["effective_date"] = update.effective_date
            metadata.pop("date", None)

        await rag.doc_status.update_doc_status_fields(
            update.document_id, {"metadata": metadata}
        )
    @router.patch("/{document_id}/sequence")
    async def update_document_sequence(
        document_id: str,
        update: DocumentSequenceUpdate,
        _auth=Depends(combined_auth),
    ):
        """
        Update the sequence index of a single document.

        This allows reordering documents in the temporal sequence.
        """
        try:
            if rag is None:
                raise HTTPException(
                    status_code=500, detail="RAG instance not available"
                )

            await _apply_sequence_update(update)

            logger.info(
                f"Updated sequence for document {document_id}: index={update.sequence_index}"
            )

            return SequenceResponse(
                status="success",
                message=f"Updated sequence index for document {document_id}",
                updated_count=1,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update document sequence: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to update document sequence: {str(e)}"
            )

    @router.post("/batch-sequence")
    async def batch_update_sequences(
        updates: BatchSequenceUpdate,
        _auth=Depends(combined_auth),
    ):
        """
        Update sequence indices for multiple documents in a single request.

        This is more efficient than updating documents one by one.
        """
        try:
            if rag is None:
                raise HTTPException(
                    status_code=500, detail="RAG instance not available"
                )

            updated_count = 0
            errors = []

            for update in updates.updates:
                try:
                    await _apply_sequence_update(update)
                    updated_count += 1
                except HTTPException as e:
                    errors.append(f"{update.document_id}: {e.detail}")
                except Exception as e:
                    errors.append(f"Failed to update {update.document_id}: {str(e)}")

            if errors:
                logger.warning(f"Batch sequence update completed with errors: {errors}")

            logger.info(f"Batch updated {updated_count} document sequences")

            return SequenceResponse(
                status="success" if not errors else "partial_success",
                message=f"Updated {updated_count} documents"
                + (f". Errors: {'; '.join(errors)}" if errors else ""),
                updated_count=updated_count,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to batch update sequences: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to batch update sequences: {str(e)}"
            )

    @router.post("/batch-upload-sequenced")
    async def batch_upload_sequenced(
        files: List[UploadFile] = File(...),
        order: str = Form(...),  # JSON string of ordered filenames
        metadata: str = Form(default="{}"),  # JSON string of additional metadata
        _auth=Depends(combined_auth),
    ):
        """
        Upload multiple files with automatic sequencing based on provided order.

        This endpoint:
        1. Accepts multiple files
        2. Orders them according to the provided sequence
        3. Uses ContractSequencer to inject temporal metadata
        4. Inserts documents with sequence indices

        The order parameter should be a JSON array of filenames in the desired sequence.
        Example: ["Base.md", "Amendment1.md", "Amendment2.md"]
        """
        try:
            logger.info(f"Starting batch upload sequenced with {len(files)} files")

            if rag is None:
                logger.error("RAG instance not available")
                raise HTTPException(
                    status_code=500, detail="RAG instance not available"
                )

            # Parse order and metadata
            try:
                file_order = json.loads(order)
                extra_metadata = json.loads(metadata)
                logger.debug(f"Parsed file_order: {file_order}")
                logger.debug(f"Parsed extra_metadata: {extra_metadata}")
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid JSON in order or metadata: {str(e)}",
                )

            if not isinstance(file_order, list):
                logger.error(f"Order is not a list: {type(file_order)}")
                raise HTTPException(
                    status_code=400, detail="Order must be a JSON array of filenames"
                )

            # Create temporary directory for uploaded files
            temp_dir = Path(tempfile.mkdtemp(prefix="lightrag_batch_upload_"))

            try:
                input_dir = Path(
                    getattr(global_args, "input_dir", None)
                    or os.getenv("INPUT_DIR", "./inputs")
                ).resolve()
                input_dir.mkdir(parents=True, exist_ok=True)
                max_upload = getattr(global_args, "max_upload_size", None)

                # Save uploaded files to both temp dir (for processing) and INPUT_DIR (for persistence)
                file_paths = []
                created_files: list[Path] = []
                filename_to_path = {}
                for file in files:
                    # Same rules as /documents/upload: a single literal
                    # basename, rejected (never rewritten) when unsafe.
                    safe_name = sanitize_filename(file.filename or "", input_dir)
                    content = await file.read()
                    if max_upload and max_upload > 0 and len(content) > max_upload:
                        raise HTTPException(
                            status_code=413,
                            detail=f"File too large: {safe_name} exceeds {max_upload} bytes",
                        )
                    (temp_dir / safe_name).write_bytes(content)

                    # Also save to INPUT_DIR for persistence; exclusive create so
                    # an existing document's file is never overwritten.
                    input_file_path = input_dir / safe_name
                    try:
                        with open(input_file_path, "xb") as out_file:
                            out_file.write(content)
                    except FileExistsError:
                        raise HTTPException(
                            status_code=409,
                            detail=f"File '{safe_name}' already exists in the input directory",
                        )
                    logger.info(f"Saved uploaded file to INPUT_DIR: {input_file_path}")
                    created_files.append(input_file_path)

                    # Use INPUT_DIR path for RAG (so it references the persistent file)
                    file_paths.append(input_file_path)
                    filename_to_path[safe_name] = str(input_file_path)

                # Validate that all files in order exist
                uploaded_filenames = set(filename_to_path)
                for filename in file_order:
                    if filename not in uploaded_filenames:
                        raise HTTPException(
                            status_code=400,
                            detail=f"File '{filename}' in order not found in uploaded files",
                        )

                # Use ContractSequencer to prepare documents
                logger.info(
                    f"Initializing ContractSequencer with {len(file_paths)} files"
                )
                try:
                    sequencer = ContractSequencer(file_paths, file_order)
                    logger.info("ContractSequencer initialized successfully")
                except Exception as e:
                    logger.error(
                        f"Failed to initialize ContractSequencer: {e}", exc_info=True
                    )
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to initialize ContractSequencer: {str(e)}",
                    )

                try:
                    sequenced_docs = sequencer.prepare_for_ingestion()
                    logger.info(
                        f"Prepared {len(sequenced_docs)} documents for ingestion"
                    )
                except Exception as e:
                    logger.error(f"Failed to prepare documents: {e}", exc_info=True)
                    raise HTTPException(
                        status_code=500, detail=f"Failed to prepare documents: {str(e)}"
                    )

                # Insert documents with metadata
                inserted_count = 0
                errors = []

                for idx, doc in enumerate(sequenced_docs):
                    try:
                        logger.debug(
                            f"Processing document {idx + 1}/{len(sequenced_docs)}"
                        )
                        content = doc["content"]

                        # Merge metadata: extra_metadata from frontend takes precedence
                        # This allows frontend to override sequence_index and other fields
                        source_filename = doc["metadata"]["source"]
                        file_specific_metadata = extra_metadata.get(source_filename, {})
                        doc_metadata = {**doc["metadata"], **file_specific_metadata}

                        logger.info(f"Document metadata for {source_filename}:")
                        logger.info(f"  - From ContractSequencer: {doc['metadata']}")
                        logger.info(
                            f"  - From frontend (extra_metadata): {file_specific_metadata}"
                        )
                        logger.info(f"  - Final merged metadata: {doc_metadata}")

                        # Get the actual file path from the filename
                        actual_file_path = filename_to_path.get(
                            source_filename, source_filename
                        )

                        logger.debug(
                            f"Inserting document: {source_filename} -> {actual_file_path}"
                        )

                        # Insert document
                        await rag.ainsert(
                            input=content,
                            file_paths=actual_file_path,
                            metadata=doc_metadata,
                        )

                        inserted_count += 1
                        logger.info(
                            f"Inserted sequenced document: {doc_metadata['source']} (seq={doc_metadata['sequence_index']})"
                        )

                    except Exception as e:
                        error_msg = (
                            f"Failed to insert {doc['metadata']['source']}: {str(e)}"
                        )
                        errors.append(error_msg)
                        logger.error(error_msg, exc_info=True)

                # Clean up temporary directory
                shutil.rmtree(temp_dir, ignore_errors=True)

                if errors:
                    logger.warning(f"Batch upload completed with errors: {errors}")

                return {
                    "status": "success" if not errors else "partial_success",
                    "message": f"Uploaded and sequenced {inserted_count} documents"
                    + (f". Errors: {'; '.join(errors)}" if errors else ""),
                    "inserted_count": inserted_count,
                    "total_files": len(files),
                }

            except Exception:
                # Clean up on error, including files persisted before the
                # failure (nothing has been ingested from them yet).
                shutil.rmtree(temp_dir, ignore_errors=True)
                for created in created_files:
                    created.unlink(missing_ok=True)
                raise

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Failed to batch upload sequenced documents: {e}", exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to batch upload sequenced documents: {str(e)}",
            )

    @router.get("/sequences")
    async def get_document_sequences(_auth=Depends(combined_auth)):
        """
        Get all documents with their sequence information.

        Returns documents sorted by sequence index.
        """
        try:
            if rag is None:
                raise HTTPException(
                    status_code=500, detail="RAG instance not available"
                )

            sequenced_docs = []
            page = 1
            while True:
                docs, total = await rag.doc_status.get_docs_paginated(
                    page=page, page_size=200, sort_field="created_at", sort_direction="asc"
                )
                for doc_id, doc in docs:
                    metadata = doc.metadata or {}
                    if metadata.get("is_duplicate") or "sequence_index" not in metadata:
                        continue
                    status = getattr(doc.status, "value", doc.status)
                    sequenced_docs.append(
                        {
                            "document_id": doc_id,
                            "file_path": doc.file_path or "",
                            "sequence_index": metadata["sequence_index"],
                            "doc_type": metadata.get("doc_type", "unknown"),
                            "effective_date": metadata.get("effective_date")
                            or metadata.get("date")
                            or "unknown",
                            "status": status or "unknown",
                        }
                    )
                if not docs or page * 200 >= total:
                    break
                page += 1

            # Sort by sequence index
            sequenced_docs.sort(key=lambda x: x["sequence_index"])

            return {
                "status": "success",
                "count": len(sequenced_docs),
                "documents": sequenced_docs,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get document sequences: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to get document sequences: {str(e)}"
            )

    @router.delete("/{document_id}/sequenced")
    async def delete_sequenced_document(
        document_id: str,
        delete_file: bool = True,
        delete_llm_cache: bool = False,
        _auth=Depends(combined_auth),
    ):
        """
        Delete a sequenced document while preserving sequence gaps.

        This endpoint removes a document from the system without reindexing
        other documents in the sequence. Sequence gaps are intentionally preserved
        to maintain temporal integrity.

        Args:
            document_id: ID of the document to delete
            delete_file: Whether to delete the physical file (default: True)
            delete_llm_cache: Whether to delete LLM cache entries (default: False)

        Returns:
            Deletion status and details

        Example:
            DELETE /documents/doc_123/sequenced?delete_file=true&delete_llm_cache=false
        """
        try:
            if rag is None:
                raise HTTPException(
                    status_code=500, detail="RAG instance not available"
                )

            # Check if document exists
            doc_status = await rag.doc_status.get_by_id(document_id)
            if doc_status is None:
                raise HTTPException(
                    status_code=404, detail=f"Document not found: {document_id}"
                )

            # Get sequence information before deletion
            metadata = doc_status.get("metadata") or {}
            sequence_index = metadata.get("sequence_index")
            effective_date = metadata.get("effective_date") or metadata.get("date")
            doc_type = metadata.get("doc_type")
            stored_path = doc_status.get("file_path")

            logger.info(
                f"Deleting sequenced document {document_id} "
                f"(seq={sequence_index}, date={effective_date}, type={doc_type})"
            )

            deletion_result = await rag.adelete_by_doc_id(
                document_id, delete_llm_cache=delete_llm_cache
            )
            if deletion_result.status == "not_allowed":
                raise HTTPException(
                    status_code=deletion_result.status_code or 409,
                    detail=deletion_result.message,
                )
            if deletion_result.status != "success":
                raise HTTPException(
                    status_code=deletion_result.status_code
                    if deletion_result.status_code >= 400
                    else 500,
                    detail=deletion_result.message,
                )

            file_deleted = False
            if delete_file and stored_path:
                input_dir = Path(getattr(global_args, "input_dir", "./inputs")).resolve()
                candidate = input_dir / Path(stored_path).name
                if candidate.parent == input_dir and candidate.is_file():
                    candidate.unlink()
                    file_deleted = True

            logger.info(
                f"Successfully deleted sequenced document {document_id}. "
                f"Sequence gaps preserved."
            )

            return {
                "status": "success",
                "message": deletion_result.message or f"Deleted document {document_id}",
                "document_id": document_id,
                "sequence_index": sequence_index,
                "effective_date": effective_date,
                "doc_type": doc_type,
                "deleted_file": file_deleted,
                "deleted_cache": delete_llm_cache,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete sequenced document: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete sequenced document: {str(e)}",
            )

    @router.post("/{document_id}/replace")
    async def replace_sequenced_document(
        document_id: str,
        file: UploadFile = File(...),
        _auth=Depends(combined_auth),
    ):
        """
        Replace a sequenced document with new content while preserving metadata.

        This endpoint:
        1. Retrieves the original document's sequence metadata
        2. Deletes the old document
        3. Uploads the new document with the same sequence_index and effective_date
        4. Maintains the document's position in the temporal sequence

        Args:
            document_id: ID of the document to replace
            file: New file to upload

        Returns:
            Upload status and new document details

        Example:
            POST /documents/doc_123/replace
            Content-Type: multipart/form-data
            file: <new_file.pdf>
        """
        try:
            if rag is None:
                raise HTTPException(
                    status_code=500, detail="RAG instance not available"
                )

            input_dir = Path(
                getattr(global_args, "input_dir", None) or os.getenv("INPUT_DIR", "./inputs")
            ).resolve()
            input_dir.mkdir(parents=True, exist_ok=True)
            safe_name = sanitize_filename(file.filename or "", input_dir)

            content = await file.read()
            max_upload = getattr(global_args, "max_upload_size", None)
            if max_upload and max_upload > 0 and len(content) > max_upload:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large: {safe_name} exceeds {max_upload} bytes",
                )

            # Get original document metadata
            doc_status = await rag.doc_status.get_by_id(document_id)
            if doc_status is None:
                raise HTTPException(
                    status_code=404, detail=f"Document not found: {document_id}"
                )

            # Extract sequence metadata to preserve
            original_metadata = doc_status.get("metadata") or {}
            sequence_index = original_metadata.get("sequence_index")
            effective_date = original_metadata.get(
                "effective_date"
            ) or original_metadata.get("date")
            doc_type = original_metadata.get("doc_type", "unknown")
            old_stored_path = doc_status.get("file_path")

            if sequence_index is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Document {document_id} is not a sequenced document",
                )

            logger.info(
                f"Replacing sequenced document {document_id} "
                f"(seq={sequence_index}, date={effective_date}, type={doc_type}) "
                f"with new file: {safe_name}"
            )

            # The new bytes are already in memory, so the old document is only
            # removed once nothing about the request can still be rejected.
            deletion_result = await rag.adelete_by_doc_id(
                document_id, delete_llm_cache=False
            )
            if deletion_result.status != "success":
                raise HTTPException(
                    status_code=deletion_result.status_code
                    if deletion_result.status_code >= 400
                    else 409,
                    detail=deletion_result.message,
                )
            logger.info(f"Deleted old document {document_id}")

            if old_stored_path:
                old_file = input_dir / Path(old_stored_path).name
                if old_file.parent == input_dir and old_file.is_file():
                    old_file.unlink()

            new_file_path = input_dir / safe_name
            try:
                with open(new_file_path, "xb") as out_file:
                    out_file.write(content)
            except FileExistsError:
                raise HTTPException(
                    status_code=409,
                    detail=f"File '{safe_name}' already exists in the input directory",
                )
            logger.info(f"Saved replacement file to: {new_file_path}")

            # Index through the standard file pipeline (real parsing for
            # PDF/DOCX, dedupe, admission) with the preserved sequence info.
            await pipeline_index_file(
                rag,
                new_file_path,
                generate_track_id("replace"),
                metadata={
                    "sequence_index": sequence_index,
                    "effective_date": effective_date or "unknown",
                    "doc_type": doc_type,
                },
            )

            logger.info(
                f"Successfully replaced document {document_id} with {safe_name} "
                f"(preserved seq={sequence_index}, date={effective_date})"
            )

            return {
                "status": "success",
                "message": f"Replaced document {document_id} with {safe_name}",
                "original_document_id": document_id,
                "new_file": safe_name,
                "preserved_metadata": {
                    "sequence_index": sequence_index,
                    "effective_date": effective_date,
                    "doc_type": doc_type,
                },
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to replace sequenced document: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to replace sequenced document: {str(e)}",
            )

    return router


# Made with Bob
