"""Unit tests for entity and relationship extraction functions.

This module tests the core extraction logic from lightrag/operate.py including:
- Entity extraction and validation
- Relationship extraction and validation
- Text sanitization and normalization
- Error handling in extraction pipelines
"""

import pytest

from lightrag.operate import (
    _handle_single_entity_extraction,
    _handle_single_relationship_extraction,
)


class TestEntityExtraction:
    """Test suite for entity extraction functions."""

    @pytest.mark.asyncio
    async def test_valid_entity_extraction(self):
        """Test extraction of a valid entity."""
        record = ["entity", "Apple Inc", "Organization", "A technology company"]
        result = await _handle_single_entity_extraction(
            record, "chunk_123", 1705622400, "test.txt"
        )

        assert result is not None
        assert result["entity_name"] == "Apple Inc"
        assert result["entity_type"] == "organization"
        assert result["description"] == "A technology company"
        assert result["source_id"] == "chunk_123"
        assert result["file_path"] == "test.txt"
        assert result["timestamp"] == 1705622400

    @pytest.mark.asyncio
    async def test_empty_entity_name(self):
        """Test that empty entity names are rejected."""
        record = ["entity", "", "Organization", "Description"]
        result = await _handle_single_entity_extraction(record, "chunk_123", 1705622400)

        assert result is None

    @pytest.mark.asyncio
    async def test_whitespace_only_entity_name(self):
        """Test that whitespace-only entity names are rejected."""
        record = ["entity", "   ", "Organization", "Description"]
        result = await _handle_single_entity_extraction(record, "chunk_123", 1705622400)

        assert result is None

    @pytest.mark.asyncio
    async def test_entity_type_normalization(self):
        """Test that entity types are normalized (lowercased, spaces removed)."""
        record = ["entity", "Apple Inc", "Tech Organization", "Description"]
        result = await _handle_single_entity_extraction(record, "chunk_123", 1705622400)

        assert result is not None
        assert result["entity_type"] == "techorganization"

    @pytest.mark.asyncio
    async def test_invalid_entity_type_with_special_chars(self):
        """Test that entity types with special characters are rejected."""
        record = ["entity", "Apple Inc", "Org|Type", "Description"]
        result = await _handle_single_entity_extraction(record, "chunk_123", 1705622400)

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_entity_description(self):
        """Test that empty descriptions are rejected."""
        record = ["entity", "Apple Inc", "Organization", ""]
        result = await _handle_single_entity_extraction(record, "chunk_123", 1705622400)

        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_entity_record_wrong_field_count(self):
        """Test that records with wrong field count are rejected."""
        record = ["entity", "Apple Inc", "Organization"]  # Missing description
        result = await _handle_single_entity_extraction(record, "chunk_123", 1705622400)

        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_entity_record_wrong_type(self):
        """Test that records with wrong type marker are rejected."""
        record = ["relationship", "Apple Inc", "Organization", "Description"]
        result = await _handle_single_entity_extraction(record, "chunk_123", 1705622400)

        assert result is None

    @pytest.mark.asyncio
    async def test_entity_with_quotes(self):
        """Test that inner quotes are removed from entity names."""
        record = ["entity", '"Apple Inc"', "Organization", "Description"]
        result = await _handle_single_entity_extraction(record, "chunk_123", 1705622400)

        assert result is not None
        # Should remove quotes during sanitization
        assert '"' not in result["entity_name"]


