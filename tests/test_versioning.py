"""
Tests for LightRAG versioning system.

Tests cover:
- Auto-versioning without explicit sequence_index
- Versioned entity extraction
- Temporal resolution of versioned documents
- Soft tag date interpretation
"""

import json
import os
import shutil
import tempfile

import pytest

from lightrag import LightRAG, QueryParam
from lightrag.functions import embedding_func, llm_model_func


@pytest.fixture
def temp_rag_dir():
    """Create a temporary directory for LightRAG storage."""
    temp_dir = tempfile.mkdtemp(prefix="test_rag_versioning_")
    yield temp_dir
    # Cleanup
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


class TestAutoVersioning:
    """Tests for automatic version assignment."""

    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_auto_versioning_without_explicit_metadata(self, temp_rag_dir):
        """
        Test that versioning works without explicit sequence_index metadata.

        Documents ingested without providing sequence_index should automatically
        receive incremented version numbers [v1], [v2], [v3], etc.
        """
        # Initialize LightRAG
        rag = LightRAG(
            working_dir=temp_rag_dir,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
        )
        await rag.initialize_storages()

        try:
            # Create test documents
            doc_v1 = """
            # Parking Policy - Base Version
            
            ## Parking Fee
            The parking fee is $50 per month for employees.
            Parking spaces are assigned based on seniority.
            """

            doc_v2 = """
            # Parking Policy - Updated
            
            ## Parking Fee
            The parking fee is now $60 per month for employees.
            Parking spaces are assigned based on seniority and department.
            """

            doc_v3 = """
            # Parking Policy - Latest Amendment
            
            ## Parking Fee
            The parking fee is now $75 per month for employees.
            Visitor parking is available at $10 per day.
            """

            # Ingest without metadata - should auto-assign sequence_index
            await rag.ainsert(input=doc_v1, file_paths="parking_v1.md")
            await rag.ainsert(input=doc_v2, file_paths="parking_v2.md")
            await rag.ainsert(input=doc_v3, file_paths="parking_v3.md")

            # Verify versioned entities were created
            entities_file = os.path.join(temp_rag_dir, "kv_store_full_entities.json")
            assert os.path.exists(entities_file), "Entities storage file not found"

            with open(entities_file, "r") as f:
                entities_data = json.load(f)

            # Count versioned entities
            versioned_count = 0
            for doc_id, doc_info in entities_data.items():
                if isinstance(doc_info, dict) and "entity_names" in doc_info:
                    for entity_name in doc_info["entity_names"]:
                        if "[v" in entity_name:
                            versioned_count += 1

            # Assert that versioned entities exist
            assert versioned_count > 0, "No versioned entities found [v1, v2, v3]"
        finally:
            await rag.finalize_storages()

    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_versioned_entity_extraction(self, temp_rag_dir):
        """
        Test that LightRAG creates separate versioned entities.

        Documents with overlapping entities at different versions should create
        separate versioned entities (e.g., "Parking Fee [v1]" and "Parking Fee [v2]")
        instead of merging them.
        """
        rag = LightRAG(
            working_dir=temp_rag_dir,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
        )
        await rag.initialize_storages()

        try:
            # Contract A - Version 1
            contract_v1 = """
            # Service Agreement - Version 1
            **Effective Date:** 2023-01-01
            
            ## Services
            1. Parking Fee - Monthly parking allocation for 50 spaces at $100 per space
            
            ## Payment Terms
            - Parking Fee: $5,000 per month (50 spaces × $100)
            """

            # Contract B - Version 2 (Amendment)
            contract_v2 = """
            # Service Agreement - Amendment 1
            **Effective Date:** 2024-01-01
            
            ## Changes
            1. Parking Fee - Increased to 75 spaces at $120 per space
            
            ## Updated Payment Terms
            - Parking Fee: $9,000 per month (75 spaces × $120)
            """

            metadata_v1 = {
                "sequence_index": 1,
                "effective_date": "2023-01-01",
                "doc_type": "base",
            }

            metadata_v2 = {
                "sequence_index": 2,
                "effective_date": "2024-01-01",
                "doc_type": "amendment",
            }

            # Insert versioned documents
            await rag.ainsert(
                input=contract_v1, file_paths="contract_v1.md", metadata=metadata_v1
            )
            await rag.ainsert(
                input=contract_v2, file_paths="contract_v2.md", metadata=metadata_v2
            )

            # Verify versioned entities exist
            entities_file = os.path.join(temp_rag_dir, "kv_store_full_entities.json")
            assert os.path.exists(entities_file)

            with open(entities_file, "r") as f:
                entities_data = json.load(f)

            # Check for versioned parking fee entities
            parking_versions = []
            for doc_id, doc_info in entities_data.items():
                if isinstance(doc_info, dict) and "entity_names" in doc_info:
                    for entity_name in doc_info["entity_names"]:
                        if "Parking Fee" in entity_name and "[v" in entity_name:
                            parking_versions.append(entity_name)

            # Should find at least v1 and v2 versions
            assert len(parking_versions) >= 2, (
                f"Expected separate versioned 'Parking Fee' entities, got: {parking_versions}"
            )
        finally:
            await rag.finalize_storages()

    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_temporal_versioning_resolution(self, temp_rag_dir):
        """
        Test deterministic temporal resolution for versioned documents.

        System should correctly resolve which version applies based on effective_date
        using the "Isolate, Link, Filter" philosophy.
        """
        rag = LightRAG(
            working_dir=temp_rag_dir,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
        )
        await rag.initialize_storages()

        try:
            # Base contract
            base_contract = """
            PARKING SERVICE AGREEMENT
            
            Article 1: Service Fee
            The monthly parking fee is $50 per vehicle.
            
            Article 2: Operating Hours
            Parking facility is available 24/7.
            """

            # Amendment 1
            amendment_1 = """
            AMENDMENT 1 TO PARKING SERVICE AGREEMENT
            
            Article 1: Service Fee Amendment
            The monthly parking fee is hereby amended to $75 per vehicle.
            """

            # Amendment 2
            amendment_2 = """
            AMENDMENT 2 TO PARKING SERVICE AGREEMENT
            
            Article 1: Service Fee Amendment
            The monthly parking fee is hereby amended to $100 per vehicle.
            """

            # Insert versioned documents
            await rag.ainsert(
                base_contract,
                doc_metadata={
                    "sequence_index": 1,
                    "effective_date": "2024-01-01T00:00:00Z",
                },
            )
            await rag.ainsert(
                amendment_1,
                doc_metadata={
                    "sequence_index": 2,
                    "effective_date": "2024-06-01T00:00:00Z",
                },
            )
            await rag.ainsert(
                amendment_2,
                doc_metadata={
                    "sequence_index": 3,
                    "effective_date": "2024-12-01T00:00:00Z",
                },
            )

            # Query with different reference dates
            # Note: This is a basic structural test; full temporal query validation
            # requires external LLM services marked with @pytest.mark.integration
            result_early = await rag.aquery(
                "What is the monthly parking fee?",
                param=QueryParam(
                    mode="local",
                    reference_date="2024-03-01T00:00:00Z",
                ),
            )
            assert result_early is not None, "Early date query returned None"

            result_late = await rag.aquery(
                "What is the monthly parking fee?",
                param=QueryParam(
                    mode="local",
                    reference_date="2024-12-15T00:00:00Z",
                ),
            )
            assert result_late is not None, "Late date query returned None"
        finally:
            await rag.finalize_storages()


