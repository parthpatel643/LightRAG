import os
from dataclasses import dataclass
from typing import Any, Union, final

from lightrag.base import (
    DocProcessingStatus,
    DocStatus,
    DocStatusStorage,
)
from lightrag.exceptions import StorageNotInitializedError
from lightrag.utils import (
    get_pinyin_sort_key,
    load_json,
    logger,
    write_json,
)

from .shared_storage import (
    clear_all_update_flags,
    get_data_init_lock,
    get_namespace_data,
    get_namespace_lock,
    get_update_flag,
    set_all_update_flags,
    try_initialize_namespace,
)


@final
@dataclass
class JsonDocStatusStorage(DocStatusStorage):
    """JSON implementation of document status storage"""

    def __post_init__(self):
        working_dir = self.global_config["working_dir"]
        if self.workspace:
            # Include workspace in the file path for data isolation
            workspace_dir = os.path.join(working_dir, self.workspace)
        else:
            # Default behavior when workspace is empty
            workspace_dir = working_dir
            self.workspace = ""

        os.makedirs(workspace_dir, exist_ok=True)
        self._file_name = os.path.join(workspace_dir, f"kv_store_{self.namespace}.json")
        self._data = None
        self._storage_lock = None
        self.storage_updated = None

    def _sanitize_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Remove invalid document records that are missing required fields

        Args:
            data: Raw data dictionary loaded from storage

        Returns:
            Sanitized dictionary with only valid records
        """
        sanitized = {}
        required_fields = [
            "status",
            "content_summary",
            "content_length",
            "file_path",
            "created_at",
            "updated_at",
        ]

        for doc_id, doc_data in data.items():
            # Skip internal system keys (locks, counters, etc.)
            if doc_id.startswith("__") and doc_id.endswith("__"):
                sanitized[doc_id] = doc_data
                continue

            # Skip non-dict values
            if not isinstance(doc_data, dict):
                logger.warning(f"Skipping invalid document {doc_id}: not a dictionary")
                continue

            # Check for required fields
            missing_fields = [f for f in required_fields if f not in doc_data]
            if missing_fields:
                logger.warning(
                    f"Skipping document {doc_id}: missing required fields {missing_fields}"
                )
                continue

            # Valid record
            sanitized[doc_id] = doc_data

        return sanitized

    async def initialize(self):
        """Initialize storage data"""
        self._storage_lock = get_namespace_lock(
            self.namespace, workspace=self.workspace
        )
        self.storage_updated = await get_update_flag(
            self.namespace, workspace=self.workspace
        )
        async with get_data_init_lock():
            # check need_init must before get_namespace_data
            need_init = await try_initialize_namespace(
                self.namespace, workspace=self.workspace
            )
            self._data = await get_namespace_data(
                self.namespace, workspace=self.workspace
            )
            if need_init:
                loaded_data = load_json(self._file_name) or {}
                # Sanitize loaded data to remove invalid records
                sanitized_data = self._sanitize_data(loaded_data)
                if len(sanitized_data) < len(loaded_data):
                    logger.warning(
                        f"[{self.workspace}] Removed {len(loaded_data) - len(sanitized_data)} invalid records during initialization"
                    )
                async with self._storage_lock:
                    self._data.update(sanitized_data)
                    logger.info(
                        f"[{self.workspace}] Process {os.getpid()} doc status load {self.namespace} with {len(sanitized_data)} records"
                    )

    async def filter_keys(self, keys: set[str]) -> set[str]:
        """Return keys that should be processed (not in storage or not successfully processed)"""
        if self._storage_lock is None:
            raise StorageNotInitializedError("JsonDocStatusStorage")
        async with self._storage_lock:
            return set(keys) - set(self._data.keys())

    async def get_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        ordered_results: list[dict[str, Any] | None] = []
        if self._storage_lock is None:
            raise StorageNotInitializedError("JsonDocStatusStorage")
        async with self._storage_lock:
            for id in ids:
                data = self._data.get(id, None)
                if data:
                    # Validate data integrity before returning
                    if isinstance(data, dict) and "status" in data:
                        ordered_results.append(data.copy())
                    else:
                        logger.warning(
                            f"Document {id} has invalid data, returning None"
                        )
                        ordered_results.append(None)
                else:
                    ordered_results.append(None)
        return ordered_results

    async def get_status_counts(self) -> dict[str, int]:
        """Get counts of documents in each status"""
        counts = {status.value: 0 for status in DocStatus}
        if self._storage_lock is None:
            raise StorageNotInitializedError("JsonDocStatusStorage")
        async with self._storage_lock:
            for k, doc in self._data.items():
                # Skip internal metadata entries
                if k.startswith("__") and k.endswith("__"):
                    continue

                # Skip documents without status field (data integrity issue)
                if not isinstance(doc, dict) or "status" not in doc:
                    logger.warning(
                        f"Document {k} missing 'status' field in count, skipping"
                    )
                    continue
                counts[doc["status"]] += 1
        return counts

    async def get_docs_by_status(
        self, status: DocStatus
    ) -> dict[str, DocProcessingStatus]:
        """Get all documents with a specific status"""
        if self._storage_lock is None:
            raise StorageNotInitializedError("JsonDocStatusStorage")
        result = {}
        async with self._storage_lock:
            for k, v in self._data.items():
                # Skip internal metadata entries (used by SequenceIndexManager, etc.)
                if k.startswith("__") and k.endswith("__"):
                    continue

                if isinstance(v, dict) and v.get("_is_metadata"):
                    continue

                # Skip documents without status field (data integrity issue)
                if not isinstance(v, dict) or "status" not in v:
                    logger.warning(f"Document {k} missing 'status' field, skipping")
                    continue

                if v["status"] == status.value:
                    try:
                        # Make a copy of the data to avoid modifying the original
                        data = v.copy()
                        # Remove deprecated content field if it exists
                        data.pop("content", None)
                        # If file_path is not in data, use document id as file path
                        if "file_path" not in data:
                            data["file_path"] = "no-file-path"
                        # Ensure new fields exist with default values
                        if "metadata" not in data:
                            data["metadata"] = {}
                        if "error_msg" not in data:
                            data["error_msg"] = None

                        # Convert status string to DocStatus enum
                        if "status" in data and isinstance(data["status"], str):
                            data["status"] = DocStatus(data["status"])

                        result[k] = DocProcessingStatus(**data)
                    except KeyError as e:
                        logger.error(
                            f"[{self.workspace}] Missing required field for document {k}: {e}"
                        )
                        continue
        return result

    async def get_docs_by_track_id(
        self, track_id: str
    ) -> dict[str, DocProcessingStatus]:
        """Get all documents with a specific track_id"""
        if self._storage_lock is None:
            raise StorageNotInitializedError("JsonDocStatusStorage")
        result = {}
        async with self._storage_lock:
            for k, v in self._data.items():
                # Skip internal metadata entries
                if k.startswith("__") and k.endswith("__"):
                    continue

                if isinstance(v, dict) and v.get("_is_metadata"):
                    continue

                if v.get("track_id") == track_id:
                    try:
                        # Make a copy of the data to avoid modifying the original
                        data = v.copy()
                        # Remove deprecated content field if it exists
                        data.pop("content", None)
                        # If file_path is not in data, use document id as file path
                        if "file_path" not in data:
                            data["file_path"] = "no-file-path"
                        # Ensure new fields exist with default values
                        if "metadata" not in data:
                            data["metadata"] = {}
                        if "error_msg" not in data:
                            data["error_msg"] = None

                        # Convert status string to DocStatus enum
                        if "status" in data and isinstance(data["status"], str):
                            data["status"] = DocStatus(data["status"])

                        result[k] = DocProcessingStatus(**data)
                    except KeyError as e:
                        logger.error(
                            f"[{self.workspace}] Missing required field for document {k}: {e}"
                        )
                        continue
        return result

    async def index_done_callback(self) -> None:
        async with self._storage_lock:
            if self.storage_updated.value:
                data_dict = (
                    dict(self._data) if hasattr(self._data, "_getvalue") else self._data
                )
                logger.debug(
                    f"[{self.workspace}] Process {os.getpid()} doc status writting {len(data_dict)} records to {self.namespace}"
                )

                # Write JSON and check if sanitization was applied
                needs_reload = write_json(data_dict, self._file_name)

                # If data was sanitized, reload cleaned data to update shared memory
                if needs_reload:
                    logger.info(
                        f"[{self.workspace}] Reloading sanitized data into shared memory for {self.namespace}"
                    )
                    cleaned_data = load_json(self._file_name)
                    if cleaned_data is not None:
                        self._data.clear()
                        self._data.update(cleaned_data)

                await clear_all_update_flags(self.namespace, workspace=self.workspace)

    async def upsert(self, data: dict[str, dict[str, Any]]) -> None:
        """
        Importance notes for in-memory storage:
        1. Changes will be persisted to disk during the next index_done_callback
        2. update flags to notify other processes that data persistence is needed
        """
        if not data:
            return
        logger.debug(
            f"[{self.workspace}] Inserting {len(data)} records to {self.namespace}"
        )
        if self._storage_lock is None:
            raise StorageNotInitializedError("JsonDocStatusStorage")

        # Validate data before upserting
        validated_data = {}
        required_fields = [
            "status",
            "content_summary",
            "content_length",
            "file_path",
            "created_at",
            "updated_at",
        ]

        for doc_id, doc_data in data.items():
            # Skip internal system keys (locks, counters, etc.)
            if doc_id.startswith("__") and doc_id.endswith("__"):
                validated_data[doc_id] = doc_data
                continue

            # Validate required fields for regular documents
            missing_fields = [f for f in required_fields if f not in doc_data]
            if missing_fields:
                logger.error(
                    f"Cannot upsert document {doc_id}: missing required fields {missing_fields}"
                )
                continue

            # Ensure optional fields have defaults
            if "chunks_list" not in doc_data:
                doc_data["chunks_list"] = []
            if "metadata" not in doc_data:
                doc_data["metadata"] = {}
            if "error_msg" not in doc_data:
                doc_data["error_msg"] = None

            validated_data[doc_id] = doc_data

        if validated_data:
            async with self._storage_lock:
                self._data.update(validated_data)
                await set_all_update_flags(self.namespace, workspace=self.workspace)
            await self.index_done_callback()
        else:
            logger.warning(f"[{self.workspace}] No valid records to upsert")

    async def is_empty(self) -> bool:
        """Check if the storage is empty

        Returns:
            bool: True if storage is empty, False otherwise

        Raises:
            StorageNotInitializedError: If storage is not initialized
        """
        if self._storage_lock is None:
            raise StorageNotInitializedError("JsonDocStatusStorage")
        async with self._storage_lock:
            return len(self._data) == 0

    async def get_by_id(self, id: str) -> Union[dict[str, Any], None]:
        async with self._storage_lock:
            return self._data.get(id)

    async def get_docs_paginated(
        self,
        status_filter: DocStatus | None = None,
        page: int = 1,
        page_size: int = 50,
        sort_field: str = "updated_at",
        sort_direction: str = "desc",
    ) -> tuple[list[tuple[str, DocProcessingStatus]], int]:
        """Get documents with pagination support

        Args:
            status_filter: Filter by document status, None for all statuses
            page: Page number (1-based)
            page_size: Number of documents per page (10-200)
            sort_field: Field to sort by ('created_at', 'updated_at', 'id')
            sort_direction: Sort direction ('asc' or 'desc')

        Returns:
            Tuple of (list of (doc_id, DocProcessingStatus) tuples, total_count)
        """
        # Validate parameters
        if page < 1:
            page = 1
        if page_size < 10:
            page_size = 10
        elif page_size > 200:
            page_size = 200

        if sort_field not in ["created_at", "updated_at", "id", "file_path"]:
            sort_field = "updated_at"

        if sort_direction.lower() not in ["asc", "desc"]:
            sort_direction = "desc"

        # For JSON storage, we load all data and sort/filter in memory
        all_docs = []

        async with self._storage_lock:
            for doc_id, doc_data in self._data.items():
                # Skip internal metadata entries
                if doc_id.startswith("__") and doc_id.endswith("__"):
                    continue

                if doc_data.get("_is_metadata"):
                    continue

                # Skip documents without status field
                if "status" not in doc_data:
                    logger.warning(
                        f"Document {doc_id} missing 'status' field, skipping"
                    )
                    continue

                # Apply status filter
                if (
                    status_filter is not None
                    and doc_data.get("status") != status_filter.value
                ):
                    continue

                try:
                    # Prepare document data
                    data = doc_data.copy()
                    data.pop("content", None)
                    if "file_path" not in data:
                        data["file_path"] = "no-file-path"
                    if "metadata" not in data:
                        data["metadata"] = {}
                    if "error_msg" not in data:
                        data["error_msg"] = None

                    # Convert status string to DocStatus enum
                    if "status" in data and isinstance(data["status"], str):
                        data["status"] = DocStatus(data["status"])

                    doc_status = DocProcessingStatus(**data)

                    # Add sort key for sorting
                    if sort_field == "id":
                        doc_status._sort_key = doc_id
                    elif sort_field == "file_path":
                        # Use pinyin sorting for file_path field to support Chinese characters
                        file_path_value = getattr(doc_status, sort_field, "")
                        doc_status._sort_key = get_pinyin_sort_key(file_path_value)
                    else:
                        doc_status._sort_key = getattr(doc_status, sort_field, "")

                    all_docs.append((doc_id, doc_status))

                except KeyError as e:
                    logger.error(
                        f"[{self.workspace}] Error processing document {doc_id}: {e}"
                    )
                    continue

        # Sort documents
        reverse_sort = sort_direction.lower() == "desc"
        all_docs.sort(
            key=lambda x: getattr(x[1], "_sort_key", ""), reverse=reverse_sort
        )

        # Remove sort key from documents
        for doc_id, doc in all_docs:
            if hasattr(doc, "_sort_key"):
                delattr(doc, "_sort_key")

        total_count = len(all_docs)

        # Apply pagination
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_docs = all_docs[start_idx:end_idx]

        return paginated_docs, total_count

    async def get_all_status_counts(self) -> dict[str, int]:
        """Get counts of documents in each status for all documents

        Returns:
            Dictionary mapping status names to counts, including 'all' field
        """
        counts = await self.get_status_counts()

        # Add 'all' field with total count
        total_count = sum(counts.values())
        counts["all"] = total_count

        return counts

    async def delete(self, doc_ids: list[str]) -> None:
        """Delete specific records from storage by their IDs

        Importance notes for in-memory storage:
        1. Changes will be persisted to disk during the next index_done_callback
        2. update flags to notify other processes that data persistence is needed

        Args:
            ids (list[str]): List of document IDs to be deleted from storage

        Returns:
            None
        """
        async with self._storage_lock:
            any_deleted = False
            for doc_id in doc_ids:
                result = self._data.pop(doc_id, None)
                if result is not None:
                    any_deleted = True

            if any_deleted:
                await set_all_update_flags(self.namespace, workspace=self.workspace)

    async def get_doc_by_file_path(self, file_path: str) -> Union[dict[str, Any], None]:
        """Get document by file path

        Args:
            file_path: The file path to search for

        Returns:
            Union[dict[str, Any], None]: Document data if found, None otherwise
            Returns the same format as get_by_ids method
        """
        if self._storage_lock is None:
            raise StorageNotInitializedError("JsonDocStatusStorage")

        async with self._storage_lock:
            for doc_id, doc_data in self._data.items():
                if doc_data.get("file_path") == file_path:
                    # Return complete document data, consistent with get_by_ids method
                    return doc_data

        return None

    async def drop(self) -> dict[str, str]:
        """Drop all document status data from storage and clean up resources

        This method will:
        1. Clear all document status data from memory
        2. Update flags to notify other processes
        3. Trigger index_done_callback to save the empty state

        Returns:
            dict[str, str]: Operation status and message
            - On success: {"status": "success", "message": "data dropped"}
            - On failure: {"status": "error", "message": "<error details>"}
        """
        try:
            async with self._storage_lock:
                self._data.clear()
                await set_all_update_flags(self.namespace, workspace=self.workspace)

            await self.index_done_callback()
            logger.info(
                f"[{self.workspace}] Process {os.getpid()} drop {self.namespace}"
            )
            return {"status": "success", "message": "data dropped"}
        except Exception as e:
            logger.error(f"[{self.workspace}] Error dropping {self.namespace}: {e}")
            return {"status": "error", "message": str(e)}
