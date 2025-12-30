"""Debug script to find all 787 RON pricing information with insertion_order."""
import asyncio
from lightrag import LightRAG
from functions import llm_model_func, embedding_func, rerank_model_func

async def debug_787_ron():
    rag = LightRAG(
        working_dir='./data/storage',
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        rerank_model_func=rerank_model_func,
    )
    await rag.initialize_storages()
    
    print("\n" + "=" * 80)
    print("🔍 DEBUGGING 787 RON RATES WITH INSERTION_ORDER")
    print("=" * 80)
    
    # Get the graph storage
    graph = rag.chunk_entity_relation_graph
    
    # Get all nodes
    all_nodes = await graph.get_all_nodes()
    print(f"\nTotal nodes in graph: {len(all_nodes)}")
    
    # Search for 787 RON related entities with rate information
    target_rates = ['391.93', '384.08', '372.85', '346.77']
    
    print("\n" + "=" * 80)
    print("💰 SEARCHING FOR TARGET RATES IN NODES")
    print("=" * 80)
    
    for rate in target_rates:
        matching_nodes = []
        for node_data in all_nodes:
            if rate in str(node_data):
                matching_nodes.append(node_data)
        
        print(f"\n--- Rate: ${rate} ---")
        print(f"Found {len(matching_nodes)} nodes containing this rate:")
        
        for node_data in matching_nodes[:5]:  # Show first 5
            insertion_order = node_data.get('insertion_order', 'MISSING')
            entity_type = node_data.get('entity_type', 'UNKNOWN')
            description = node_data.get('description', 'No description')
            source_id = node_data.get('source_id', 'UNKNOWN')
            
            print(f"\n  📌 Insertion Order: {insertion_order}")
            print(f"     Type: {entity_type}")
            print(f"     Source: {source_id}")
            print(f"     Description: {description[:200]}...")
    
    # Now check edges/relationships
    all_edges = await graph.get_all_edges()
    print(f"\n\nTotal edges in graph: {len(all_edges)}")
    
    print("\n" + "=" * 80)
    print("🔗 SEARCHING FOR TARGET RATES IN EDGES")
    print("=" * 80)
    
    for rate in target_rates:
        matching_edges = []
        for edge_data in all_edges:
            if rate in str(edge_data):
                matching_edges.append(edge_data)
        
        print(f"\n--- Rate: ${rate} ---")
        print(f"Found {len(matching_edges)} edges containing this rate:")
        
        for edge_data in matching_edges[:5]:  # Show first 5
            insertion_order = edge_data.get('insertion_order', 'MISSING')
            src = edge_data.get('src_id', 'UNKNOWN')
            tgt = edge_data.get('tgt_id', 'UNKNOWN')
            description = edge_data.get('description', 'No description')
            source_id = edge_data.get('source_id', 'UNKNOWN')
            
            print(f"\n  📌 Insertion Order: {insertion_order}")
            print(f"     Edge: {src} -> {tgt}")
            print(f"     Source: {source_id}")
            print(f"     Description: {description[:200]}...")
    
    # Check chunks
    print("\n" + "=" * 80)
    print("📄 CHECKING TEXT CHUNKS")
    print("=" * 80)
    
    text_chunks_storage = rag.key_string_value_json_storage_cls(
        namespace="text_chunks",
        global_config=rag.global_config,
        embedding_func=rag.embedding_func,
    )
    
    all_chunks = await text_chunks_storage.get_all()
    print(f"\nTotal chunks: {len(all_chunks)}")
    
    for rate in target_rates:
        matching_chunks = []
        for chunk_id, chunk_data in all_chunks.items():
            if rate in str(chunk_data):
                matching_chunks.append((chunk_id, chunk_data))
        
        print(f"\n--- Rate: ${rate} ---")
        print(f"Found {len(matching_chunks)} chunks containing this rate:")
        
        for chunk_id, chunk_data in matching_chunks[:3]:  # Show first 3
            insertion_order = chunk_data.get('insertion_order', 'MISSING')
            full_doc_id = chunk_data.get('full_doc_id', 'UNKNOWN')
            content = chunk_data.get('content', 'No content')
            
            print(f"\n  📌 Chunk ID: {chunk_id}")
            print(f"     Insertion Order: {insertion_order}")
            print(f"     Document: {full_doc_id}")
            print(f"     Content snippet: {content[:300]}...")
    
    await rag.finalize_storages()

if __name__ == "__main__":
    asyncio.run(debug_787_ron())