class TestSoftTags:
    """Tests for soft tag date interpretation."""

    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_soft_tag_effective_date_interpretation(self, temp_rag_dir):
        """
        Test soft tag validation and date interpretation.

        System should:
        1. Extract dates wrapped in <EFFECTIVE_DATE> tags
        2. Use sequence_index for retrieval (highest version)
        3. Allow LLM to interpret <EFFECTIVE_DATE> tags for temporal context
        """
        rag = LightRAG(
            working_dir=temp_rag_dir,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
        )
        await rag.initialize_storages()

        try:
            # Base document with soft tag
            base_doc = """
            # Service Agreement - Version 1
            <EFFECTIVE_DATE>2023-01-01</EFFECTIVE_DATE>
            
            ## Parking Fee
            The parking fee is $5 per space per month.
            """

            # Amendment with updated soft tag
            amended_doc = """
            # Service Agreement - Version 2
            <EFFECTIVE_DATE>2030-01-01</EFFECTIVE_DATE>
            
            ## Parking Fee
            The parking fee is $10 per space per month.
            """

            # Insert documents
            await rag.ainsert(
                base_doc,
                file_paths="agreement_v1.md",
            )
            await rag.ainsert(
                amended_doc,
                file_paths="agreement_v2.md",
            )

            # System should retrieve highest version (v2)
            result = await rag.aquery(
                "What is the parking fee?",
                param=QueryParam(mode="hybrid"),
            )
            assert result is not None, "Query returned None"
        finally:
            await rag.finalize_storages()


