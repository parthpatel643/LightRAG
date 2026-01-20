"""
PostgreSQL optimization utilities for LightRAG.

This module provides optimizations for PostgreSQL storage backends
to enhance performance through:
- Automatic index management
- Connection pooling optimization 
- Query performance tuning
- Batch operations
"""

import asyncio
from typing import Any, Dict, List


from ..utils import logger


class PostgreSQLOptimizer:
    """
    Optimizer for PostgreSQL storage backends in LightRAG.
    
    This class provides methods to optimize:
    - Database indexes and statistics
    - Query performance
    - Connection pooling
    - Vector search performance
    """
    
    def __init__(self, db_connection):
        """
        Initialize the PostgreSQL optimizer.
        
        Args:
            db_connection: PostgreSQL database connection
        """
        self.db = db_connection
        self._initialized = False
        
    async def initialize(self):
        """Initialize the optimizer by gathering database information."""
        if self._initialized:
            return
            
        # Get database version
        version_info = await self.db.query("SELECT version()")
        self.db_version = version_info['version'] if version_info else "Unknown"
        logger.info(f"PostgreSQL optimizer initialized for version: {self.db_version}")
        self._initialized = True
        
    async def analyze_indexes(self, table_name: str) -> Dict[str, Any]:
        """
        Analyze existing indexes on a table and recommend improvements.
        
        Args:
            table_name: Name of the table to analyze
            
        Returns:
            Dictionary with index analysis results and recommendations
        """
        if not self._initialized:
            await self.initialize()
            
        # Get existing indexes
        indexes_query = """
            SELECT 
                i.indexname as index_name,
                i.indexdef as index_definition,
                pg_stat_user_indexes.idx_scan as usage_count,
                pg_stat_user_indexes.idx_tup_read as tuples_read,
                pg_stat_user_indexes.idx_tup_fetch as tuples_fetched
            FROM 
                pg_indexes i
            LEFT JOIN 
                pg_stat_user_indexes ON i.indexname = pg_stat_user_indexes.indexrelname
            WHERE 
                i.tablename = $1
            ORDER BY 
                pg_stat_user_indexes.idx_scan DESC NULLS LAST
        """
        
        existing_indexes = await self.db.query(indexes_query, [table_name], multirows=True)
        
        # Get table statistics
        table_stats_query = """
            SELECT 
                reltuples as row_estimate,
                pg_size_pretty(pg_relation_size($1)) as table_size,
                pg_size_pretty(pg_total_relation_size($1) - pg_relation_size($1)) as index_size
            FROM 
                pg_class
            WHERE 
                relname = $1
        """
        
        table_stats = await self.db.query(table_stats_query, [table_name])
        
        # Analyze unused indexes
        unused_indexes = [
            idx for idx in existing_indexes 
            if idx['usage_count'] is not None and idx['usage_count'] < 10
        ]
        
        # Analyze missing indexes
        missing_indexes_query = """
            SELECT 
                relname as table_name,
                seq_scan as seq_scans,
                idx_scan as idx_scans
            FROM 
                pg_stat_user_tables
            WHERE 
                relname = $1
        """
        
        scan_stats = await self.db.query(missing_indexes_query, [table_name])
        
        # Generate recommendations
        recommendations = []
        if scan_stats:
            seq_scans = scan_stats['seq_scans'] or 0
            idx_scans = scan_stats['idx_scans'] or 0
            
            if seq_scans > idx_scans * 3 and seq_scans > 100:
                recommendations.append(f"Table {table_name} has {seq_scans} sequential scans vs {idx_scans} index scans - consider adding indexes")
                
        if unused_indexes:
            for idx in unused_indexes:
                recommendations.append(f"Index {idx['index_name']} is rarely used ({idx['usage_count']} scans) - consider removing")
                
        return {
            "table_name": table_name,
            "table_stats": table_stats,
            "existing_indexes": existing_indexes,
            "unused_indexes": unused_indexes,
            "recommendations": recommendations
        }
    
    async def optimize_table(self, table_name: str) -> Dict[str, Any]:
        """
        Run ANALYZE on a table to update statistics and optimize query planning.
        
        Args:
            table_name: Name of the table to optimize
            
        Returns:
            Dictionary with optimization results
        """
        start_time = asyncio.get_event_loop().time()
        
        # Safely escape table name to prevent SQL injection
        sanitized_table = table_name.replace('"', '""')
        
        try:
            # Run ANALYZE to update table statistics
            await self.db.execute(f'ANALYZE "{sanitized_table}"')
            
            end_time = asyncio.get_event_loop().time()
            duration = end_time - start_time
            
            return {
                "success": True,
                "table": table_name,
                "duration_seconds": duration,
                "message": f"Table {table_name} successfully optimized in {duration:.2f} seconds"
            }
        except Exception as e:
            return {
                "success": False,
                "table": table_name,
                "error": str(e)
            }
    
    async def create_optimized_vector_index(
        self, 
        table_name: str, 
        column_name: str = "embedding",
        index_type: str = "hnsw",
        index_options: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Create an optimized vector index for faster similarity searches.
        
        Args:
            table_name: Name of the table
            column_name: Name of the vector column
            index_type: Type of index (ivfflat, hnsw, or exact)
            index_options: Additional index options
            
        Returns:
            Dictionary with index creation results
        """
        if not self._initialized:
            await self.initialize()
            
        # Default options based on index type
        default_options = {
            "hnsw": {"m": 16, "ef_construction": 64},
            "ivfflat": {"lists": 100},
            "exact": {}
        }
        
        options = {**default_options.get(index_type, {}), **(index_options or {})}
        
        # Generate a safe index name
        index_name = f"idx_{table_name.lower()}_{column_name}_{index_type}"
        if len(index_name) > 63:  # PostgreSQL identifier length limit
            # Use a shorter name if it would exceed the limit
            index_name = f"idx_{table_name.lower()[:20]}_{column_name}_{index_type}"
            
        # Create the appropriate index based on type
        try:
            if index_type == "hnsw":
                sql = f"""
                    CREATE INDEX IF NOT EXISTS {index_name}
                    ON {table_name} USING hnsw({column_name} vector_cosine_ops)
                    WITH (m = {options['m']}, ef_construction = {options['ef_construction']})
                """
            elif index_type == "ivfflat":
                sql = f"""
                    CREATE INDEX IF NOT EXISTS {index_name}
                    ON {table_name} USING ivfflat({column_name} vector_cosine_ops)
                    WITH (lists = {options['lists']})
                """
            else:  # exact index
                sql = f"""
                    CREATE INDEX IF NOT EXISTS {index_name}
                    ON {table_name} USING vector_cosine_ops({column_name})
                """
                
            await self.db.execute(sql)
            
            return {
                "success": True,
                "table": table_name,
                "column": column_name,
                "index_name": index_name,
                "index_type": index_type,
                "options": options,
                "message": f"Created {index_type} vector index on {table_name}.{column_name}"
            }
        except Exception as e:
            return {
                "success": False,
                "table": table_name,
                "column": column_name,
                "index_type": index_type,
                "error": str(e)
            }
    
    async def optimize_connection_pool(
        self, 
        min_size: int = 5,
        max_size: int = 20,
        max_queries: int = 50000,
        max_idle: int = 300
    ) -> Dict[str, Any]:
        """
        Optimize the database connection pool settings.
        
        Args:
            min_size: Minimum number of connections
            max_size: Maximum number of connections
            max_queries: Maximum number of queries per connection
            max_idle: Maximum idle time in seconds
            
        Returns:
            Dictionary with pool optimization results
        """
        if not hasattr(self.db, "pool") or not self.db.pool:
            return {
                "success": False,
                "error": "No connection pool available"
            }
            
        # Pool settings can only be set when creating the pool,
        # so this is just informational for future reference
        return {
            "success": True,
            "message": "Connection pool optimization recommendations (apply when creating pool)",
            "recommendations": {
                "min_size": min_size,
                "max_size": max_size,
                "max_queries": max_queries,
                "max_idle": max_idle,
                "connection_string": f"postgresql://user:password@host:port/db?min_size={min_size}&max_size={max_size}&max_queries={max_queries}&max_idle={max_idle}"
            }
        }
    
    async def analyze_query_performance(self, sql: str, params: List[Any] = None) -> Dict[str, Any]:
        """
        Analyze query performance using EXPLAIN ANALYZE.
        
        Args:
            sql: SQL query to analyze
            params: Query parameters
            
        Returns:
            Dictionary with query analysis results
        """
        if not self._initialized:
            await self.initialize()
            
        explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"
        
        try:
            # Get the query execution plan
            plan_results = await self.db.query(explain_sql, params or [], multirows=False)
            
            if not plan_results or not isinstance(plan_results, list):
                return {"success": False, "error": "Invalid query plan result"}
                
            plan = plan_results[0]
            
            # Extract key metrics from the plan
            execution_time = plan.get("Planning Time", 0) + plan.get("Execution Time", 0)
            planning_time = plan.get("Planning Time", 0)
            execution_time = plan.get("Execution Time", 0)
            
            # Extract nodes that might benefit from optimization
            nodes_to_optimize = []
            
            def extract_nodes(node):
                if node.get("Actual Total Time", 0) > execution_time * 0.1:  # Nodes taking >10% of time
                    nodes_to_optimize.append({
                        "node_type": node["Node Type"],
                        "time": node.get("Actual Total Time", 0),
                        "rows": node.get("Actual Rows", 0)
                    })
                    
                # Recursively process child nodes
                for child in node.get("Plans", []):
                    extract_nodes(child)
            
            # Process the root node
            root_node = plan.get("Plan", {})
            extract_nodes(root_node)
            
            # Generate recommendations
            recommendations = []
            
            # Check for sequential scans
            if any(node["node_type"] == "Seq Scan" for node in nodes_to_optimize):
                recommendations.append("Query uses sequential scans - consider adding indexes")
                
            # Check for hash joins on large tables
            if any(node["node_type"] == "Hash Join" and node["rows"] > 10000 for node in nodes_to_optimize):
                recommendations.append("Large hash join detected - consider optimizing join conditions")
                
            return {
                "success": True,
                "execution_time_ms": execution_time,
                "planning_time_ms": planning_time,
                "total_time_ms": planning_time + execution_time,
                "plan": plan,
                "nodes_to_optimize": nodes_to_optimize,
                "recommendations": recommendations
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


async def analyze_postgresql_performance(db_connection, workspace: str) -> Dict[str, Any]:
    """
    Analyze PostgreSQL database performance for a specific workspace.
    
    Args:
        db_connection: Database connection object
        workspace: Workspace to analyze
        
    Returns:
        Dictionary with performance analysis results
    """
    optimizer = PostgreSQLOptimizer(db_connection)
    await optimizer.initialize()
    
    # Get all tables in the LightRAG namespace
    tables_query = """
        SELECT 
            table_name 
        FROM 
            information_schema.tables
        WHERE 
            table_schema = 'public'
        AND
            table_name LIKE '%vector%' OR table_name LIKE '%entity%' OR table_name LIKE '%relation%'
    """
    
    tables = await db_connection.query(tables_query, [], multirows=True)
    
    if not tables:
        return {
            "success": False,
            "error": "No relevant tables found"
        }
    
    results = {
        "workspace": workspace,
        "tables_analyzed": [],
        "overall_recommendations": []
    }
    
    # Analyze each table
    for table_record in tables:
        table_name = table_record.get('table_name')
        if not table_name:
            continue
            
        # Analyze indexes
        index_analysis = await optimizer.analyze_indexes(table_name)
        
        # Run table optimization
        optimization_result = await optimizer.optimize_table(table_name)
        
        results["tables_analyzed"].append({
            "table_name": table_name,
            "index_analysis": index_analysis,
            "optimization_result": optimization_result
        })
        
        # Collect overall recommendations
        results["overall_recommendations"].extend(index_analysis.get("recommendations", []))
        
    # Deduplicate recommendations
    results["overall_recommendations"] = list(set(results["overall_recommendations"]))
    
    # Add connection pool recommendations
    pool_recommendations = await optimizer.optimize_connection_pool()
    results["connection_pool"] = pool_recommendations
    
    return {
        "success": True,
        "analysis": results
    }


async def create_vector_indexes(
    db_connection, 
    table_names: List[str], 
    column_name: str = "embedding",
    index_type: str = "hnsw"
) -> Dict[str, Any]:
    """
    Create vector indexes on multiple tables.
    
    Args:
        db_connection: Database connection object
        table_names: List of tables to create indexes for
        column_name: Name of the vector column
        index_type: Type of index (hnsw, ivfflat, or exact)
        
    Returns:
        Dictionary with index creation results
    """
    optimizer = PostgreSQLOptimizer(db_connection)
    await optimizer.initialize()
    
    results = {
        "success": True,
        "indexes_created": [],
        "errors": []
    }
    
    for table_name in table_names:
        index_result = await optimizer.create_optimized_vector_index(
            table_name=table_name,
            column_name=column_name,
            index_type=index_type
        )
        
        if index_result.get("success"):
            results["indexes_created"].append(index_result)
        else:
            results["errors"].append(index_result)
            
    if results["errors"]:
        results["success"] = False
        
    return results