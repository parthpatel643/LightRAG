"""
Tests for HierarchicalMarkdownYAMLChunker.

Tests cover:
- Header stack management (nesting, level changes)
- Global metadata extraction
- YAML stream parsing (valid, malformed, mixed)
- Context injection for both YAML and prose chunks
- Token counting and chunk sizing
- Environment variable configuration
- LightRAG integration via chunking_func
"""

import os
import tempfile
from typing import List

import pytest

from lightrag.hierarchical_chunker import (
    HierarchicalMarkdownYAMLChunker,
    create_hierarchical_chunking_func,
)


class DummyTokenizer:
    """Simple tokenizer for testing (1 char = 1 token)."""

    def encode(self, content: str) -> List[int]:
        """Encode text as list of character codes."""
        return [ord(ch) for ch in content]

    def decode(self, tokens: List[int]) -> str:
        """Decode tokens back to text."""
        return "".join(chr(token) for token in tokens)


class MockTokenizer:
    """Mock tokenizer with encode/decode interface."""

    def __init__(self, model_name="dummy"):
        self.model_name = model_name
        self._tokenizer = DummyTokenizer()

    def encode(self, content: str) -> List[int]:
        return self._tokenizer.encode(content)

    def decode(self, tokens: List[int]) -> str:
        return self._tokenizer.decode(tokens)


@pytest.fixture
def mock_tokenizer():
    """Provide mock tokenizer for tests."""
    return MockTokenizer()


@pytest.fixture
def sample_markdown_with_yaml():
    """Sample Markdown document with YAML streams."""
    return """Contract#: TEST-001
Vendor: Test Vendor Inc

# Section A

Introduction text for section A.

## Subsection A.1

Details about subsection A.1 with some content.

### Data Table

```yaml
Name: Item 1
Price: 100
---
Name: Item 2
Price: 200
---
Name: Item 3
Price: 300
```

## Subsection A.2

More prose content here.

# Section B

Final section with summary.
"""


@pytest.fixture
def malformed_yaml_markdown():
    """Markdown with malformed YAML to test error handling."""
    return """Contract#: TEST-002

# Test Section

```yaml
Valid: data
Key: value
---
Invalid YAML content [[[
This will fail parsing
---
Another Valid: record
Works: true
```

Prose after YAML.
"""


@pytest.mark.offline
def test_header_stack_management(mock_tokenizer):
    """Test that header stack correctly manages hierarchy."""
    content = """# Level 1

Content at level 1.

## Level 2

Content at level 2.

### Level 3

Content at level 3.

## Back to Level 2

More content at level 2.

# New Level 1

Final content at new level 1.
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        chunker = HierarchicalMarkdownYAMLChunker(tokenizer=mock_tokenizer)
        chunks = chunker.process(temp_path)

        # Should have prose chunks with correct hierarchies
        assert len(chunks) > 0

        # Check that hierarchies are properly nested
        hierarchies = [c.get("hierarchy", []) for c in chunks if c.get("hierarchy")]

        # Verify hierarchy structure exists
        assert any(hierarchies), "Should have chunks with hierarchy information"

        # Verify nesting depth changes correctly
        max_depth = max(len(h) for h in hierarchies)
        assert max_depth >= 2, "Should have nested hierarchies"

    finally:
        os.unlink(temp_path)


@pytest.mark.offline
def test_global_metadata_extraction(mock_tokenizer):
    """Test extraction of global metadata from document headers."""
    content = """Contract#: CW-2024-999
Vendor: ACME Corporation
Date: 2024-01-15
Region: North America

# Content

Some content here.
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        chunker = HierarchicalMarkdownYAMLChunker(tokenizer=mock_tokenizer)
        chunks = chunker.process(temp_path)

        # Check that contract ID appears in context
        assert len(chunks) > 0
        first_chunk_content = chunks[0]["content"]
        assert "CW-2024-999" in first_chunk_content

    finally:
        os.unlink(temp_path)


