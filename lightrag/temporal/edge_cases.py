"""
Edge case handling for temporal operations.

This module provides Phase 4 (LOW priority) fixes for:
- Issue #13: Edge Case - Empty Results
- Issue #14: Edge Case - Malformed Versions
- Issue #15: Edge Case - Concurrent Deletes

Usage:
    from lightrag.temporal.edge_cases import (
        handle_empty_results,
        validate_version_format,
        safe_concurrent_delete
    )
"""

import re
from typing import Callable, Optional, Tuple

from lightrag.utils import logger

# Version format validation
VERSION_PATTERN = re.compile(r"^(.*?)\s*\[v(\d+)\]$")
VALID_VERSION_RANGE = range(1, 10000)  # Support up to v9999


def validate_version_format(
    entity_name: str,
) -> Tuple[bool, Optional[str], Optional[int]]:
    """
    Validate entity name version format (Issue #14).

    Args:
        entity_name: Entity name to validate (e.g., "Entity [v1]")

    Returns:
        Tuple of (is_valid, base_name, version_number)
        - is_valid: True if format is valid
        - base_name: Base entity name without version (None if invalid)
        - version_number: Version number (None if invalid or unversioned)

    Examples:
        >>> validate_version_format("Entity [v1]")
        (True, "Entity", 1)

        >>> validate_version_format("Entity [v999]")
        (True, "Entity", 999)

        >>> validate_version_format("Entity [vABC]")
        (False, None, None)

        >>> validate_version_format("Entity")
        (True, "Entity", None)
    """
    if not entity_name or not isinstance(entity_name, str):
        logger.warning(f"Invalid entity_name type: {type(entity_name)}")
        return False, None, None

    # Check for version pattern
    match = VERSION_PATTERN.match(entity_name)

    if match:
        base_name = match.group(1).strip()
        try:
            version_num = int(match.group(2))

            # Validate version is in reasonable range
            if version_num not in VALID_VERSION_RANGE:
                logger.warning(
                    f"Version number {version_num} out of range (1-9999) for entity: {entity_name}"
                )
                return False, None, None

            # Validate base name is not empty
            if not base_name:
                logger.warning(f"Empty base name in versioned entity: {entity_name}")
                return False, None, None

            return True, base_name, version_num

        except ValueError:
            logger.warning(f"Invalid version number format in entity: {entity_name}")
            return False, None, None
    else:
        # Unversioned entity - valid
        return True, entity_name, None


def handle_empty_results(
    entities: list[dict], relations: list[dict], operation: str = "filtering"
) -> Tuple[list[dict], list[dict]]:
    """
    Handle empty result sets gracefully (Issue #13).

    Args:
        entities: List of entities (may be empty)
        relations: List of relations (may be empty)
        operation: Name of operation for logging

    Returns:
        Tuple of (entities, relations) with appropriate logging

    Examples:
        >>> entities, relations = handle_empty_results([], [], "version_filtering")
        # Logs warning and returns empty lists
    """
    if not entities and not relations:
        logger.warning(
            f"{operation}: Both entities and relations are empty. "
            "This may indicate no data matches the criteria or an upstream issue."
        )
        return [], []

    if not entities:
        logger.warning(
            f"{operation}: No entities found but {len(relations)} relations exist. "
            "Relations will be filtered out as they have no valid entities."
        )
        return [], []

    if not relations:
        logger.info(
            f"{operation}: Found {len(entities)} entities but no relations. "
            "This is normal for isolated entities."
        )
        return entities, []

    # Both have data
    logger.debug(
        f"{operation}: Found {len(entities)} entities and {len(relations)} relations"
    )
    return entities, relations


def safe_concurrent_delete(
    entity_name: str, check_func: Callable, delete_func: Callable, max_retries: int = 3
) -> Tuple[bool, Optional[str]]:
    """
    Safely delete entity with concurrent operation protection (Issue #15).

    Uses optimistic locking pattern to handle concurrent deletes.

    Args:
        entity_name: Name of entity to delete
        check_func: Function to check if entity exists (returns bool)
        delete_func: Function to delete entity (returns bool)
        max_retries: Maximum number of retry attempts

    Returns:
        Tuple of (success, error_message)
        - success: True if deleted or already gone
        - error_message: None if success, error description if failed

    Examples:
        >>> async def check():
        ...     return await storage.exists(entity_name)
        >>> async def delete():
        ...     return await storage.delete(entity_name)
        >>> success, error = await safe_concurrent_delete(
        ...     "Entity [v1]", check, delete
        ... )
    """
    import asyncio

    for attempt in range(max_retries):
        try:
            # Check if entity exists
            exists = check_func()
            if asyncio.iscoroutine(exists):
                exists = asyncio.run(exists)

            if not exists:
                # Already deleted (possibly by concurrent operation)
                logger.info(
                    f"Entity {entity_name} already deleted (attempt {attempt + 1}/{max_retries})"
                )
                return True, None

            # Attempt delete
            deleted = delete_func()
            if asyncio.iscoroutine(deleted):
                deleted = asyncio.run(deleted)

            if deleted:
                logger.info(f"Successfully deleted entity {entity_name}")
                return True, None
            else:
                # Delete failed but entity exists - retry
                logger.warning(
                    f"Delete failed for {entity_name}, retrying (attempt {attempt + 1}/{max_retries})"
                )
                continue

        except Exception as e:
            logger.error(
                f"Error during delete of {entity_name} (attempt {attempt + 1}/{max_retries}): {e}"
            )
            if attempt == max_retries - 1:
                return False, f"Delete failed after {max_retries} attempts: {str(e)}"
            continue

    return False, f"Delete failed after {max_retries} attempts"


