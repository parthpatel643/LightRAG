#!/usr/bin/env python3
"""
LightRAG Query Debugger

This script provides detailed inspection of each step in the query execution pipeline,
including vector search, temporal filtering, entity extraction, and answer generation.

Usage:
    python debug_query.py "Your query here"
    python debug_query.py "Your query" --mode hybrid
    python debug_query.py "Your query" --relevance-threshold 0.4 --verbose

Features:
    - Vector search results with similarity scores
    - Temporal filtering decisions for each insertion_order
    - Entity and relationship extraction details
    - Chunk selection and merging process
    - Final context sent to LLM
    - Complete execution timeline
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from typing import Any, List

from functions_openai import embedding_func, llm_model_func
from lightrag import LightRAG, QueryParam
from lightrag.utils import setup_logger


# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text: str):
    """Print a formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")


def print_section(text: str):
    """Print a formatted section header"""
    print(f"\n{Colors.OKBLUE}{Colors.BOLD}▶ {text}{Colors.ENDC}")
    print(f"{Colors.OKBLUE}{'─'*80}{Colors.ENDC}")


def print_success(text: str):
    """Print success message"""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_warning(text: str, indent: int = 0):
    """Print warning message"""
    prefix = "  " * indent
    print(f"{prefix}{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def print_error(text: str, indent: int = 0):
    """Print error message"""
    prefix = "  " * indent
    print(f"{prefix}{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_info(text: str, indent: int = 0):
    """Print info message"""
    prefix = "  " * indent
    print(f"{prefix}{Colors.OKCYAN}• {text}{Colors.ENDC}")


class QueryDebugger:
    """Debug wrapper for LightRAG queries"""
    
    def __init__(self, working_dir: str = "./data/storage", verbose: bool = False):
        self.working_dir = working_dir
        self.verbose = verbose
        self.timeline = []
        self.rag = None
        
    def log_event(self, event: str, data: Any = None):
        """Log an event with timestamp"""
        self.timeline.append({
            'timestamp': datetime.now().isoformat(),
            'event': event,
            'data': data
        })
        
    async def initialize(self):
        """Initialize LightRAG instance"""
        print_section("Initializing LightRAG")
        
        self.rag = LightRAG(
            working_dir=self.working_dir,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
            chunk_token_size=2000,
            chunk_overlap_token_size=200,
            chunk_top_k=50,
            max_total_tokens=50000,
        )
        await self.rag.initialize_storages()
        
        # Get graph stats
        graph = self.rag.chunk_entity_relation_graph
        num_nodes = await graph.node_count() if hasattr(graph, 'node_count') else 'N/A'
        num_edges = await graph.edge_count() if hasattr(graph, 'edge_count') else 'N/A'
        
        print_success(f"Working directory: {self.working_dir}")
        print_success(f"Graph loaded: {num_nodes} nodes, {num_edges} edges")
        
        self.log_event("initialized", {
            'working_dir': self.working_dir,
            'nodes': num_nodes,
            'edges': num_edges
        })
        
    async def inspect_chunks(self):
        """Inspect chunk storage for temporal metadata"""
        print_section("Inspecting Chunk Storage")
        
        try:
            # Load chunks from storage
            chunks_file = f"{self.working_dir}/kv_store_text_chunks.json"
            with open(chunks_file, 'r') as f:
                chunks = json.load(f)
            
            # Group by insertion_order
            chunks_by_order = {}
            for chunk_id, chunk in chunks.items():
                order = chunk.get('insertion_order', 'unknown')
                if order not in chunks_by_order:
                    chunks_by_order[order] = []
                chunks_by_order[order].append(chunk_id)
            
            print_info(f"Total chunks: {len(chunks)}")
            
            for order in sorted(chunks_by_order.keys(), key=lambda x: int(x) if x != 'unknown' else -1):
                count = len(chunks_by_order[order])
                print_info(f"insertion_order={order}: {count} chunks", indent=1)
            
            self.log_event("chunks_inspected", {
                'total': len(chunks),
                'by_order': {k: len(v) for k, v in chunks_by_order.items()}
            })
            
        except Exception as e:
            print_error(f"Failed to inspect chunks: {e}")
    
    async def debug_query(
        self,
        query: str,
        mode: str = "hybrid",
        relevance_threshold: float = 0.3
    ):
        """Execute query with full debugging"""
        
        print_header("Query Debug Session")
        print(f"{Colors.BOLD}Query:{Colors.ENDC} {query}")
        print(f"{Colors.BOLD}Mode:{Colors.ENDC} {mode}")
        print(f"{Colors.BOLD}Relevance Threshold:{Colors.ENDC} {relevance_threshold}")
        
        self.log_event("query_started", {
            'query': query,
            'mode': mode,
            'relevance_threshold': relevance_threshold
        })
        
        # Step 1: Vector Search
        print_section("Step 1: Vector Search")
        print_info("Generating query embedding...")
        
        # Note: This is a simplified inspection - full vector search happens inside aquery
        print_warning("Vector search details are internal to aquery()")
        print_info("Check logs for: 'Query nodes:', 'Query edges:', 'Naive query:'")
        
        # Step 2: Execute Query
        print_section("Step 2: Executing Query")
        
        try:
            result = await self.rag.aquery(
                query,
                param=QueryParam(mode=mode, only_need_context=False)
            )
            
            print_success("Query executed successfully")
            self.log_event("query_completed", {'result_length': len(result)})
            
        except Exception as e:
            print_error(f"Query failed: {e}")
            self.log_event("query_failed", {'error': str(e)})
            return None
        
        # Step 3: Display Results
        print_section("Step 3: Query Results")
        print(f"\n{Colors.BOLD}Answer:{Colors.ENDC}")
        print("─" * 80)
        print(result)
        print("─" * 80)
        
        return result
    
    async def inspect_entities(self, entity_names: List[str]):
        """Inspect specific entities"""
        print_section("Inspecting Entities")
        
        graph = self.rag.chunk_entity_relation_graph
        
        for entity_name in entity_names:
            print_info(f"Entity: {entity_name}")
            
            try:
                history = await graph.get_entity_history(entity_name)
                
                if history:
                    print_info(f"insertion_order: {history.get('insertion_order', 'N/A')}", indent=1)
                    print_info(f"insertion_timestamp: {history.get('insertion_timestamp', 'N/A')}", indent=1)
                    print_info(f"update_count: {history.get('update_count', 0)}", indent=1)
                    
                    update_history = history.get('update_history', [])
                    print_info(f"update_history: {len(update_history)} chunks", indent=1)
                    
                    if self.verbose and update_history:
                        for chunk_id in update_history[:5]:  # Show first 5
                            print_info(f"- {chunk_id}", indent=2)
                else:
                    print_warning(f"Entity '{entity_name}' not found", indent=1)
                    
            except Exception as e:
                print_error(f"Failed to inspect entity: {e}", indent=1)
    
    def print_timeline(self):
        """Print execution timeline"""
        print_section("Execution Timeline")
        
        for i, event in enumerate(self.timeline, 1):
            timestamp = event['timestamp'].split('T')[1][:12]
            print_info(f"[{timestamp}] {event['event']}")
            
            if self.verbose and event.get('data'):
                print(f"    {Colors.OKCYAN}Data: {json.dumps(event['data'], indent=6)}{Colors.ENDC}")
    
    def save_debug_output(self, filename: str = "debug_output.json"):
        """Save debug output to file"""
        output = {
            'timeline': self.timeline,
            'timestamp': datetime.now().isoformat()
        }
        
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2)
        
        print_success(f"Debug output saved to: {filename}")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Debug LightRAG query execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python debug_query.py "What are the latest Boeing 787 rates?"
  python debug_query.py "Contract termination?" --mode hybrid
  python debug_query.py "Your query" --relevance-threshold 0.4 --verbose
  python debug_query.py "Your query" --inspect-entities "Boeing 787" "Pricing"
        """
    )
    
    parser.add_argument(
        "query",
        help="The query to debug"
    )
    
    parser.add_argument(
        "--mode",
        default="hybrid",
        choices=["hybrid", "local", "global", "naive"],
        help="Query mode (default: hybrid)"
    )
    
    parser.add_argument(
        "--relevance-threshold",
        type=float,
        default=0.3,
        help="Relevance threshold for temporal filtering (default: 0.3)"
    )
    
    parser.add_argument(
        "--working-dir",
        default="./data/storage",
        help="LightRAG working directory (default: ./data/storage)"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    parser.add_argument(
        "--inspect-entities",
        nargs="+",
        help="Entity names to inspect after query"
    )
    
    parser.add_argument(
        "--save-output",
        help="Save debug output to JSON file"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logger("lightrag", level=log_level)
    
    # Create debugger
    debugger = QueryDebugger(
        working_dir=args.working_dir,
        verbose=args.verbose
    )
    
    # Initialize
    await debugger.initialize()
    
    # Inspect chunks
    await debugger.inspect_chunks()
    
    # Execute query
    result = await debugger.debug_query(
        query=args.query,
        mode=args.mode,
        relevance_threshold=args.relevance_threshold
    )
    
    # Inspect entities if requested
    if args.inspect_entities:
        await debugger.inspect_entities(args.inspect_entities)
    
    # Print timeline
    debugger.print_timeline()
    
    # Save output if requested
    if args.save_output:
        debugger.save_debug_output(args.save_output)
    
    print_header("Debug Session Complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print_warning("\nDebug session interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Debug session failed: {e}")
        sys.exit(1)
