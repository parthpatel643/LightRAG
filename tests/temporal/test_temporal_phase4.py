"""
Tests for Phase 4 (Low Priority) temporal logic fixes.

Tests cover:
- Issue #12: Internationalization (i18n)
- Issue #13: Empty Result Handling
- Issue #14: Malformed Version Handling
- Issue #15: Concurrent Delete Protection
"""

from unittest.mock import Mock

from lightrag.temporal.edge_cases import (
    handle_empty_results,
    safe_concurrent_delete,
    sanitize_entity_name,
    validate_entity_batch,
    validate_version_format,
)
from lightrag.temporal.i18n import (
    I18nError,
    I18nWarning,
    add_language,
    get_language,
    get_message,
    get_supported_languages,
    set_language,
)

# ============================================================================
# Issue #12: Internationalization Tests
# ============================================================================


class TestInternationalization:
    """Test i18n support for temporal operations."""

    def test_default_language_english(self):
        """Test default language is English."""
        # Reset to default
        set_language("en")
        assert get_language() == "en"

    def test_set_supported_language(self):
        """Test setting supported languages."""
        assert set_language("es") is True
        assert get_language() == "es"

        assert set_language("fr") is True
        assert get_language() == "fr"

        assert set_language("de") is True
        assert get_language() == "de"

        assert set_language("zh") is True
        assert get_language() == "zh"

        # Reset
        set_language("en")

    def test_set_unsupported_language_fallback(self):
        """Test unsupported language falls back to English."""
        result = set_language("invalid_lang")
        assert result is False
        assert get_language() == "en"

    def test_get_supported_languages(self):
        """Test getting list of supported languages."""
        languages = get_supported_languages()
        assert "en" in languages
        assert "es" in languages
        assert "fr" in languages
        assert "de" in languages
        assert "zh" in languages

    def test_get_message_english(self):
        """Test getting English messages."""
        set_language("en")

        msg = get_message("error.invalid_date", date="2024-02-30")
        assert "Invalid date: 2024-02-30" == msg

        msg = get_message("warning.future_date", date="2025-01-01")
        assert "Date 2025-01-01 is in the future" == msg

    def test_get_message_spanish(self):
        """Test getting Spanish messages."""
        set_language("es")

        msg = get_message("error.invalid_date", date="2024-02-30")
        assert "Fecha inválida: 2024-02-30" == msg

        msg = get_message("warning.future_date", date="2025-01-01")
        assert "La fecha 2025-01-01 está en el futuro" == msg

        # Reset
        set_language("en")

    def test_get_message_french(self):
        """Test getting French messages."""
        set_language("fr")

        msg = get_message("error.invalid_date", date="2024-02-30")
        assert "Date invalide: 2024-02-30" == msg

        # Reset
        set_language("en")

    def test_get_message_german(self):
        """Test getting German messages."""
        set_language("de")

        msg = get_message("error.invalid_date", date="2024-02-30")
        assert "Ungültiges Datum: 2024-02-30" == msg

        # Reset
        set_language("en")

    def test_get_message_chinese(self):
        """Test getting Chinese messages."""
        set_language("zh")

        msg = get_message("error.invalid_date", date="2024-02-30")
        assert "无效日期: 2024-02-30" == msg

        # Reset
        set_language("en")

    def test_get_message_missing_key(self):
        """Test getting message with missing key."""
        msg = get_message("nonexistent.key")
        assert "[Missing message: nonexistent.key]" in msg

    def test_get_message_missing_parameter(self):
        """Test getting message with missing parameter."""
        msg = get_message("error.invalid_date")  # Missing 'date' parameter
        assert "[Missing parameter:" in msg

    def test_add_custom_language(self):
        """Test adding custom language."""
        add_language(
            "ja",
            {
                "error.invalid_date": "無効な日付: {date}",
                "warning.future_date": "日付 {date} は未来です",
            },
        )

        set_language("ja")
        msg = get_message("error.invalid_date", date="2024-02-30")
        assert "無効な日付: 2024-02-30" == msg

        # Reset
        set_language("en")

    def test_i18n_error(self):
        """Test I18nError exception."""
        set_language("en")

        try:
            raise I18nError("error.invalid_date", date="2024-02-30")
        except I18nError as e:
            assert "Invalid date: 2024-02-30" in str(e)
            assert e.message_key == "error.invalid_date"
            assert e.params == {"date": "2024-02-30"}

    def test_i18n_warning(self):
        """Test I18nWarning."""
        set_language("en")

        warning = I18nWarning("warning.future_date", date="2025-01-01")
        assert "Date 2025-01-01 is in the future" in str(warning)
        assert warning.message_key == "warning.future_date"
        assert warning.params == {"date": "2025-01-01"}


