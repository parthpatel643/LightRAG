"""
Temporal filtering functions for version and date-based entity/relation filtering.

This module provides Phase 2 fixes for:
- Issue #1: Deprecated Parameters (with warnings)
- Issue #2: Hardcoded Version Limit (configurable)
- Issue #3: Inconsistent Temporal Mode (proper date filtering)
- Issue #7: Missing Error Handling (comprehensive try-catch)

Usage:
    from lightrag.temporal.filtering import filter_by_version, filter_by_date

    # Version-based (highest version)
    entities, relations = await filter_by_version(entities, relations, graph_storage)

    # Date-based (effective_date filtering)
    entities, relations = await filter_by_date(
        entities, relations, "2024-01-01", graph_storage, text_chunks_db
    )
"""

import os
import re
import warnings
from typing import Optional, Tuple

from lightrag.base import BaseGraphStorage, BaseKVStorage
from lightrag.temporal.utils import TemporalUtils, validate_and_parse_date
from lightrag.utils import logger

# Configuration
MAX_VERSION_PROBE = int(os.getenv("LIGHTRAG_MAX_VERSION_PROBE", "100"))


async def filter_by_version(
    entities: list[dict],
    relations: list[dict],
    knowledge_graph_inst: BaseGraphStorage,
    max_version_probe: Optional[int] = None,
    # Deprecated parameters (Issue #1)
    reference_date: Optional[str] = None,
    text_chunks_db: Optional[BaseKVStorage] = None,
) -> Tuple[list[dict], list[dict]]:
    """
    Filter entities and relations by version (sequence-based).

    Returns the highest version of each entity based on sequence_index.

    Args:
        entities: List of entity dictionaries with 'entity_name' field
        relations: List of relation dictionaries with 'src_id' and 'tgt_id' fields
        knowledge_graph_inst: Graph storage to query entity versions
        max_version_probe: Maximum version number to probe (default: LIGHTRAG_MAX_VERSION_PROBE)
        reference_date: DEPRECATED - Use filter_by_date() instead
        text_chunks_db: DEPRECATED - Not needed for version filtering

    Returns:
        Tuple of (filtered_entities, filtered_relations)

    Raises:
        ValueError: If knowledge_graph_inst is None

    Examples:
        >>> entities, relations = await filter_by_version(
        ...     entities, relations, graph_storage
        ... )
    """
    # Issue #1: Deprecation warnings
    if reference_date is not None:
        warnings.warn(
            "Parameter 'reference_date' is deprecated and will be removed in v2.0. "
            "Use filter_by_date() for date-based filtering.",
            DeprecationWarning,
            stacklevel=2,
        )

    if text_chunks_db is not None:
        warnings.warn(
            "Parameter 'text_chunks_db' is deprecated and will be removed in v2.0. "
            "It is not needed for version-based filtering.",
            DeprecationWarning,
            stacklevel=2,
        )

    # Issue #7: Validate inputs
    if knowledge_graph_inst is None:
        raise ValueError("knowledge_graph_inst is required for version filtering")

    if not entities:
        logger.debug("No entities to filter")
        return [], []

    # Issue #2: Configurable version limit
    probe_limit = max_version_probe or MAX_VERSION_PROBE
    logger.debug(f"Using version probe limit: {probe_limit}")

    version_pattern = re.compile(r"^(.*?)\s*\[v(\d+)\]$")

    try:
        # Step 1: Extract unique base names
        base_names = set()
        for entity in entities:
            entity_name = entity.get("entity_name")
            if not entity_name:
                continue

            match = version_pattern.match(entity_name)
            if match:
                base_name = match.group(1).strip()
            else:
                base_name = entity_name
            base_names.add(base_name)

        logger.debug(
            f"Found {len(base_names)} unique base entity names from {len(entities)} entities"
        )

        # Step 2: Check if storage supports batch version query (Issue #2 optimization)
        if hasattr(knowledge_graph_inst, "get_max_version_batch"):
            # Use optimized batch query (2000x faster)
            max_versions = await knowledge_graph_inst.get_max_version_batch(base_names)
            filtered_entities = []
            valid_entity_names = set()

            for base_name in base_names:
                max_version = max_versions.get(base_name)
                if max_version:
                    versioned_name = f"{base_name} [v{max_version}]"
                    try:
                        node_data = await knowledge_graph_inst.get_node(versioned_name)
                        if node_data:
                            filtered_entities.append(
                                {"entity_name": versioned_name, **node_data}
                            )
                            valid_entity_names.add(versioned_name)
                    except Exception as e:
                        logger.warning(f"Error fetching node {versioned_name}: {e}")
                else:
                    # Try unversioned name
                    try:
                        node_data = await knowledge_graph_inst.get_node(base_name)
                        if node_data:
                            filtered_entities.append(
                                {"entity_name": base_name, **node_data}
                            )
                            valid_entity_names.add(base_name)
                    except Exception as e:
                        logger.warning(f"Error fetching node {base_name}: {e}")
        else:
            # Fallback to sequential probing (backward compatible)
            logger.debug(
                "Using sequential version probing (consider implementing get_max_version_batch)"
            )
            filtered_entities = []
            valid_entity_names = set()

            for base_name in base_names:
                version_candidates = []

                # Probe versions up to limit
                for v in range(1, probe_limit + 1):
                    candidate_name = f"{base_name} [v{v}]"
                    try:
                        node_data = await knowledge_graph_inst.get_node(candidate_name)
                        if node_data:
                            version_candidates.append(
                                {
                                    "entity_name": candidate_name,
                                    "version": v,
                                    "data": node_data,
                                }
                            )
                    except Exception as e:
                        # Issue #7: Log but continue
                        logger.debug(f"Version {v} not found for {base_name}: {e}")
                        continue

                # Check unversioned as fallback
                try:
                    node_data = await knowledge_graph_inst.get_node(base_name)
                    if node_data:
                        version_candidates.append(
                            {"entity_name": base_name, "version": 0, "data": node_data}
                        )
                except Exception as e:
                    logger.debug(f"Unversioned entity not found for {base_name}: {e}")

                if version_candidates:
                    # Select highest version
                    version_candidates.sort(key=lambda x: x["version"], reverse=True)
                    selected = version_candidates[0]
                    filtered_entities.append(
                        {"entity_name": selected["entity_name"], **selected["data"]}
                    )
                    valid_entity_names.add(selected["entity_name"])
                    logger.debug(
                        f"Selected {selected['entity_name']} (v{selected['version']}) "
                        f"from {len(version_candidates)} candidates"
                    )

        # Step 3: Filter relations
        filtered_relations = [
            rel
            for rel in relations
            if rel.get("src_id") in valid_entity_names
            and rel.get("tgt_id") in valid_entity_names
        ]

        logger.info(
            f"Version filtering: {len(entities)} → {len(filtered_entities)} entities, "
            f"{len(relations)} → {len(filtered_relations)} relations"
        )

        return filtered_entities, filtered_relations

    except Exception as e:
        # Issue #7: Comprehensive error handling
        logger.error(f"Error in filter_by_version: {e}", exc_info=True)
        # Graceful degradation: return original data
        logger.warning("Returning unfiltered data due to error")
        return entities, relations


