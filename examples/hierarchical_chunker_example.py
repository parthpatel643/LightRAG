"""
Example: Using HierarchicalMarkdownYAMLChunker with LightRAG

This example demonstrates how to integrate the HierarchicalMarkdownYAMLChunker
with LightRAG for processing legal contracts containing YAML data tables.
"""

from lightrag import LightRAG, QueryParam
from lightrag.hierarchical_chunker import create_hierarchical_chunking_func


def main():
    """
    Example of using HierarchicalMarkdownYAMLChunker with LightRAG.
    """

    # Create a LightRAG instance with hierarchical chunking
    rag = LightRAG(
        working_dir="./rag_storage_legal",
        # Use the hierarchical chunking function instead of default
        chunking_func=create_hierarchical_chunking_func(
            chunk_size=2000,  # Or use env var CHUNK_SIZE
            chunk_overlap=200,  # Or use env var CHUNK_OVERLAP_SIZE
        ),
        # Other LightRAG configuration...
    )

    # Example: Insert a legal contract
    contract_content = """Contract#: CW-2024-100
Vendor: Facilities Management Corp
Effective Date: 2024-01-15

# Service Level Agreement

This document defines the service levels for facility management.

## Maintenance Services

### Equipment Rates

```yaml
Equipment: Industrial Vacuum
Hourly Rate: $45.00
Daily Rate: $300.00
---
Equipment: Floor Scrubber
Hourly Rate: $60.00
Daily Rate: $420.00
```

## Terms

Payment due within 30 days of invoice date.
"""

    # Insert the document
    # Note: In production, you'd typically read from a file
    rag.insert(contract_content)

    # Query examples

    # 1. Query for specific equipment rates
    result = rag.query(
        "What is the hourly rate for the Floor Scrubber?",
        param=QueryParam(mode="hybrid"),
    )
    print("Query 1 - Equipment Rate:")
    print(result)
    print()

    # 2. Query for contract metadata
    result = rag.query(
        "What is the vendor name and effective date?", param=QueryParam(mode="naive")
    )
    print("Query 2 - Contract Metadata:")
    print(result)
    print()

    # 3. Query for terms and conditions
    result = rag.query("What are the payment terms?", param=QueryParam(mode="local"))
    print("Query 3 - Payment Terms:")
    print(result)


def standalone_processing_example():
    """
    Example of using the chunker standalone (without LightRAG).

    This is useful for preprocessing documents before insertion
    or for analyzing chunk structure.
    """
    from lightrag.hierarchical_chunker import HierarchicalMarkdownYAMLChunker

    # Create chunker instance
    chunker = HierarchicalMarkdownYAMLChunker(chunk_size=1500, chunk_overlap=150)

    # Process a file
    chunks = chunker.process("path/to/legal_contract.md")

    # Analyze chunks
    print(f"Total chunks: {len(chunks)}")

    yaml_chunks = [c for c in chunks if c.get("type") == "structured_row"]
    prose_chunks = [c for c in chunks if c.get("type") == "prose"]

    print(f"YAML row chunks: {len(yaml_chunks)}")
    print(f"Prose chunks: {len(prose_chunks)}")

    # Examine YAML chunks
    for chunk in yaml_chunks[:3]:
        print("\nYAML Chunk:")
        print(f"  Primary Key: {chunk.get('primary_key')}")
        print(f"  Hierarchy: {' > '.join(chunk.get('hierarchy', []))}")
        print(f"  Content preview: {chunk['content'][:100]}...")


if __name__ == "__main__":
    print("=" * 80)
    print("HierarchicalMarkdownYAMLChunker - LightRAG Integration Example")
    print("=" * 80)
    print()
    print("This example shows two usage patterns:")
    print("1. Integration with LightRAG (main function)")
    print("2. Standalone preprocessing (standalone_processing_example function)")
    print()
    print("To use with LightRAG, ensure you have:")
    print("- Configured LLM and embedding providers in .env")
    print("- Set CHUNK_SIZE and CHUNK_OVERLAP_SIZE environment variables")
    print()
    print("Example .env settings:")
    print("  CHUNK_SIZE=2000")
    print("  CHUNK_OVERLAP_SIZE=200")
    print()
    print("Uncomment the function calls below to run the examples:")
    print()

    # Uncomment to run:
    # main()
    # standalone_processing_example()
