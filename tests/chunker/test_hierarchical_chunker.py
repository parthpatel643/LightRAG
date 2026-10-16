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


def _chunk_text(mock_tokenizer, content: str, **kwargs) -> List[dict]:
    func = create_hierarchical_chunking_func(**kwargs)
    return func(mock_tokenizer, content)


@pytest.mark.offline
def test_yaml_block_carries_preceding_clause_as_caption(mock_tokenizer):
    """A table introduced by a bold-numbered clause keeps that clause as caption.

    Contracts often use bold clause numbers instead of Markdown headers, so the
    header path is empty and the table chunk would otherwise lose any hint of
    what its rows describe.
    """
    content = """**1.2.2.5** In the event that the aircraft arrives ahead of schedule the Carrier shall be charged as shown below:

**1.2.2.6**

```yaml
---
Minutes: 0 -40
Percent of Turn Rate: 0%
---
Minutes: 41-120
Percent of Turn Rate: 25%
```

**1.2.2.7** In the event that the departure is delayed the Carrier shall be charged as follows:

```yaml
---
Minutes: 0 -45
Percent of Turn Rate: 0%
```
"""
    chunks = _chunk_text(mock_tokenizer, content)
    tables = [c for c in chunks if c.get("type") == "yaml_block"]
    assert len(tables) == 2

    early, delayed = tables
    assert (
        "Table caption: **1.2.2.5** In the event that the aircraft arrives ahead"
        in early["content"]
    )
    assert "**1.2.2.6**" in early["content"]
    assert "delayed" not in early["content"]
    assert "Minutes: 41-120" in early["content"]

    assert (
        "Table caption: **1.2.2.7** In the event that the departure is delayed"
        in delayed["content"]
    )
    assert "arrives ahead" not in delayed["content"]

    for chunk in tables:
        assert chunk["content"].startswith("Context: ")
        assert chunk["tokens"] == len(chunk["content"])


@pytest.mark.offline
def test_yaml_rows_carry_caption_when_split(mock_tokenizer):
    content = """Rates for additional services are listed below:

```yaml
Service: GPU
Charge: '70.00'
---
Service: Air Start Unit
Charge: '100.00'
```
"""
    chunks = _chunk_text(mock_tokenizer, content, chunk_size=80, chunk_overlap=10)
    rows = [c for c in chunks if c.get("type") == "structured_row"]
    assert len(rows) == 2
    for row in rows:
        assert (
            "Table caption: Rates for additional services are listed below:"
            in row["content"]
        )


@pytest.mark.offline
def test_yaml_block_without_preceding_prose_has_no_caption(mock_tokenizer):
    content = """# Rates

```yaml
Item: A
Price: 1
```
"""
    chunks = _chunk_text(mock_tokenizer, content)
    table = next(c for c in chunks if c.get("type") == "yaml_block")
    assert "Table caption" not in table["content"]
    assert table["content"].startswith("Context: Unknown > Rates\n---\n")


@pytest.mark.offline
def test_long_caption_is_trimmed_to_text_nearest_table(mock_tokenizer):
    long_para = "Intro " + "filler words " * 200 + "charged as shown below:"
    content = f"{long_para}\n\n```yaml\nItem: A\nPrice: 1\n```\n"
    chunks = _chunk_text(mock_tokenizer, content)
    table = next(c for c in chunks if c.get("type") == "yaml_block")
    caption_line = next(
        line
        for line in table["content"].splitlines()
        if line.startswith("Table caption: ")
    )
    assert caption_line.endswith("charged as shown below:")
    assert len(caption_line) <= len("Table caption: ") + 600