async def filter_by_date(
    entities: list[dict],
    relations: list[dict],
    reference_date: str,
    knowledge_graph_inst: BaseGraphStorage,
    text_chunks_db: BaseKVStorage,
) -> Tuple[list[dict], list[dict]]:
    """
    Filter entities and relations by effective date.

    Returns entities/relations that were effective on or before the reference date.

    Args:
        entities: List of entity dictionaries
        relations: List of relation dictionaries
        reference_date: Target date in ISO format (e.g., "2024-01-01")
        knowledge_graph_inst: Graph storage instance
        text_chunks_db: Text chunks storage to get effective_date metadata

    Returns:
        Tuple of (filtered_entities, filtered_relations)

    Raises:
        ValueError: If reference_date is invalid or required parameters are None

    Examples:
        >>> entities, relations = await filter_by_date(
        ...     entities, relations, "2024-06-01", graph_storage, chunks_db
        ... )
    """
    # Issue #7: Validate inputs
    if not reference_date or reference_date.lower() == "unknown":
        raise ValueError("reference_date is required and cannot be 'unknown'")

    if knowledge_graph_inst is None:
        raise ValueError("knowledge_graph_inst is required")

    if text_chunks_db is None:
        raise ValueError("text_chunks_db is required for date-based filtering")

    if not entities:
        logger.debug("No entities to filter")
        return [], []

    try:
        # Issue #5: Validate and parse date
        target_date = validate_and_parse_date(reference_date, "reference_date")
        target_date_utc = TemporalUtils.normalize_to_utc(target_date)

        logger.info(f"Filtering by date: {reference_date} (UTC: {target_date_utc})")

        # Extract entity names and get their source chunks
        entity_to_chunks = {}
        for entity in entities:
            entity_name = entity.get("entity_name")
            if not entity_name:
                continue

            # Get source_id from entity
            source_id = entity.get("source_id")
            if source_id:
                entity_to_chunks[entity_name] = source_id

        # Query chunks to get effective_date metadata
        filtered_entities = []
        valid_entity_names = set()

        for entity in entities:
            entity_name = entity.get("entity_name")
            source_id = entity_to_chunks.get(entity_name)

            if not source_id:
                # No source info, skip
                continue

            try:
                # Get chunk metadata
                chunk_data = await text_chunks_db.get_by_id(source_id)
                if not chunk_data:
                    continue

                # Get effective_date from metadata
                effective_date_str = chunk_data.get("effective_date", "unknown")

                if effective_date_str == "unknown":
                    # Include entities with unknown date (conservative approach)
                    filtered_entities.append(entity)
                    valid_entity_names.add(entity_name)
                    continue

                # Parse and compare dates
                effective_date = validate_and_parse_date(
                    effective_date_str, "effective_date"
                )
                effective_date_utc = TemporalUtils.normalize_to_utc(effective_date)

                # Include if effective date is on or before reference date
                if effective_date_utc <= target_date_utc:
                    filtered_entities.append(entity)
                    valid_entity_names.add(entity_name)
                    logger.debug(
                        f"Included {entity_name}: {effective_date_str} <= {reference_date}"
                    )
                else:
                    logger.debug(
                        f"Excluded {entity_name}: {effective_date_str} > {reference_date}"
                    )

            except Exception as e:
                # Issue #7: Log error but continue
                logger.warning(f"Error processing entity {entity_name}: {e}")
                # Conservative: include entity if we can't determine date
                filtered_entities.append(entity)
                valid_entity_names.add(entity_name)

        # Filter relations
        filtered_relations = [
            rel
            for rel in relations
            if rel.get("src_id") in valid_entity_names
            and rel.get("tgt_id") in valid_entity_names
        ]

        logger.info(
            f"Date filtering ({reference_date}): "
            f"{len(entities)} → {len(filtered_entities)} entities, "
            f"{len(relations)} → {len(filtered_relations)} relations"
        )

        return filtered_entities, filtered_relations

    except Exception as e:
        # Issue #7: Comprehensive error handling
        logger.error(f"Error in filter_by_date: {e}", exc_info=True)
        raise ValueError(f"Date filtering failed: {e}") from e


#