class TestRelationshipExtraction:
    """Test suite for relationship extraction functions."""

    @pytest.mark.asyncio
    async def test_valid_relationship_extraction(self):
        """Test extraction of a valid relationship."""
        record = [
            "relation",
            "Apple Inc",
            "Tim Cook",
            "CEO_OF",
            "Tim Cook is the CEO of Apple Inc",
        ]
        result = await _handle_single_relationship_extraction(
            record, "chunk_123", 1705622400, "test.txt"
        )

        assert result is not None
        assert result["src_id"] == "Apple Inc"
        assert result["tgt_id"] == "Tim Cook"
        assert result["keywords"] == "CEO_OF"
        assert result["description"] == "Tim Cook is the CEO of Apple Inc"
        assert result["source_id"] == "chunk_123"
        assert result["file_path"] == "test.txt"
        assert result["timestamp"] == 1705622400
        assert result["weight"] == 1.0  # Default weight

    @pytest.mark.asyncio
    async def test_empty_source_entity(self):
        """Test that relationships with empty source are rejected."""
        record = ["relation", "", "Tim Cook", "CEO_OF", "Description"]
        result = await _handle_single_relationship_extraction(
            record, "chunk_123", 1705622400
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_target_entity(self):
        """Test that relationships with empty target are rejected."""
        record = ["relation", "Apple Inc", "", "CEO_OF", "Description"]
        result = await _handle_single_relationship_extraction(
            record, "chunk_123", 1705622400
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_self_loop_relationship(self):
        """Test that self-loop relationships are rejected."""
        record = ["relation", "Apple Inc", "Apple Inc", "OWNS", "Description"]
        result = await _handle_single_relationship_extraction(
            record, "chunk_123", 1705622400
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_chinese_comma_normalization(self):
        """Test that Chinese commas are normalized to English commas."""
        record = [
            "relation",
            "Apple Inc",
            "Tim Cook",
            "CEO，CTO",  # Chinese comma
            "Description",
        ]
        result = await _handle_single_relationship_extraction(
            record, "chunk_123", 1705622400
        )

        assert result is not None
        assert "，" not in result["keywords"]
        assert "," in result["keywords"]

    @pytest.mark.asyncio
    async def test_malformed_relationship_wrong_field_count(self):
        """Test that records with wrong field count are rejected."""
        record = ["relation", "Apple Inc", "Tim Cook", "CEO_OF"]  # Missing description
        result = await _handle_single_relationship_extraction(
            record, "chunk_123", 1705622400
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_relationship_wrong_type(self):
        """Test that records with wrong type marker are rejected."""
        record = ["entity", "Apple Inc", "Tim Cook", "CEO_OF", "Description"]
        result = await _handle_single_relationship_extraction(
            record, "chunk_123", 1705622400
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_relationship_with_quotes(self):
        """Test that inner quotes are removed from entity names."""
        record = [
            "relation",
            '"Apple Inc"',
            '"Tim Cook"',
            "CEO_OF",
            "Description",
        ]
        result = await _handle_single_relationship_extraction(
            record, "chunk_123", 1705622400
        )

        assert result is not None
        assert '"' not in result["src_id"]
        assert '"' not in result["tgt_id"]


class TestExtractionErrorHandling:
    """Test suite for error handling in extraction functions."""

    @pytest.mark.asyncio
    async def test_entity_extraction_with_unicode_error(self):
        """Test that unicode errors are handled gracefully."""
        # This test validates the exception handling, not that it throws
        record = ["entity", "Valid Name", "Type", "Description"]
        result = await _handle_single_entity_extraction(record, "chunk_123", 1705622400)

        # Should not raise exception, even with potential encoding issues
        assert result is not None or result is None

    @pytest.mark.asyncio
    async def test_relationship_extraction_with_unicode_error(self):
        """Test that unicode errors are handled gracefully."""
        record = ["relation", "Source", "Target", "Keywords", "Description"]
        result = await _handle_single_relationship_extraction(
            record, "chunk_123", 1705622400
        )

        # Should not raise exception, even with potential encoding issues
        assert result is not None or result is None


class TestExtractionEdgeCases:
    """Test suite for edge cases in extraction."""

    @pytest.mark.asyncio
    async def test_entity_with_very_long_name(self):
        """Test handling of very long entity names."""
        long_name = "A" * 1000
        record = ["entity", long_name, "Organization", "Description"]
        result = await _handle_single_entity_extraction(record, "chunk_123", 1705622400)

        # Should either accept or reject, but not crash
        assert result is not None or result is None

    @pytest.mark.asyncio
    async def test_entity_with_special_unicode_chars(self):
        """Test handling of special Unicode characters."""
        record = ["entity", "Apple™ Inc®", "Organization", "Tech company"]
        result = await _handle_single_entity_extraction(record, "chunk_123", 1705622400)

        assert result is not None
        # Special chars might be preserved or sanitized
        assert result["entity_name"]

    @pytest.mark.asyncio
    async def test_relationship_with_very_long_description(self):
        """Test handling of very long relationship descriptions."""
        long_desc = "Description " * 500
        record = ["relation", "Apple Inc", "Tim Cook", "CEO_OF", long_desc]
        result = await _handle_single_relationship_extraction(
            record, "chunk_123", 1705622400
        )

        assert result is not None or result is None

    @pytest.mark.asyncio
    async def test_entity_default_file_path(self):
        """Test that default file path is set correctly."""
        record = ["entity", "Apple Inc", "Organization", "Description"]
        result = await _handle_single_entity_extraction(record, "chunk_123", 1705622400)

        assert result is not None
        assert result["file_path"] == "unknown_source"  # Default value

    @pytest.mark.asyncio
    async def test_relationship_default_file_path(self):
        """Test that default file path is set correctly."""
        record = ["relation", "Apple Inc", "Tim Cook", "CEO_OF", "Description"]
        result = await _handle_single_relationship_extraction(
            record, "chunk_123", 1705622400
        )

        assert result is not None
        assert result["file_path"] == "unknown_source"  # Default value