@pytest.mark.offline
def test_continued_table_inherits_previous_caption(mock_tokenizer):
    """Page-split tables keep the caption of the table they continue."""
    content = """**Pricing** - Per plane event bid for all services listed below:

```yaml
Aircraft Type: Narrowbody
Price/event: $ 10.00
```

---

<!-- Table continues from previous section -->
```yaml
Aircraft Type: Hourly Bill Rate
Service Description: Security Search Agent
Price/event: $ 20.50
```
"""
    chunks = _chunk_text(mock_tokenizer, content)
    tables = [c for c in chunks if c.get("type") == "yaml_block"]
    assert len(tables) == 2
    for table in tables:
        assert (
            "Table caption: **Pricing** - Per plane event bid for all services listed below:"
            in table["content"]
        )
    assert "Table continues" not in tables[1]["content"]


@pytest.mark.offline
def test_caption_is_not_inherited_across_headers(mock_tokenizer):
    content = """Turnaround rates are listed below:

```yaml
Item: A
Price: 1
```

# Other Section

```yaml
Item: B
Price: 2
```
"""
    chunks = _chunk_text(mock_tokenizer, content)
    tables = [c for c in chunks if c.get("type") == "yaml_block"]
    assert "Table caption: Turnaround rates" in tables[0]["content"]
    assert "Table caption" not in tables[1]["content"]


@pytest.mark.offline
def test_short_table_label_pulls_in_the_introducing_sentence(mock_tokenizer):
    """A bare label like "Prices for Turnarounds:" keeps the dated sentence above it."""
    content = """Unrelated earlier paragraph about invoicing that must not be included at all here.

Please find below the current handling charges and those that will apply as of January 01, 2019:

Prices for Turnarounds:

```yaml
Type/Version: B772
current handling charges in EUR: 2,408.85
new handling charges in EUR effective January 01, 2019: 2,432.94
```
"""
    chunks = _chunk_text(mock_tokenizer, content)
    table = next(c for c in chunks if c.get("type") == "yaml_block")
    assert (
        "Table caption: Please find below the current handling charges and those "
        "that will apply as of January 01, 2019: Prices for Turnarounds:"
    ) in table["content"]
    assert "invoicing" not in table["content"]


@pytest.mark.offline
def test_caption_ignores_image_summaries_and_html_tables(mock_tokenizer):
    content = """**2.1** All services not included in article 1 will be charged at the following rates:

<img_summary>
img_num: 2
description: A stylized letter logo with a maroon diagonal stroke.
</img_summary>

<table><thead><tr><th>Aircraft type</th></tr></thead><tbody></tbody></table>

```yaml
Service: GPU
Charge: '70.00'
```
"""
    chunks = _chunk_text(mock_tokenizer, content)
    table = next(c for c in chunks if c.get("type") == "yaml_block")
    assert (
        "Table caption: **2.1** All services not included in article 1 will be "
        "charged at the following rates:\n"
    ) in table["content"]


@pytest.mark.offline
def test_oversized_table_packs_rows_up_to_chunk_size(mock_tokenizer):
    """Rows of an oversized table are packed, not emitted one chunk per row.

    One-row chunks that repeat the same caption flood vector retrieval: MUC's
    57-row invoice-credit table crowded the actual turnaround price table out
    of the top results.
    """
    rows = "\n---\n".join(
        f"Station: S{i}\nAmount turnarounds: '{i}'\nRate: {i}.00" for i in range(6)
    )
    content = f"Single payout of the handling charges per turnaround:\n\n```yaml\n{rows}\n```\n"
    chunks = _chunk_text(mock_tokenizer, content, chunk_size=260, chunk_overlap=10)
    tables = [c for c in chunks if c.get("type") == "structured_row"]

    assert 1 < len(tables) < 6
    joined = "".join(c["content"] for c in tables)
    for i in range(6):
        assert joined.count(f"Station: S{i}\n") == 1
    for table in tables:
        assert table["tokens"] <= 260
        assert table["content"].count("Table caption:") == 1
        assert table["content"].startswith("Context: Unknown > Root\nTable caption: ")
    assert [c["chunk_order_index"] for c in chunks] == list(range(len(chunks)))
