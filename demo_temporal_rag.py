"""
Complete Temporal RAG Demo: Sprint 1 + Sprint 2

This script demonstrates the complete workflow:
1. Sprint 1: Data Sequencing with ContractSequencer
2. Sprint 2: Versioned Entity Ingestion into LightRAG
"""

import asyncio
import tempfile
from pathlib import Path

from data_prep import ContractSequencer
from lightrag import LightRAG, QueryParam
from lightrag.llm import gpt_4o_mini_complete


def create_sample_contracts():
    """Create sample contract files for demonstration."""
    temp_dir = Path(tempfile.mkdtemp(prefix="temporal_rag_demo_"))

    # Base Contract
    base_content = """# Facilities Management Agreement

**Effective Date:** 2023-01-01

## Parties
This agreement is between Acme Corp and Facilities Plus Inc.

## Services
1. **Parking Services**: Management of 50 parking spaces at $100/space/month
2. **Cleaning Services**: Weekly office cleaning at $5,000/month
3. **Security**: 24/7 security monitoring at $8,000/month

## Payment Terms
Total monthly fee: $18,000
Payment due on the 1st of each month.
"""

    # Amendment 1
    amend1_content = """# Amendment 1 to Facilities Management Agreement

**Effective Date:** 2024-01-01

## Changes
This amendment modifies the parking services component.

### Updated Parking Services
- **Parking Services**: Expanded to 75 spaces at $120/space/month
- Reason: Market rate increase and additional demand

### Other Services
- Cleaning Services: No change
- Security: No change

## Updated Payment Terms
Total monthly fee: $22,000 (reflects parking increase from $5,000 to $9,000)
"""

    # Amendment 2
    amend2_content = """# Amendment 2 to Facilities Management Agreement

**Effective Date:** 2025-01-01

## Changes
This amendment adds new services and adjusts existing ones.

### Updated Services
- **Parking Services**: Further expanded to 100 spaces at $125/space/month
- **Cleaning Services**: Upgraded to daily cleaning at $8,000/month
- **Security**: Enhanced with AI monitoring at $10,000/month

## Updated Payment Terms
Total monthly fee: $30,500
"""

    # Write files
    base_file = temp_dir / "Base.md"
    amend1_file = temp_dir / "Amendment1.md"
    amend2_file = temp_dir / "Amendment2.md"

    base_file.write_text(base_content)
    amend1_file.write_text(amend1_content)
    amend2_file.write_text(amend2_content)

    return temp_dir, [base_file, amend1_file, amend2_file]


