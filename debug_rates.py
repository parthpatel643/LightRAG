"""Debug script to check what rates were extracted from the graph."""

import asyncio

from functions_openai import embedding_func, llm_model_func
from lightrag import LightRAG
from lightrag.kg.networkx_impl import NetworkXStorage

WORKING_DIR = "./data/storage"

async def check_rates():
    # Initialize LightRAG
    rag = LightRAG(
        working_dir=WORKING_DIR,
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
    )
    await rag.initialize_storages()
    
    graph: NetworkXStorage = rag.chunk_entity_relation_graph
    graph_data = await graph._get_graph()
    
    # Find all rate entities
    print("Searching for 787 RON rate entities...")
    rate_entities = []
    for node, data in graph_data.nodes(data=True):
        desc = str(data.get('description', ''))
        if '391.93' in desc or '384.08' in desc or '346.77' in desc:
            rate_entities.append((node, data))
    
    print(f'\nFound {len(rate_entities)} entities with specific 787 RON rates:\n')
    print("=" * 100)
    
    for name, data in rate_entities:
        print(f"\nEntity Name: {name}")
        print(f"  Type: {data.get('entity_type')}")
        print(f"  Description: {data.get('description', '')}")
        print(f"  Insertion Order: {data.get('insertion_order')}")
        print(f"  Insertion Timestamp: {data.get('insertion_timestamp')}")
        print(f"  Source ID: {data.get('source_id', 'N/A')}")
        print("-" * 100)
    
    # Also search for entities mentioning "787" and "Ron"
    print("\n\nSearching for all 787-related rate entities...")
    boeing_entities = []
    for node, data in graph_data.nodes(data=True):
        desc = str(data.get('description', '')).lower()
        entity_type = data.get('entity_type', '').lower()
        if entity_type == 'rate' and ('787' in desc or '787' in str(node)):
            boeing_entities.append((node, data))
    
    print(f'\nFound {len(boeing_entities)} total 787 rate entities:\n')
    print("=" * 100)
    
    # Sort by insertion order to see chronological order
    boeing_entities.sort(key=lambda x: x[1].get('insertion_order', 0))
    
    for name, data in boeing_entities[:10]:  # Show first 10
        print(f"\nEntity Name: {name}")
        print(f"  Type: {data.get('entity_type')}")
        print(f"  Description: {data.get('description', '')[:300]}")
        print(f"  Insertion Order: {data.get('insertion_order')}")
        print(f"  Source ID: {data.get('source_id', 'N/A')}")
        print("-" * 100)
    
    await rag.finalize_storages()

if __name__ == "__main__":
    asyncio.run(check_rates())