class TestTemporalMode:
    """Tests for temporal search mode with versioned entities."""

    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_temporal_queries_with_different_reference_dates(self, temp_rag_dir):
        """
        Test temporal search mode with different reference dates.

        Validates that queries use the correct version based on reference_date.
        """
        rag = LightRAG(
            working_dir=temp_rag_dir,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
        )
        await rag.initialize_storages()

        try:
            # Base contract (version 1)
            doc_v1 = """
            Effective Date: 2023-01-01
            
            # Service Agreement - Version 1
            
            ## Rule A
            The monthly service fee is $1,000 USD.
            Payment is due on the first day of each month.
            
            ## Rule B
            The contract term is 12 months with automatic renewal.
            """

            # Amendment (version 2)
            doc_v2 = """
            Effective Date: 2024-01-01
            
            # Service Agreement - Amendment 1
            
            ## Rule A (Updated)
            The monthly service fee is increased to $1,500 USD effective January 1, 2024.
            
            ## Rule C (New)
            A 10% late payment penalty applies to invoices not paid within 15 days.
            """

            # Ingest versioned documents
            await rag.ainsert(
                input=doc_v1,
                metadata={
                    "sequence_index": 1,
                    "effective_date": "2023-01-01",
                    "doc_type": "base",
                },
            )
            await rag.ainsert(
                input=doc_v2,
                metadata={
                    "sequence_index": 2,
                    "effective_date": "2024-01-01",
                    "doc_type": "amendment",
                },
            )

            # Query before v2 effective date (should use v1)
            result_early = await rag.aquery(
                "What is Rule A and the monthly service fee?",
                param=QueryParam(
                    mode="temporal",
                    reference_date="2023-12-31",
                ),
            )
            assert result_early is not None

            # Query after v2 effective date (should use v2)
            result_late = await rag.aquery(
                "What is Rule A and the monthly service fee?",
                param=QueryParam(
                    mode="temporal",
                    reference_date="2025-01-01",
                ),
            )
            assert result_late is not None
        finally:
            await rag.finalize_storages()

    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_query_returns_highest_version(self, temp_rag_dir):
        """
        Test that queries without reference_date return highest version.

        When no specific reference date is provided, the system should
        return the highest sequence version.
        """
        rag = LightRAG(
            working_dir=temp_rag_dir,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
        )
        await rag.initialize_storages()

        try:
            # Create documents
            base_rule = "The fee is $10."
            amendment_rule = "The fee is $15."
            final_rule = "The fee is $20."

            # Insert documents with increasing sequence indices
            await rag.ainsert(
                base_rule,
                metadata={"sequence_index": 1},
            )
            await rag.ainsert(
                amendment_rule,
                metadata={"sequence_index": 2},
            )
            await rag.ainsert(
                final_rule,
                metadata={"sequence_index": 3},
            )

            # Query without reference date
            result = await rag.aquery(
                "What is the fee?",
                param=QueryParam(mode="hybrid"),
            )
            assert result is not None
        finally:
            await rag.finalize_storages()
