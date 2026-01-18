"""
HierarchicalMarkdownYAMLChunker - A specialized chunker for legal contracts.

This module provides robust chunking for Markdown documents containing
embedded YAML streams (data tables). It maintains hierarchical context
from headers and creates atomic chunks for each YAML record.

Key Features:
- Header stack management for hierarchical context
- Global metadata extraction from document headers
- YAML stream parsing with per-record error handling
- Context injection for both structured rows and prose
- LightRAG pipeline integration via chunking_func interface
"""

import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import yaml

from lightrag.utils import logger


@dataclass
class Chunk:
    """Represents a chunk of text with metadata."""

    tokens: int
    content: str
    chunk_order_index: int
    # Optional metadata fields
    source: Optional[str] = None
    hierarchy: Optional[List[str]] = None
    type: Optional[str] = None
    primary_key: Optional[str] = None


class HierarchicalMarkdownYAMLChunker:
    """
    Chunks Markdown documents with embedded YAML streams.

    This chunker:
    1. Maintains a hierarchical header stack
    2. Extracts global metadata from document headers
    3. Parses YAML blocks as individual records (atomic rows)
    4. Chunks prose text with context injection
    5. Respects CHUNK_SIZE and CHUNK_OVERLAP_SIZE from environment
    """

    def __init__(
        self,
        tokenizer=None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ):
        """
        Initialize the chunker.

        Args:
            tokenizer: Tokenizer instance for counting tokens (optional for standalone use)
            chunk_size: Maximum tokens per prose chunk (defaults to CHUNK_SIZE env var or 2000)
            chunk_overlap: Overlap tokens between prose chunks (defaults to CHUNK_OVERLAP_SIZE env var or 200)
        """
        self.tokenizer = tokenizer
        self.chunk_size = chunk_size or int(os.getenv("CHUNK_SIZE", "2000"))
        self.chunk_overlap = chunk_overlap or int(
            os.getenv("CHUNK_OVERLAP_SIZE", "200")
        )

        # Header regex pattern
        self.header_pattern = re.compile(r"^(#+)\s*(.*)")

        # Global metadata patterns (first 50 lines)
        self.metadata_pattern = re.compile(r"^([A-Za-z0-9#_\s-]+):\s*(.+)$")

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using tokenizer or fallback to word count."""
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        # Fallback: rough estimate (1 token ≈ 4 chars)
        return max(1, len(text) // 4)

    def _extract_global_metadata(self, lines: List[str]) -> Dict[str, str]:
        """
        Extract global metadata from first 50 lines.

        Looks for patterns like:
            Contract#: CW123
            Vendor: G2
            Date: 2024-01-15

        Args:
            lines: First 50 lines of the document

        Returns:
            Dictionary of metadata key-value pairs
        """
        metadata = {}
        for line in lines[:50]:
            match = self.metadata_pattern.match(line.strip())
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()
                metadata[key] = value
        return metadata

    def _update_header_stack(self, header_match, header_stack: List[str]) -> List[str]:
        """
        Update the header stack based on new header level.

        Logic:
        - If new level N <= current depth, pop until depth is N-1
        - Push new header text

        Args:
            header_match: Regex match object from header pattern
            header_stack: Current header stack

        Returns:
            Updated header stack
        """
        hashes = header_match.group(1)
        header_text = header_match.group(2).strip()
        new_level = len(hashes)

        # Pop stack to appropriate depth
        while len(header_stack) >= new_level:
            header_stack.pop()

        # Push new header
        header_stack.append(header_text)
        return header_stack

    def _parse_yaml_block(self, yaml_content: str) -> List[tuple]:
        """
        Parse YAML block content into individual records.

        Splits on '---' delimiter and attempts to parse each segment.
        Logs warnings for malformed segments but continues processing.

        Args:
            yaml_content: Raw YAML block content

        Returns:
            List of tuples: (parsed_dict, original_text)
        """
        records = []
        segments = yaml_content.split("---")

        for idx, segment in enumerate(segments):
            segment_stripped = segment.strip()
            if not segment_stripped:
                continue

            try:
                parsed = yaml.safe_load(segment_stripped)
                if isinstance(parsed, dict):
                    # Store both parsed dict and original text
                    records.append((parsed, segment_stripped))
                else:
                    logger.warning(
                        f"YAML segment {idx} did not parse to a dict: {type(parsed)}"
                    )
            except yaml.YAMLError as e:
                logger.warning(f'Failed to parse YAML segment {idx}: {e}")')
                continue

        return records

    def _format_context(
        self, global_metadata: Dict[str, str], header_stack: List[str]
    ) -> str:
        """
        Format hierarchical context string.

        Template: Context: {contract_id} > {header_path}

        Args:
            global_metadata: Document-level metadata
            header_stack: Current header hierarchy

        Returns:
            Formatted context string
        """
        contract_id = global_metadata.get(
            "Contract#", global_metadata.get("Contract", "Unknown")
        )
        hierarchy_path = " > ".join(header_stack) if header_stack else "Root"
        return f"Context: {contract_id} > {hierarchy_path}"

    def _create_yaml_chunk(
        self,
        row_data: tuple,
        context: str,
        header_stack: List[str],
        source: str,
        chunk_index: int,
    ) -> Chunk:
        """
        Create a chunk from a YAML row.

        Args:
            row_data: Tuple of (parsed_dict, original_yaml_text)
            context: Formatted context string
            header_stack: Current header hierarchy
            source: Source filename
            chunk_index: Sequential chunk number

        Returns:
            Chunk object with YAML content and metadata
        """
        row, original_yaml = row_data

        # Format content: context + original YAML (preserves order and formatting)
        content = f"{context}\n---\n{original_yaml}\n"

        # Extract primary key (first key in row)
        primary_key = next(iter(row.keys())) if row else None

        # Count tokens
        tokens = self._count_tokens(content)

        return Chunk(
            tokens=tokens,
            content=content,
            chunk_order_index=chunk_index,
            source=source,
            hierarchy=header_stack.copy(),
            type="structured_row",
            primary_key=primary_key,
        )

    def _chunk_prose_with_overlap(self, text: str, context: str) -> List[str]:
        """
        Chunk prose text with sliding window overlap.

        Splits on paragraph breaks (double newlines) and combines into
        chunks respecting token limits with overlap.

        Args:
            text: Prose text to chunk
            context: Context string to prepend

        Returns:
            List of prose chunk strings with context prepended
        """
        # Split into paragraphs
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        if not paragraphs:
            return []

        chunks = []
        current_chunk = []
        current_tokens = self._count_tokens(context + "\n")

        for para in paragraphs:
            para_tokens = self._count_tokens(para)

            # If adding this paragraph exceeds limit, finalize current chunk
            if current_chunk and current_tokens + para_tokens > self.chunk_size:
                chunk_text = context + "\n" + "\n\n".join(current_chunk)
                chunks.append(chunk_text)

                # Start new chunk with overlap
                # Keep last few paragraphs for overlap
                overlap_tokens = 0
                overlap_paras = []
                for p in reversed(current_chunk):
                    p_tokens = self._count_tokens(p)
                    if overlap_tokens + p_tokens <= self.chunk_overlap:
                        overlap_paras.insert(0, p)
                        overlap_tokens += p_tokens
                    else:
                        break

                current_chunk = overlap_paras
                current_tokens = self._count_tokens(
                    context + "\n" + "\n\n".join(current_chunk)
                )

            current_chunk.append(para)
            current_tokens += para_tokens + 2  # +2 for newlines

        # Add final chunk
        if current_chunk:
            chunk_text = context + "\n" + "\n\n".join(current_chunk)
            chunks.append(chunk_text)

        return chunks

    def _create_prose_chunks(
        self,
        prose_text: str,
        context: str,
        header_stack: List[str],
        source: str,
        start_index: int,
    ) -> List[Chunk]:
        """
        Create prose chunks with context injection.

        Args:
            prose_text: Prose text to chunk
            context: Formatted context string
            header_stack: Current header hierarchy
            source: Source filename
            start_index: Starting chunk index

        Returns:
            List of Chunk objects for prose segments
        """
        prose_chunks = self._chunk_prose_with_overlap(prose_text, context)

        chunks = []
        for idx, chunk_text in enumerate(prose_chunks):
            tokens = self._count_tokens(chunk_text)
            chunks.append(
                Chunk(
                    tokens=tokens,
                    content=chunk_text,
                    chunk_order_index=start_index + idx,
                    source=source,
                    hierarchy=header_stack.copy(),
                    type="prose",
                )
            )

        return chunks

    def process(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Process a Markdown file with YAML streams.

        This is the main entry point for standalone usage.

        Args:
            file_path: Path to Markdown file

        Returns:
            List of chunk dictionaries compatible with LightRAG
        """
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Extract global metadata from first 50 lines
        global_metadata = self._extract_global_metadata(lines)

        # Process document line by line
        chunks = []
        chunk_index = 0
        header_stack = []
        prose_buffer = []
        in_yaml_block = False
        yaml_buffer = []
        source = os.path.basename(file_path)

        for line in lines:
            # Check for YAML code fence
            if line.strip().startswith("```yaml"):
                # Save any accumulated prose before YAML block
                if prose_buffer:
                    prose_text = "".join(prose_buffer).strip()
                    if prose_text:
                        context = self._format_context(global_metadata, header_stack)
                        prose_chunks = self._create_prose_chunks(
                            prose_text, context, header_stack, source, chunk_index
                        )
                        chunks.extend(prose_chunks)
                        chunk_index += len(prose_chunks)
                    prose_buffer = []

                in_yaml_block = True
                yaml_buffer = []
                continue

            if in_yaml_block:
                if line.strip().startswith("```"):
                    # End of YAML block - process it
                    in_yaml_block = False
                    yaml_content = "".join(yaml_buffer)
                    context = self._format_context(global_metadata, header_stack)

                    # Check if entire YAML block fits within token limit
                    full_yaml_content = f"{context}\n---\n{yaml_content.strip()}\n"
                    full_yaml_tokens = self._count_tokens(full_yaml_content)

                    if full_yaml_tokens <= self.chunk_size:
                        # Keep entire YAML block as single chunk
                        chunk = Chunk(
                            tokens=full_yaml_tokens,
                            content=full_yaml_content,
                            chunk_order_index=chunk_index,
                            source=source,
                            hierarchy=header_stack.copy(),
                            type="yaml_block",
                        )
                        chunks.append(chunk)
                        chunk_index += 1
                    else:
                        # Split into individual records
                        records = self._parse_yaml_block(yaml_content)
                        for row_data in records:
                            chunk = self._create_yaml_chunk(
                                row_data, context, header_stack, source, chunk_index
                            )
                            chunks.append(chunk)
                            chunk_index += 1

                    yaml_buffer = []
                else:
                    yaml_buffer.append(line)
                continue

            # Check for headers
            header_match = self.header_pattern.match(line)
            if header_match:
                # Save any accumulated prose before header change
                if prose_buffer:
                    prose_text = "".join(prose_buffer).strip()
                    if prose_text:
                        context = self._format_context(global_metadata, header_stack)
                        prose_chunks = self._create_prose_chunks(
                            prose_text, context, header_stack, source, chunk_index
                        )
                        chunks.extend(prose_chunks)
                        chunk_index += len(prose_chunks)
                    prose_buffer = []

                # Update header stack
                header_stack = self._update_header_stack(header_match, header_stack)
                continue

            # Accumulate prose
            prose_buffer.append(line)

        # Process any remaining prose
        if prose_buffer:
            prose_text = "".join(prose_buffer).strip()
            if prose_text:
                context = self._format_context(global_metadata, header_stack)
                prose_chunks = self._create_prose_chunks(
                    prose_text, context, header_stack, source, chunk_index
                )
                chunks.extend(prose_chunks)

        # Convert to dict format for LightRAG compatibility
        return [self._chunk_to_dict(chunk) for chunk in chunks]

    def _chunk_to_dict(self, chunk: Chunk) -> Dict[str, Any]:
        """Convert Chunk object to dictionary format."""
        result = {
            "tokens": chunk.tokens,
            "content": chunk.content,
            "chunk_order_index": chunk.chunk_order_index,
        }

        # Add optional metadata if present
        if chunk.source:
            result["source"] = chunk.source
        if chunk.hierarchy:
            result["hierarchy"] = chunk.hierarchy
        if chunk.type:
            result["type"] = chunk.type
        if chunk.primary_key:
            result["primary_key"] = chunk.primary_key

        return result