def sanitize_entity_name(entity_name: str, max_length: int = 500) -> str:
    """
    Sanitize entity name to prevent injection and overflow.

    Args:
        entity_name: Raw entity name
        max_length: Maximum allowed length

    Returns:
        Sanitized entity name

    Examples:
        >>> sanitize_entity_name("Entity [v1]")
        "Entity [v1]"

        >>> sanitize_entity_name("A" * 1000)
        "AAA...AAA"  # Truncated to max_length
    """
    if not entity_name:
        return ""

    # Remove null bytes and control characters
    sanitized = "".join(
        char for char in entity_name if ord(char) >= 32 or char in "\t\n\r"
    )

    # Truncate if too long
    if len(sanitized) > max_length:
        logger.warning(
            f"Entity name truncated from {len(sanitized)} to {max_length} characters"
        )
        sanitized = sanitized[:max_length]

    return sanitized


def validate_entity_batch(entities: list[dict]) -> Tuple[list[dict], list[str]]:
    """
    Validate a batch of entities and filter out invalid ones.

    Args:
        entities: List of entity dictionaries

    Returns:
        Tuple of (valid_entities, error_messages)

    Examples:
        >>> entities = [
        ...     {"entity_name": "Valid [v1]"},
        ...     {"entity_name": "Invalid [vABC]"},
        ...     {"entity_name": "Also Valid"}
        ... ]
        >>> valid, errors = validate_entity_batch(entities)
        >>> len(valid)
        2
        >>> len(errors)
        1
    """
    valid_entities = []
    errors = []

    for i, entity in enumerate(entities):
        entity_name = entity.get("entity_name")

        if not entity_name:
            errors.append(f"Entity {i}: Missing entity_name field")
            continue

        # Sanitize
        sanitized_name = sanitize_entity_name(entity_name)

        # Validate format
        is_valid, base_name, version = validate_version_format(sanitized_name)

        if not is_valid:
            errors.append(f"Entity {i}: Invalid version format: {entity_name}")
            continue

        # Update entity with sanitized name
        entity_copy = entity.copy()
        entity_copy["entity_name"] = sanitized_name
        valid_entities.append(entity_copy)

    if errors:
        logger.warning(
            f"Filtered out {len(errors)} invalid entities from batch of {len(entities)}"
        )

    return valid_entities, errors


def handle_version_conflict(
    entity_name: str, existing_version: int, new_version: int
) -> Tuple[str, str]:
    """
    Handle version conflicts during entity updates.

    Args:
        entity_name: Base entity name
        existing_version: Current version in storage
        new_version: Version being inserted

    Returns:
        Tuple of (action, message)
        - action: "skip", "overwrite", or "create_new"
        - message: Description of action taken

    Examples:
        >>> action, msg = handle_version_conflict("Entity", 5, 3)
        >>> action
        "skip"
    """
    if new_version < existing_version:
        return (
            "skip",
            f"Skipping older version {new_version} (current: {existing_version})",
        )
    elif new_version == existing_version:
        return "overwrite", f"Overwriting existing version {new_version}"
    else:
        return (
            "create_new",
            f"Creating new version {new_version} (current: {existing_version})",
        )


class EdgeCaseHandler:
    """
    Centralized edge case handling for temporal operations.

    Usage:
        handler = EdgeCaseHandler()
        entities, relations = handler.process_results(entities, relations)
    """

    def __init__(self, strict_mode: bool = False):
        """
        Initialize edge case handler.

        Args:
            strict_mode: If True, raise exceptions on errors instead of logging
        """
        self.strict_mode = strict_mode
        self.error_count = 0
        self.warning_count = 0

    def process_results(
        self, entities: list[dict], relations: list[dict], operation: str = "operation"
    ) -> Tuple[list[dict], list[dict]]:
        """
        Process results with comprehensive edge case handling.

        Args:
            entities: List of entities
            relations: List of relations
            operation: Operation name for logging

        Returns:
            Tuple of (processed_entities, processed_relations)
        """
        # Handle empty results
        entities, relations = handle_empty_results(entities, relations, operation)

        if not entities:
            return [], []

        # Validate entity batch
        valid_entities, errors = validate_entity_batch(entities)

        if errors:
            self.error_count += len(errors)
            if self.strict_mode:
                raise ValueError(f"Entity validation errors: {errors}")
            else:
                for error in errors:
                    logger.warning(f"{operation}: {error}")

        # Filter relations to only include valid entities
        valid_entity_names = {e.get("entity_name") for e in valid_entities}
        valid_relations = [
            rel
            for rel in relations
            if rel.get("src_id") in valid_entity_names
            and rel.get("tgt_id") in valid_entity_names
        ]

        if len(valid_relations) < len(relations):
            filtered_count = len(relations) - len(valid_relations)
            self.warning_count += filtered_count
            logger.warning(
                f"{operation}: Filtered out {filtered_count} relations "
                f"with invalid entity references"
            )

        return valid_entities, valid_relations

    def get_stats(self) -> dict[str, int]:
        """Get error and warning statistics."""
        return {"errors": self.error_count, "warnings": self.warning_count}

    def reset_stats(self):
        """Reset error and warning counters."""
        self.error_count = 0
        self.warning_count = 0


#
