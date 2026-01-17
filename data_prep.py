"""
Data Preprocessing Module for Temporal RAG System

This module provides utilities for sequencing contract documents
and preparing them for ingestion into LightRAG with temporal metadata.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Union


class ContractSequencer:
    """
    Sequences contract files with temporal metadata for RAG ingestion.

    Assigns incrementing sequence indices and extracts effective dates
    from document content to enable temporal retrieval.
    """

    # Common date patterns to extract from documents
    DATE_PATTERNS = [
        r"(?:effective|date|dated|as of)[\s:]+(\d{4}-\d{2}-\d{2})",  # YYYY-MM-DD
        r"(?:effective|date|dated|as of)[\s:]+(\d{1,2}[/-]\d{1,2}[/-]\d{4})",  # MM/DD/YYYY or DD-MM-YYYY
        r"(\d{4}-\d{2}-\d{2})",  # Standalone YYYY-MM-DD
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})",  # Standalone MM/DD/YYYY
    ]

    def __init__(self, files: List[Union[str, Path]], order: List[str]):
        """
        Initialize the ContractSequencer.

        Args:
            files: List of file paths (strings or Path objects)
            order: User-defined order of filenames (e.g., ["Base.md", "Amend1.md"])
        """
        self.files = [Path(f) for f in files]
        self.order = order
        self._validate_inputs()

    def _validate_inputs(self):
        """Validate that all ordered files exist in the files list."""
        file_names = {f.name for f in self.files}
        for ordered_file in self.order:
            if ordered_file not in file_names:
                raise ValueError(
                    f"Ordered file '{ordered_file}' not found in files list"
                )

    def _extract_date(self, content: str) -> str:
        """
        Extract effective date from the first 10 lines of content.

        Args:
            content: Document content as string

        Returns:
            Extracted date in YYYY-MM-DD format, or "unknown" if not found
        """
        lines = content.split("\n")[:10]
        search_text = "\n".join(lines).lower()

        for pattern in self.DATE_PATTERNS:
            match = re.search(pattern, search_text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                # Normalize to YYYY-MM-DD format
                return self._normalize_date(date_str)

        return "unknown"

    def _normalize_date(self, date_str: str) -> str:
        """
        Normalize various date formats to YYYY-MM-DD.

        Args:
            date_str: Date string in various formats

        Returns:
            Date in YYYY-MM-DD format
        """
        # Try common date formats
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d-%m-%Y",
            "%m-%d-%Y",
            "%d/%m/%Y",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # If all parsing fails, return as-is
        return date_str

    def _infer_doc_type(self, content: str, filename: str) -> str:
        """
        Infer document type from first page content and filename.

        Args:
            content: Full document content
            filename: Name of the file

        Returns:
            Document type string ("base", "amendment", etc.)
        """
        # Extract first page content (first 20 lines or ~500 chars)
        lines = content.split("\n")[:20]
        first_page = "\n".join(lines).lower()
        filename_lower = filename.lower()

        # Check content patterns first (more reliable than filename)
        if any(
            pattern in first_page
            for pattern in ["amendment", "amend to", "modification to"]
        ):
            return "amendment"
        elif any(pattern in first_page for pattern in ["supplement", "supplemental"]):
            return "supplement"
        elif any(pattern in first_page for pattern in ["addendum", "added to"]):
            return "addendum"
        elif any(pattern in first_page for pattern in ["revision", "revised"]):
            return "revision"
        elif any(
            pattern in first_page
            for pattern in [
                "base contract",
                "original agreement",
                "service agreement",
                "master agreement",
            ]
        ):
            return "base"

        # Default to unknown for unknown patterns
        return "unknown"

    def prepare_for_ingestion(self) -> List[Dict[str, Any]]:
        """
        Prepare documents for ingestion with temporal metadata.

        Returns:
            List of dictionaries with content and metadata:
            {
                "content": "Original content...",
                "metadata": {
                    "source": "Base.md",
                    "sequence_index": 1,
                    "doc_type": "base",
                    "date": "2023-01-01"
                }
            }
        """
        results = []

        # Create a mapping of filename to file path
        file_map = {f.name: f for f in self.files}

        for idx, filename in enumerate(self.order, start=1):
            file_path = file_map[filename]

            # Read file content
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                raise IOError(f"Failed to read file '{file_path}': {e}")

            # Extract metadata
            effective_date = self._extract_date(content)
            doc_type = self._infer_doc_type(content, filename)

            # Build result dictionary
            result = {
                "content": content,
                "metadata": {
                    "source": filename,
                    "sequence_index": idx,
                    "doc_type": doc_type,
                    "date": effective_date,
                },
            }

            results.append(result)

        return results