def create_hierarchical_chunking_func(
    chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = None
) -> Callable:
    """
    Factory function to create a LightRAG-compatible chunking function.

    This creates a callable with the signature expected by LightRAG:
        Callable[[Tokenizer, str, Optional[str], bool, int, int], List[Dict[str, Any]]]

    Args:
        chunk_size: Override for CHUNK_SIZE (optional)
        chunk_overlap: Override for CHUNK_OVERLAP_SIZE (optional)

    Returns:
        Chunking function compatible with LightRAG pipeline

    Example:
        >>> from lightrag import LightRAG
        >>> from lightrag.hierarchical_chunker import create_hierarchical_chunking_func
        >>>
        >>> rag = LightRAG(
        ...     working_dir="./rag_storage",
        ...     chunking_func=create_hierarchical_chunking_func()
        ... )
    """

    def chunking_func(
        tokenizer,
        content: str,
        delimiter: Optional[str] = None,
        strict_delimiter: bool = False,
        overlap: int = 100,
        max_tokens: int = 1200,
    ) -> List[Dict[str, Any]]:
        """
        LightRAG-compatible chunking function.

        Note: delimiter and strict_delimiter parameters are ignored as this
        chunker uses internal YAML/header parsing logic.

        Args:
            tokenizer: Tokenizer instance from LightRAG
            content: Full document content as string
            delimiter: Ignored (uses YAML/header parsing)
            strict_delimiter: Ignored
            overlap: Token overlap (uses chunk_overlap if provided)
            max_tokens: Max tokens per chunk (uses chunk_size if provided)

        Returns:
            List of chunk dictionaries
        """
        # Use provided overrides or fall back to function parameters
        effective_chunk_size = chunk_size or max_tokens
        effective_overlap = chunk_overlap or overlap

        # Create chunker instance
        chunker = HierarchicalMarkdownYAMLChunker(
            tokenizer=tokenizer,
            chunk_size=effective_chunk_size,
            chunk_overlap=effective_overlap,
        )

        # Write content to temporary file for processing
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            temp_path = f.name

        try:
            chunks = chunker.process(temp_path)
            return chunks
        finally:
            # Clean up temp file
            import os

            if os.path.exists(temp_path):
                os.unlink(temp_path)

    return chunking_func