# ============================================================================
# Issue #13: Empty Result Handling Tests
# ============================================================================


class TestEmptyResultHandling:
    """Test empty result handling."""

    def test_handle_both_empty(self):
        """Test handling when both entities and relations are empty."""
        entities, relations = handle_empty_results([], [], "query")
        assert entities == []
        assert relations == []

    def test_handle_empty_entities_with_relations(self):
        """Test handling when entities empty but relations exist."""
        entities, relations = handle_empty_results(
            [], [{"src": "A", "tgt": "B"}], "query"
        )
        # Should filter out relations when no entities
        assert entities == []
        assert relations == []

    def test_handle_entities_without_relations(self):
        """Test handling when entities exist but no relations."""
        test_entities = [{"name": "Entity1"}]
        entities, relations = handle_empty_results(test_entities, [], "query")
        assert entities == test_entities
        assert relations == []

    def test_handle_both_populated(self):
        """Test handling when both entities and relations exist."""
        test_entities = [{"name": "Entity1"}]
        test_relations = [{"src": "A", "tgt": "B"}]

        entities, relations = handle_empty_results(
            test_entities, test_relations, "query"
        )
        assert entities == test_entities
        assert relations == test_relations


# ============================================================================
# Issue #14: Malformed Version Handling Tests
# ============================================================================


class TestMalformedVersionHandling:
    """Test malformed version handling."""

    def test_valid_version_format(self):
        """Test valid version format."""
        is_valid, base_name, version = validate_version_format("Entity [v1]")
        assert is_valid is True
        assert base_name == "Entity"
        assert version == 1

    def test_valid_version_multi_digit(self):
        """Test valid version with multiple digits."""
        is_valid, base_name, version = validate_version_format("Entity [v999]")
        assert is_valid is True
        assert base_name == "Entity"
        assert version == 999

    def test_valid_version_with_spaces(self):
        """Test valid version with spaces."""
        is_valid, base_name, version = validate_version_format("My Entity [v5]")
        assert is_valid is True
        assert base_name == "My Entity"
        assert version == 5

    def test_unversioned_entity(self):
        """Test entity without version."""
        is_valid, base_name, version = validate_version_format("Entity")
        assert is_valid is True
        assert base_name == "Entity"
        assert version is None

    def test_invalid_version_non_numeric(self):
        """Test invalid version with non-numeric value."""
        is_valid, base_name, version = validate_version_format("Entity [vABC]")
        assert is_valid is False
        assert base_name is None
        assert version is None

    def test_invalid_version_out_of_range(self):
        """Test invalid version out of range."""
        is_valid, base_name, version = validate_version_format("Entity [v99999]")
        assert is_valid is False
        assert base_name is None
        assert version is None

    def test_invalid_empty_base_name(self):
        """Test invalid empty base name."""
        is_valid, base_name, version = validate_version_format("[v1]")
        assert is_valid is False
        assert base_name is None
        assert version is None

    def test_invalid_empty_string(self):
        """Test invalid empty string."""
        is_valid, base_name, version = validate_version_format("")
        assert is_valid is False
        assert base_name is None
        assert version is None


# ============================================================================
# Issue #15: Concurrent Delete Protection Tests
# ============================================================================