@pytest.mark.offline
def test_yaml_stream_parsing(mock_tokenizer, sample_markdown_with_yaml):
    """Test parsing of YAML streams with multiple records."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(sample_markdown_with_yaml)
        temp_path = f.name

    try:
        chunker = HierarchicalMarkdownYAMLChunker(tokenizer=mock_tokenizer)
        chunks = chunker.process(temp_path)

        # Should have YAML chunks (either as single block or individual rows)
        yaml_chunks = [
            c for c in chunks if c.get("type") in ["structured_row", "yaml_block"]
        ]
        assert len(yaml_chunks) >= 1, (
            f"Expected at least 1 YAML chunk, got {len(yaml_chunks)}"
        )

        # Verify content has YAML format
        for chunk in yaml_chunks:
            assert "---" in chunk["content"]
            assert "Context:" in chunk["content"]

    finally:
        os.unlink(temp_path)


@pytest.mark.offline
def test_malformed_yaml_handling(mock_tokenizer, malformed_yaml_markdown):
    """Test that malformed YAML segments are skipped without crashing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(malformed_yaml_markdown)
        temp_path = f.name

    try:
        chunker = HierarchicalMarkdownYAMLChunker(tokenizer=mock_tokenizer)
        chunks = chunker.process(temp_path)

        # Should still process YAML (either as block or individual records)
        yaml_chunks = [
            c for c in chunks if c.get("type") in ["structured_row", "yaml_block"]
        ]
        assert len(yaml_chunks) >= 1, "Should have parsed YAML content"

        # Should also have prose chunks
        prose_chunks = [c for c in chunks if c.get("type") == "prose"]
        assert len(prose_chunks) > 0, "Should have prose chunks"

    finally:
        os.unlink(temp_path)


@pytest.mark.offline
def test_context_injection(mock_tokenizer, sample_markdown_with_yaml):
    """Test that context is prepended to all chunks."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(sample_markdown_with_yaml)
        temp_path = f.name

    try:
        chunker = HierarchicalMarkdownYAMLChunker(tokenizer=mock_tokenizer)
        chunks = chunker.process(temp_path)

        # All chunks should have context
        for chunk in chunks:
            assert "Context:" in chunk["content"], (
                f"Chunk missing context: {chunk['content'][:100]}"
            )
            assert "TEST-001" in chunk["content"], (
                "Chunk should include contract ID from metadata"
            )

    finally:
        os.unlink(temp_path)


@pytest.mark.offline
def test_chunk_field_compliance(mock_tokenizer, sample_markdown_with_yaml):
    """Test that all chunks have required fields."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(sample_markdown_with_yaml)
        temp_path = f.name

    try:
        chunker = HierarchicalMarkdownYAMLChunker(tokenizer=mock_tokenizer)
        chunks = chunker.process(temp_path)

        required_fields = {"tokens", "content", "chunk_order_index"}

        for idx, chunk in enumerate(chunks):
            for field in required_fields:
                assert field in chunk, f"Chunk {idx} missing required field: {field}"

            # Verify types
            assert isinstance(chunk["tokens"], int), "tokens must be int"
            assert isinstance(chunk["content"], str), "content must be str"
            assert isinstance(chunk["chunk_order_index"], int), (
                "chunk_order_index must be int"
            )

            # Verify tokens > 0
            assert chunk["tokens"] > 0, "tokens must be positive"

        # Verify sequential chunk indices
        indices = [c["chunk_order_index"] for c in chunks]
        assert indices == list(range(len(chunks))), (
            "chunk_order_index should be sequential starting from 0"
        )

    finally:
        os.unlink(temp_path)


@pytest.mark.offline
def test_chunk_size_limits(mock_tokenizer):
    """Test that prose chunks respect chunk size limits."""
    # Create long prose content
    long_content = """# Test

""" + "\n\n".join([f"Paragraph {i} with some content." for i in range(100)])

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(long_content)
        temp_path = f.name

    try:
        # Use small chunk size
        chunker = HierarchicalMarkdownYAMLChunker(
            tokenizer=mock_tokenizer, chunk_size=200, chunk_overlap=20
        )
        chunks = chunker.process(temp_path)

        prose_chunks = [c for c in chunks if c.get("type") == "prose"]

        # Should create multiple prose chunks
        assert len(prose_chunks) > 1, "Long content should create multiple chunks"

        # Check that chunks don't grossly exceed limit (some tolerance for context)
        for chunk in prose_chunks:
            # Allow some tolerance (context string + formatting)
            assert chunk["tokens"] < 300, (
                f"Chunk exceeded size limit: {chunk['tokens']} tokens"
            )

    finally:
        os.unlink(temp_path)


@pytest.mark.offline
def test_environment_variable_configuration(mock_tokenizer, monkeypatch):
    """Test that chunker respects CHUNK_SIZE and CHUNK_OVERLAP_SIZE env vars."""
    # Set environment variables
    monkeypatch.setenv("CHUNK_SIZE", "150")
    monkeypatch.setenv("CHUNK_OVERLAP_SIZE", "30")

    content = """# Test

""" + "\n\n".join([f"Paragraph {i} content." for i in range(50)])

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        # Don't pass chunk_size/overlap explicitly
        chunker = HierarchicalMarkdownYAMLChunker(tokenizer=mock_tokenizer)

        # Verify it picked up env vars
        assert chunker.chunk_size == 150
        assert chunker.chunk_overlap == 30

        chunks = chunker.process(temp_path)

        # Verify chunks respect the env var limits
        prose_chunks = [c for c in chunks if c.get("type") == "prose"]
        for chunk in prose_chunks:
            # Allow tolerance for context
            assert chunk["tokens"] < 250

    finally:
        os.unlink(temp_path)