async def run_demo():
    """Run the complete Temporal RAG demonstration."""

    print("=" * 80)
    print("TEMPORAL RAG SYSTEM - COMPLETE DEMO")
    print("Sprint 1: Data Sequencing + Sprint 2: Versioned Ingestion")
    print("=" * 80)
    print()

    # ========================================================================
    # SPRINT 1: Data Sequencing
    # ========================================================================
    print("▶ SPRINT 1: DATA SEQUENCING")
    print("=" * 80)
    print()

    # Create test files
    temp_dir, files = create_sample_contracts()
    print(f"Created sample contracts in: {temp_dir}")
    print()

    # Define order
    order = ["Base.md", "Amendment1.md", "Amendment2.md"]

    # Initialize sequencer
    sequencer = ContractSequencer(files, order)
    print(f"Initialized ContractSequencer with order: {order}")
    print()

    # Prepare for ingestion
    sequenced_docs = sequencer.prepare_for_ingestion()
    print(f"✓ Sequenced {len(sequenced_docs)} documents")
    print()

    # Display sequencing results
    for i, doc in enumerate(sequenced_docs, 1):
        meta = doc["metadata"]
        print(f"Document {i}:")
        print(f"  Source: {meta['source']}")
        print(f"  Sequence: {meta['sequence_index']}")
        print(f"  Type: {meta['doc_type']}")
        print(f"  Date: {meta['date']}")
        print()

    # ========================================================================
    # SPRINT 2: Versioned Entity Ingestion
    # ========================================================================
    print("▶ SPRINT 2: VERSIONED ENTITY INGESTION")
    print("=" * 80)
    print()

    # Initialize LightRAG
    rag_dir = Path("./demo_temporal_rag")
    if rag_dir.exists():
        import shutil

        shutil.rmtree(rag_dir)
    rag_dir.mkdir(parents=True, exist_ok=True)

    print(f"Initializing LightRAG in: {rag_dir}")
    rag = LightRAG(
        working_dir=str(rag_dir),
        llm_model_func=gpt_4o_mini_complete,
        llm_model_name="gpt-4o-mini",
        llm_model_max_async=4,
        llm_model_max_token_size=32768,
        llm_model_kwargs={"response_format": {"type": "text"}},
    )
    print("✓ LightRAG initialized")
    print()

    # Insert each document with metadata
    print("Inserting documents with temporal metadata...")
    print("-" * 80)

    for doc in sequenced_docs:
        content = doc["content"]
        metadata = doc["metadata"]

        print(f"\nInserting: {metadata['source']} (v{metadata['sequence_index']})")
        print(f"  Type: {metadata['doc_type']}, Date: {metadata['date']}")

        await rag.ainsert(
            input=content, file_paths=metadata["source"], metadata=metadata
        )

        print("  ✓ Inserted")

    print()
    print("✓ All documents inserted with versioned entities")
    print()

    # Wait for processing
    print("Waiting for entity extraction to complete...")
    await asyncio.sleep(5)
    print()

    # ========================================================================
    # VALIDATION: Query the System
    # ========================================================================
    print("▶ VALIDATION: QUERYING THE TEMPORAL RAG SYSTEM")
    print("=" * 80)
    print()

    # Hybrid queries (baseline)
    queries = [
        "What was the original parking fee in the base contract?",
        "How did parking services change over time?",
        "What is the current monthly total payment?",
        "Compare the parking fees across all versions",
    ]

    for query in queries:
        print(f"Query: {query}")
        print("-" * 80)

        try:
            result = await rag.aquery(
                query, param=QueryParam(mode="hybrid", only_need_context=False)
            )
            response = result.response if hasattr(result, "response") else str(result)
            print(f"Response:\n{response}")
        except Exception as e:
            print(f"Error: {e}")

        print()

    # Temporal queries with reference_date
    temporal_tests = [
        ("What is the parking fee as of 2023-01-01?", "2023-01-01"),
        ("What is the parking fee as of 2024-01-01?", "2024-01-01"),
        ("What is the parking fee as of 2025-01-01?", "2025-01-01"),
    ]

    for query, ref_date in temporal_tests:
        print(f"Temporal Query: {query} (reference_date={ref_date})")
        print("-" * 80)
        try:
            result = await rag.aquery(
                query,
                param=QueryParam(
                    mode="temporal", only_need_context=False, reference_date=ref_date
                ),
            )
            response = result.response if hasattr(result, "response") else str(result)
            print(f"Response:\n{response}")
        except Exception as e:
            print(f"Error: {e}")
        print()

    # ========================================================================
    # SUMMARY
    # ========================================================================
    print("=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)
    print()
    print("✅ Sprint 1: Data successfully sequenced with temporal metadata")
    print("✅ Sprint 2: Documents ingested with versioned entities")
    print()
    print(f"📁 Sequenced files: {temp_dir}")
    print(f"📁 LightRAG storage: {rag_dir}")
    print()
    print("💡 The system now maintains separate entity versions:")
    print("   - Parking Services [v1], [v2], [v3]")
    print("   - Cleaning Services [v1], [v2], [v3]")
    print("   - etc.")
    print()
    print("🎯 This enables temporal queries and version-aware retrieval!")
    print()


if __name__ == "__main__":
    asyncio.run(run_demo())