class TestConcurrentDeleteProtection:
    """Test concurrent delete protection."""

    def test_successful_delete(self):
        """Test successful delete operation."""
        # Mock functions
        check_func = Mock(return_value=True)
        delete_func = Mock(return_value=True)

        success, error = safe_concurrent_delete("entity_123", check_func, delete_func)

        assert success is True
        assert error is None
        check_func.assert_called_once()
        delete_func.assert_called_once()

    def test_entity_already_deleted(self):
        """Test delete when entity already deleted."""
        check_func = Mock(return_value=False)
        delete_func = Mock()

        success, error = safe_concurrent_delete("entity_123", check_func, delete_func)

        assert success is True  # Already deleted is considered success
        assert error is None
        check_func.assert_called_once()
        delete_func.assert_not_called()

    def test_delete_failure_with_retry(self):
        """Test delete failure with retry."""
        # First check succeeds, delete fails, second check shows already deleted
        check_func = Mock(side_effect=[True, False])
        delete_func = Mock(side_effect=Exception("Concurrent modification"))

        success, error = safe_concurrent_delete(
            "entity_123", check_func, delete_func, max_retries=2
        )

        # Should succeed on retry when entity is gone
        assert success is True
        assert error is None
        assert check_func.call_count == 2
        assert delete_func.call_count == 1

    def test_delete_failure_max_retries(self):
        """Test delete failure after max retries."""
        check_func = Mock(return_value=True)
        delete_func = Mock(side_effect=Exception("Delete failed"))

        success, error = safe_concurrent_delete(
            "entity_123", check_func, delete_func, max_retries=3
        )

        assert success is False
        assert error is not None
        assert "3 attempts" in error
        assert check_func.call_count == 3
        assert delete_func.call_count == 3


# ============================================================================
# Additional Edge Case Tests
# ============================================================================


class TestAdditionalEdgeCases:
    """Test additional edge case utilities."""

    def test_sanitize_entity_name_normal(self):
        """Test sanitizing normal entity name."""
        result = sanitize_entity_name("Entity [v1]")
        assert result == "Entity [v1]"

    def test_sanitize_entity_name_with_control_chars(self):
        """Test sanitizing entity name with control characters."""
        result = sanitize_entity_name("Entity\x00[v1]\x01")
        assert "\x00" not in result
        assert "\x01" not in result
        assert "Entity" in result

    def test_sanitize_entity_name_too_long(self):
        """Test sanitizing entity name that's too long."""
        long_name = "A" * 1000
        result = sanitize_entity_name(long_name, max_length=500)
        assert len(result) == 500

    def test_sanitize_entity_name_empty(self):
        """Test sanitizing empty entity name."""
        result = sanitize_entity_name("")
        assert result == ""

    def test_validate_entity_batch_all_valid(self):
        """Test validating batch of all valid entities."""
        entities = [
            {"name": "Entity [v1]"},
            {"name": "Entity [v2]"},
        ]
        valid, errors = validate_entity_batch(entities)
        assert len(valid) == 2
        assert len(errors) == 0

    def test_validate_entity_batch_mixed(self):
        """Test validating batch with mixed valid/invalid entities."""
        entities = [
            {"name": "Entity [v1]"},
            {"name": "Entity [vABC]"},  # Invalid version
            {"name": "Entity [v2]"},
        ]
        valid, errors = validate_entity_batch(entities)
        assert len(valid) == 2
        assert len(errors) == 1


# ============================================================================
# Integration Tests
# ============================================================================


class TestPhase4Integration:
    """Integration tests for Phase 4 fixes."""

    def test_i18n_with_edge_cases(self):
        """Test i18n messages with edge case handling."""
        set_language("en")

        # Test with empty results
        entities, relations = handle_empty_results([], [], "query")
        msg = get_message("warning.empty_results", operation="query")
        assert "No results found" in msg

        # Test with invalid version
        is_valid, _, _ = validate_version_format("Entity [vABC]")
        if not is_valid:
            msg = get_message("error.invalid_version", version="[vABC]")
            assert "Invalid version format" in msg

    def test_concurrent_delete_with_i18n_errors(self):
        """Test concurrent delete with i18n error messages."""
        set_language("en")

        check_func = Mock(return_value=False)
        delete_func = Mock()

        success, error = safe_concurrent_delete("entity_123", check_func, delete_func)

        # Already deleted is success
        assert success is True
        assert error is None

        # Reset
        set_language("en")

    def test_version_validation_with_sanitization(self):
        """Test version validation combined with sanitization."""
        # Sanitize first, then validate
        entity_name = "Entity\x00[v1]"
        sanitized = sanitize_entity_name(entity_name)
        is_valid, base_name, version = validate_version_format(sanitized)

        assert is_valid is True
        assert base_name == "Entity"
        assert version == 1


#