@pytest.mark.offline
def test_lightrag_integration_factory(mock_tokenizer, sample_markdown_with_yaml):
    """Test create_hierarchical_chunking_func factory for LightRAG integration."""
    # Create chunking function
    chunking_func = create_hierarchical_chunking_func(chunk_size=500, chunk_overlap=50)

    # Call with LightRAG-compatible signature
    chunks = chunking_func(
        tokenizer=mock_tokenizer,
        content=sample_markdown_with_yaml,
        delimiter=None,  # Ignored
        strict_delimiter=False,  # Ignored
        overlap=100,  # Overridden by factory param
        max_tokens=1000,  # Overridden by factory param
    )

    # Verify return format
    assert isinstance(chunks, list)
    assert len(chunks) > 0

    # Check required fields
    for chunk in chunks:
        assert "tokens" in chunk
        assert "content" in chunk
        assert "chunk_order_index" in chunk


@pytest.mark.offline
def test_empty_document(mock_tokenizer):
    """Test handling of empty document."""
    content = ""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        chunker = HierarchicalMarkdownYAMLChunker(tokenizer=mock_tokenizer)
        chunks = chunker.process(temp_path)

        # Empty document should return empty list
        assert chunks == []

    finally:
        os.unlink(temp_path)


@pytest.mark.offline
def test_only_headers_no_content(mock_tokenizer):
    """Test document with only headers and no content."""
    content = """# Header 1
## Header 2
### Header 3
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        chunker = HierarchicalMarkdownYAMLChunker(tokenizer=mock_tokenizer)
        chunks = chunker.process(temp_path)

        # Should not crash, may return empty or minimal chunks
        assert isinstance(chunks, list)

    finally:
        os.unlink(temp_path)


@pytest.mark.offline
def test_yaml_without_delimiter(mock_tokenizer):
    """Test YAML block with single record (no --- delimiter)."""
    content = """# Test

```yaml
SingleKey: SingleValue
AnotherKey: AnotherValue
```
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        chunker = HierarchicalMarkdownYAMLChunker(tokenizer=mock_tokenizer)
        chunks = chunker.process(temp_path)

        yaml_chunks = [
            c for c in chunks if c.get("type") in ["structured_row", "yaml_block"]
        ]

        # Should have exactly 1 YAML chunk
        assert len(yaml_chunks) == 1

    finally:
        os.unlink(temp_path)


@pytest.mark.offline
def test_mixed_content_ordering(mock_tokenizer):
    """Test that chunks maintain correct order for mixed content."""
    content = """# Section 1

First prose.

```yaml
Record: 1
```

Middle prose.

```yaml
Record: 2
```

Final prose.
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        chunker = HierarchicalMarkdownYAMLChunker(tokenizer=mock_tokenizer)
        chunks = chunker.process(temp_path)

        # Verify chunk_order_index is sequential
        for idx, chunk in enumerate(chunks):
            assert chunk["chunk_order_index"] == idx

        # Verify alternating pattern (prose, yaml, prose, yaml, prose)
        types = [c.get("type") for c in chunks]

        # Should have both types (yaml could be either structured_row or yaml_block)
        assert "prose" in types
        assert "structured_row" in types or "yaml_block" in types

    finally:
        os.unlink(temp_path)


@pytest.mark.offline
def test_hierarchy_in_yaml_chunks(mock_tokenizer):
    """Test that YAML chunks include correct hierarchy information."""
    content = """# Parent
## Child
### Grandchild

```yaml
Item: Test
Value: 123
```
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        chunker = HierarchicalMarkdownYAMLChunker(tokenizer=mock_tokenizer)
        chunks = chunker.process(temp_path)

        yaml_chunks = [
            c for c in chunks if c.get("type") in ["structured_row", "yaml_block"]
        ]
        assert len(yaml_chunks) > 0

        # Check hierarchy
        hierarchy = yaml_chunks[0].get("hierarchy")
        assert hierarchy is not None
        assert "Parent" in hierarchy
        assert "Child" in hierarchy
        assert "Grandchild" in hierarchy

    finally:
        os.unlink(temp_path)


@pytest.mark.offline
def test_source_field(mock_tokenizer, sample_markdown_with_yaml):
    """Test that chunks include source filename."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(sample_markdown_with_yaml)
        temp_path = f.name

    try:
        chunker = HierarchicalMarkdownYAMLChunker(tokenizer=mock_tokenizer)
        chunks = chunker.process(temp_path)

        # All chunks should have source field
        for chunk in chunks:
            assert "source" in chunk
            assert chunk["source"].endswith(".md")

    finally:
        os.unlink(temp_path)
