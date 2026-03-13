"""
Document Sequencing API Routes

Provides endpoints for managing document sequences and temporal ordering.
This enables temporal RAG queries by maintaining document version history.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

# Add project root to path to import data_prep
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from data_prep import ContractSequencer
except ImportError:
    # If data_prep is not available, create a minimal stub
    class ContractSequencer:
        def __init__(self, *args, **kwargs):
            pass

        def prepare_documents(self, *args, **kwargs):
            return []


from lightrag.api.utils_api import get_combined_auth_dependency
from lightrag.utils import logger


class DocumentSequenceUpdate(BaseModel):
    """Model for updating a single document's sequence"""

    document_id: str = Field(..., description="Document ID to update")
    sequence_index: int = Field(..., ge=1, description="New sequence index (1-based)")
    doc_type: Optional[str] = Field(
        None, description="Document type (base, amendment, etc.)"
    )
    effective_date: Optional[str] = Field(
        None, description="Effective date (YYYY-MM-DD)"
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

            # Get document status storage
            doc_storage = rag.doc_status_storage

            # Check if document exists
            doc_status = await doc_storage.get_doc_status(document_id)
            if doc_status is None:
                raise HTTPException(
                    status_code=404, detail=f"Document not found: {document_id}"
                )

            # Update metadata with sequence information
            metadata = doc_status.get("metadata", {})
            metadata["sequence_index"] = update.sequence_index

            if update.doc_type:
                metadata["doc_type"] = update.doc_type

            if update.effective_date:
                metadata["date"] = update.effective_date

            # Update document status
            await doc_storage.update_doc_status(document_id, metadata=metadata)

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

            doc_storage = rag.doc_status_storage
            updated_count = 0
            errors = []

            for update in updates.updates:
                try:
                    # Get document status
                    doc_status = await doc_storage.get_doc_status(update.document_id)
                    if doc_status is None:
                        errors.append(f"Document not found: {update.document_id}")
                        continue

                    # Update metadata
                    metadata = doc_status.get("metadata", {})
                    metadata["sequence_index"] = update.sequence_index

                    if update.doc_type:
                        metadata["doc_type"] = update.doc_type

                    if update.effective_date:
                        metadata["date"] = update.effective_date

                    # Update document status
                    await doc_storage.update_doc_status(
                        update.document_id, metadata=metadata
                    )

                    updated_count += 1

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
            import tempfile

            temp_dir = Path(tempfile.mkdtemp(prefix="lightrag_batch_upload_"))

            try:
                # Get INPUT_DIR from environment or use default
                import os

                input_dir_str = os.getenv("INPUT_DIR", "./inputs")
                input_dir = Path(input_dir_str).resolve()  # Get absolute path
                input_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Using INPUT_DIR: {input_dir} (from env: {input_dir_str})")

                # Save uploaded files to both temp dir (for processing) and INPUT_DIR (for persistence)
                file_paths = []
                filename_to_path = {}
                for file in files:
                    if not file.filename:
                        raise HTTPException(
                            status_code=400, detail="File must have a filename"
                        )
                    # Save to temp directory for processing
                    temp_file_path = temp_dir / file.filename
                    content = await file.read()
                    temp_file_path.write_bytes(content)

                    # Also save to INPUT_DIR for persistence
                    input_file_path = input_dir / file.filename
                    input_file_path.write_bytes(content)
                    logger.info(f"Saved uploaded file to INPUT_DIR: {input_file_path}")

                    # Use INPUT_DIR path for RAG (so it references the persistent file)
                    file_paths.append(input_file_path)
                    filename_to_path[file.filename] = str(input_file_path)

                # Validate that all files in order exist
                uploaded_filenames = {f.filename for f in files}
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
                import shutil

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
                # Clean up on error
                import shutil

                shutil.rmtree(temp_dir, ignore_errors=True)
                raise

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Failed to batch upload sequenced documents: {e}", exc_info=True
            )
            import traceback

            traceback_str = traceback.format_exc()
            logger.error(f"Full traceback:\n{traceback_str}")
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

            doc_storage = rag.doc_status_storage

            # Get all documents
            all_docs = await doc_storage.get_all_doc_statuses()

            # Filter and sort by sequence index
            sequenced_docs = []
            for doc_id, doc_status in all_docs.items():
                metadata = doc_status.get("metadata", {})
                if "sequence_index" in metadata:
                    sequenced_docs.append(
                        {
                            "document_id": doc_id,
                            "file_path": doc_status.get("file_path", ""),
                            "sequence_index": metadata["sequence_index"],
                            "doc_type": metadata.get("doc_type", "unknown"),
                            "effective_date": metadata.get("date", "unknown"),
                            "status": doc_status.get("status", "unknown"),
                        }
                    )

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

            doc_storage = rag.doc_status_storage

            # Check if document exists
            doc_status = await doc_storage.get_doc_status(document_id)
            if doc_status is None:
                raise HTTPException(
                    status_code=404, detail=f"Document not found: {document_id}"
                )

            # Get sequence information before deletion
            metadata = doc_status.get("metadata", {})
            sequence_index = metadata.get("sequence_index")
            effective_date = metadata.get("date")
            doc_type = metadata.get("doc_type")

            logger.info(
                f"Deleting sequenced document {document_id} "
                f"(seq={sequence_index}, date={effective_date}, type={doc_type})"
            )

            # Delete the document using RAG's delete method
            deletion_result = await rag.adelete_by_ids(
                [document_id],
                delete_file=delete_file,
                delete_llm_cache=delete_llm_cache,
            )

            logger.info(
                f"Successfully deleted sequenced document {document_id}. "
                f"Sequence gaps preserved."
            )

            return {
                "status": "success",
                "message": f"Deleted document {document_id}",
                "document_id": document_id,
                "sequence_index": sequence_index,
                "effective_date": effective_date,
                "doc_type": doc_type,
                "deleted_file": delete_file,
                "deleted_cache": delete_llm_cache,
                "deletion_details": {
                    "chunks_deleted": deletion_result.get("chunks_deleted", 0),
                    "entities_deleted": deletion_result.get("entities_deleted", 0),
                    "relations_deleted": deletion_result.get("relations_deleted", 0),
                },
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

            if not file.filename:
                raise HTTPException(status_code=400, detail="File must have a filename")

            doc_storage = rag.doc_status_storage

            # Get original document metadata
            doc_status = await doc_storage.get_doc_status(document_id)
            if doc_status is None:
                raise HTTPException(
                    status_code=404, detail=f"Document not found: {document_id}"
                )

            # Extract sequence metadata to preserve
            original_metadata = doc_status.get("metadata", {})
            sequence_index = original_metadata.get("sequence_index")
            effective_date = original_metadata.get("date")
            doc_type = original_metadata.get("doc_type", "unknown")

            if sequence_index is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Document {document_id} is not a sequenced document",
                )

            logger.info(
                f"Replacing sequenced document {document_id} "
                f"(seq={sequence_index}, date={effective_date}, type={doc_type}) "
                f"with new file: {file.filename}"
            )

            # Delete old document (keep file deletion false to avoid issues)
            await rag.adelete_by_ids(
                [document_id], delete_file=True, delete_llm_cache=False
            )

            logger.info(f"Deleted old document {document_id}")

            # Read new file content
            content = await file.read()

            # Get INPUT_DIR from environment or use default
            import os

            input_dir_str = os.getenv("INPUT_DIR", "./inputs")
            input_dir = Path(input_dir_str).resolve()
            input_dir.mkdir(parents=True, exist_ok=True)

            # Save new file to INPUT_DIR
            new_file_path = input_dir / file.filename
            new_file_path.write_bytes(content)

            logger.info(f"Saved replacement file to: {new_file_path}")

            # Prepare metadata for new document (preserve sequence info)
            new_metadata = {
                "sequence_index": sequence_index,
                "date": effective_date,
                "doc_type": doc_type,
                "replaced_document_id": document_id,  # Track replacement history
                "source": file.filename,
            }

            # Insert new document with preserved metadata
            await rag.ainsert(
                input=content.decode("utf-8", errors="ignore"),
                file_paths=str(new_file_path),
                metadata=new_metadata,
            )

            logger.info(
                f"Successfully replaced document {document_id} with {file.filename} "
                f"(preserved seq={sequence_index}, date={effective_date})"
            )

            return {
                "status": "success",
                "message": f"Replaced document {document_id} with {file.filename}",
                "original_document_id": document_id,
                "new_file": file.filename,
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