if __name__ == "__main__":
    """Demonstration of HierarchicalMarkdownYAMLChunker."""

    # Create sample Markdown file with YAML streams
    sample_content = """Contract#: CW-2024-001
Vendor: Global Services Inc
Effective Date: 2024-01-01

# Service Agreement

This agreement outlines the terms and conditions for facility management services.

## Exhibit A - Office Cleaning

Standard office cleaning procedures and rates.

### Daily Tasks

Routine cleaning activities performed on a daily basis including vacuuming, 
dusting, and trash removal. These tasks maintain the general cleanliness of 
the office environment.

### Weekly Tasks

Deep cleaning activities performed weekly including floor waxing, window 
cleaning, and sanitization of high-touch surfaces.

## Exhibit B - Specialized Services

### Janitorial Rates

The following rates apply for janitorial services:

```yaml
Staff type: Junior Janitor
Hourly rate: $15.00
Overtime rate: $22.50
Weekend rate: $18.00
---
Staff type: Senior Janitor
Hourly rate: $22.00
Overtime rate: $33.00
Weekend rate: $26.40
---
Staff type: Supervisor
Hourly rate: $35.00
Overtime rate: $52.50
Weekend rate: $42.00
```

### Provisioning Center Rates

Equipment and supply provisioning rates:

```yaml
Item: Vacuum Cleaner
Daily rate: $25.00
Weekly rate: $150.00
Monthly rate: $500.00
---
Item: Floor Buffer
Daily rate: $40.00
Weekly rate: $240.00
Monthly rate: $800.00
---
Item: Cleaning Supplies Kit
Daily rate: $10.00
Weekly rate: $60.00
Monthly rate: $200.00
```

## Terms and Conditions

All services are subject to the terms outlined in the master agreement. 
Payment terms are net 30 days from invoice date. Late payments will incur 
a 1.5% monthly interest charge.

### Termination Clause

Either party may terminate this agreement with 60 days written notice. Early 
termination fees may apply as specified in Section 12.3 of the master agreement.
"""

    # Write sample file
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(sample_content)
        sample_file = f.name

    try:
        # Create chunker instance
        print("=" * 80)
        print("HierarchicalMarkdownYAMLChunker Demonstration")
        print("=" * 80)
        print()

        chunker = HierarchicalMarkdownYAMLChunker()
        chunks = chunker.process(sample_file)

        print(f"Generated {len(chunks)} chunks from sample document")
        print()

        # Display first few chunks
        for idx, chunk in enumerate(chunks[:5], 1):
            print(f"Chunk {idx}:")
            print(f"  Type: {chunk.get('type', 'unknown')}")
            print(f"  Tokens: {chunk['tokens']}")
            print(f"  Hierarchy: {chunk.get('hierarchy', [])}")
            if chunk.get("primary_key"):
                print(f"  Primary Key: {chunk['primary_key']}")
            print("  Content (first 200 chars):")
            print(f"    {chunk['content'][:200]}...")
            print()

        if len(chunks) > 5:
            print(f"... and {len(chunks) - 5} more chunks")
            print()

        # Show some statistics
        yaml_chunks = [c for c in chunks if c.get("type") == "structured_row"]
        prose_chunks = [c for c in chunks if c.get("type") == "prose"]

        print("Statistics:")
        print(f"  Total chunks: {len(chunks)}")
        print(f"  YAML row chunks: {len(yaml_chunks)}")
        print(f"  Prose chunks: {len(prose_chunks)}")
        print(
            f"  Average tokens per chunk: {sum(c['tokens'] for c in chunks) / len(chunks):.1f}"
        )

    finally:
        # Clean up
        if os.path.exists(sample_file):
            os.unlink(sample_file)
