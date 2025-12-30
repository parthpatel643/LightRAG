"""Debug script to check insertion_order values in the graph."""
import asyncio
from lightrag import LightRAG
from functions import llm_model_func, embedding_func, rerank_model_func

async def debug_insertion_order():
    rag = LightRAG(
        working_dir='./data/storage',
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        rerank_model_func=rerank_model_func,
    )
    await rag.initialize_storages()
    
    # Search for Boeing 787 related entities
    print("\n🔍 Searching for Boeing 787 entities...")
    print("=" * 80)
    
    # Get the graph storage
    graph = rag.chunk_entity_relation_graph
    
    # Search for Boeing 787 related nodes
    boeing_nodes = []
    all_nodes = await graph.get_all_nodes()
    
    print(f"DEBUG: all_nodes type = {type(all_nodes)}, length = {len(all_nodes)}")
    
    # all_nodes is a list of node data dictionaries
    for node_data in all_nodes:
        node_name = node_data.get('entity_name', node_data.get('name', 'UNKNOWN'))
        node_str = str(node_data).lower()
        if '787' in node_str or '787' in str(node_name).lower():
            boeing_nodes.append((node_name, node_data))
    
    print(f"\nFound {len(boeing_nodes)} Boeing 787-related nodes:")
    for node_name, node_data in boeing_nodes[:10]:  # Limit to first 10
        insertion_order = node_data.get('insertion_order', 'MISSING')
        entity_type = node_data.get('entity_type', 'UNKNOWN')
        description = node_data.get('description', 'No description')[:100]
        print(f"\n  Entity: {node_name}")
        print(f"    Type: {entity_type}")
        print(f"    Insertion Order: {insertion_order}")
        print(f"    Description: {description}...")
    
    # Now check pricing-related entities
    print("\n\n💰 Searching for pricing/rate entities...")
    print("=" * 80)
    
    pricing_keywords = ['price', 'rate', '391.93', '384.08', '372.85', 'ron', 'lavatory']
    pricing_nodes = []
    
    for node_data in all_nodes:
        node_name = node_data.get('entity_name', node_data.get('name', 'UNKNOWN'))
        node_str = (str(node_name) + str(node_data)).lower()
        if any(kw in node_str for kw in pricing_keywords):
            pricing_nodes.append((node_name, node_data))
    
    print(f"\nFound {len(pricing_nodes)} pricing-related nodes:")
    for node_name, node_data in pricing_nodes[:20]:  # Limit to first 20
        insertion_order = node_data.get('insertion_order', 'MISSING')
        entity_type = node_data.get('entity_type', 'UNKNOWN')
        description = node_data.get('description', 'No description')[:150]
        print(f"\n  Entity: {node_name}")
        print(f"    Type: {entity_type}")
        print(f"    Insertion Order: {insertion_order}")
        print(f"    Description: {description}...")
    
    # Check relationships/edges
    print("\n\n🔗 Searching for pricing relationships...")
    print("=" * 80)
    
    all_edges = await graph.get_all_edges()
    print(f"DEBUG: all_edges type = {type(all_edges)}, length = {len(all_edges)}")
    
    pricing_edges = []
    
    for edge_data in all_edges:
        src = edge_data.get('src_id', 'UNKNOWN_SRC')
        tgt = edge_data.get('tgt_id', 'UNKNOWN_TGT')
        edge_str = str(edge_data).lower()
        if any(kw in edge_str for kw in pricing_keywords):
            pricing_edges.append((src, tgt, edge_data))
    
    print(f"\nFound {len(pricing_edges)} pricing-related edges:")
    for src, tgt, edge_data in pricing_edges[:20]:  # Limit to first 20
        insertion_order = edge_data.get('insertion_order', 'MISSING')
        description = edge_data.get('description', 'No description')[:150]
        print(f"\n  Relationship: {src} -> {tgt}")
        print(f"    Insertion Order: {insertion_order}")
        print(f"    Description: {description}...")
    
    await rag.finalize_storages()

if __name__ == "__main__":
    asyncio.run(debug_insertion_order())
