"""
Data Preprocessing Module for Temporal RAG System

This module provides utilities for sequencing contract documents
and preparing them for ingestion into LightRAG with temporal metadata.


Instead of extracting a single date per document, this module now:
1. Scans each paragraph for date patterns
2. Wraps found dates with XML tags: <EFFECTIVE_DATE confidence="high">YYYY-MM-DD</EFFECTIVE_DATE>
3. Preserves dates as part of content (not hidden metadata) for LLM interpretation
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Union


class ContractSequencer:
    """
    Sequences contract files with temporal metadata for RAG ingestion.

    Assigns incrementing sequence indices and injects effective date tags
    directly into content for LLM interpretation (Soft Tagging).

    Instead of extracting dates as hidden metadata, this class now:
    - Identifies date patterns at paragraph level
    - Wraps dates with <EFFECTIVE_DATE> tags in the content
    - Allows LLM to interpret temporal confidence during generation
    """

    # Comprehensive date patterns with context markers
    DATE_PATTERNS_WITH_CONTEXT = [
        # High-confidence patterns (explicit temporal markers)
        (
            r"(?:effective|commencing|beginning|starting|valid from)\s+(?:as of\s+)?(\d{4}-\d{2}-\d{2})",
            "high",
        ),
        (
            r"(?:effective|commencing|beginning|starting|valid from)\s+(?:as of\s+)?(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
            "high",
        ),
        (
            r"(?:shall take effect on|becomes effective on|effective date is)\s+(\d{4}-\d{2}-\d{2})",
            "high",
        ),
        (
            r"(?:shall take effect on|becomes effective on|effective date is)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
            "high",
        ),
        # Medium-confidence patterns (contextual dates)
        (r"(?:dated|as of|on|from)\s+(\d{4}-\d{2}-\d{2})", "medium"),
        (r"(?:dated|as of|on|from)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})", "medium"),
        # Low-confidence patterns (standalone dates)
        (r"\b(\d{4}-\d{2}-\d{2})\b", "low"),
        (r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b", "low"),
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
        Extract first effective date from the first 10 lines (legacy method).

        NOTE: This is deprecated for hard filtering.
        Now used only for display/logging purposes.

        Args:
            content: Document content as string

        Returns:
            Extracted date in YYYY-MM-DD format, or "unknown" if not found
        """
        lines = content.split("\n")[:10]
        search_text = "\n".join(lines).lower()

        for pattern, confidence in self.DATE_PATTERNS_WITH_CONTEXT:
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

    def _inject_soft_tags(self, content: str) -> str:
        """
        Inject <EFFECTIVE_DATE> tags around date patterns in content.

        Soft Tagging Implementation
        Instead of extracting dates as metadata, we wrap them with XML tags
        so the LLM can interpret temporal confidence during generation.

        Algorithm:
        1. Split content into paragraphs
        2. For each paragraph, scan for date patterns
        3. If found, wrap with: <EFFECTIVE_DATE confidence="X">DATE</EFFECTIVE_DATE>
        4. Avoid duplicate tagging (track already-tagged dates)

        Args:
            content: Original document content

        Returns:
            Content with <EFFECTIVE_DATE> tags injected
        """
        tagged_content = content
        tagged_dates = set()  # Avoid duplicate tagging

        # Process each date pattern (high to low confidence)
        for pattern, confidence in self.DATE_PATTERNS_WITH_CONTEXT:
            # Find all matches in the current content
            for match in re.finditer(pattern, tagged_content, re.IGNORECASE):
                date_str = match.group(1)

                # Normalize date
                normalized_date = self._normalize_date(date_str)

                # Skip if already tagged (avoid double-tagging)
                if normalized_date in tagged_dates:
                    continue

                # Create soft tag
                soft_tag = f'<EFFECTIVE_DATE confidence="{confidence}">{normalized_date}</EFFECTIVE_DATE>'

                # Replace the date with tagged version
                # Use word boundaries to avoid partial replacements
                tagged_content = re.sub(
                    rf"\b{re.escape(date_str)}\b", soft_tag, tagged_content, count=1
                )

                tagged_dates.add(normalized_date)

        return tagged_content

    def prepare_for_ingestion(self) -> List[Dict[str, Any]]:
        """
        Prepare documents for ingestion with temporal metadata.


        - Injects <EFFECTIVE_DATE> tags directly into content
        - sequence_index is the ONLY hard filter
        - effective_date in metadata is for display only (not used in retrieval)

        Returns:
            List of dictionaries with content and metadata:
            {
                "content": "Content with <EFFECTIVE_DATE>...</EFFECTIVE_DATE> tags",
                "metadata": {
                    "source": "Base.md",
                    "sequence_index": 1,
                    "doc_type": "base",
                    "date": "2023-01-01"  # Display only, not used for filtering
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

            # Inject soft tags into content
            tagged_content = self._inject_soft_tags(content)

            # Extract metadata (for display purposes)
            effective_date = self._extract_date(content)
            doc_type = self._infer_doc_type(content, filename)

            # Build result dictionary
            result = {
                "content": tagged_content,  # Now contains <EFFECTIVE_DATE> tags
                "metadata": {
                    "source": filename,
                    "sequence_index": idx,
                    "doc_type": doc_type,
                    "date": effective_date,  # Display only - not used for retrieval
                },
            }

            results.append(result)

        return results
