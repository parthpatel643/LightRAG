from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from tenacity import retry, stop_after_attempt, wait_exponential

from .utils import generate_cache_key, logger

# Global TTL (time-to-live) settings for different cache types (in seconds)
CACHE_TTL = {
    "default": 86400 * 30,  # 30 days
    "extract": 86400 * 365,  # 1 year
    "query": 86400 * 7,     # 1 week
    "rerank": 86400 * 30,   # 30 days
}

# In-memory LRU cache for frequently accessed items
MEMORY_CACHE_SIZE = 1024  # Size of the LRU cache


@dataclass
class CacheData:
    """Data structure for caching LLM responses"""
    args_hash: str
    content: str
    prompt: str
    cache_type: str = "default"
    chunk_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    create_time: int = None
    
    def __post_init__(self):
        if self.create_time is None:
            self.create_time = int(time.time())


class TieredCache:
    """
    Tiered caching system with memory and persistent layers for LLM responses.
    
    This class provides:
    1. Ultra-fast in-memory LRU cache for frequent queries
    2. Persistent storage backing for durability
    3. Automatic cache invalidation based on TTL
    4. Cache analytics and hit rate tracking
    5. Semantic similarity cache lookup option
    
    Usage:
        cache = TieredCache(persistent_storage)
        result = await cache.get(key, default=None)
        await cache.set(key, value)
    """
    
    def __init__(self, persistent_storage):
        """
        Initialize the tiered cache.
        
        Args:
            persistent_storage: Persistent storage backend (KVStorage)
        """
        self.storage = persistent_storage
        self._memory_cache = {}  # Type-specific memory caches
        self._stats = {
            "hits": 0,
            "misses": 0,
            "memory_hits": 0,
            "semantic_hits": 0,
        }
        self._semantic_cache = {}  # Cache for semantic similarity lookups
        self._lock = asyncio.Lock()
    
    @lru_cache(maxsize=MEMORY_CACHE_SIZE)
    def _get_from_memory(self, cache_key: str) -> Optional[Tuple[str, int]]:
        """
        Get item from memory cache with LRU eviction policy.
        
        Args:
            cache_key: Cache key
            
        Returns:
            Tuple of (content, timestamp) or None if not found
        """
        cache_type = cache_key.split(":", 1)[0] if ":" in cache_key else "default"
        type_cache = self._memory_cache.get(cache_type, {})
        
        if cache_key in type_cache:
            self._stats["memory_hits"] += 1
            return type_cache[cache_key]
        
        return None
    
    def _add_to_memory(self, cache_key: str, value: Tuple[str, int]) -> None:
        """
        Add item to memory cache with type-specific management.
        
        Args:
            cache_key: Cache key
            value: Value to store (content, timestamp)
        """
        cache_type = cache_key.split(":", 1)[0] if ":" in cache_key else "default"
        
        if cache_type not in self._memory_cache:
            self._memory_cache[cache_type] = {}
            
        self._memory_cache[cache_type][cache_key] = value
        
        # Enforce memory limits by removing oldest items if needed
        cache = self._memory_cache[cache_type]
        if len(cache) > MEMORY_CACHE_SIZE:
            # Simple LRU implementation - remove random item (python 3.7+ dicts maintain insertion order)
            oldest_key = next(iter(cache))
            del cache[oldest_key]
    
    async def get(self, cache_key: str, default=None) -> Optional[Tuple[str, int]]:
        """
        Get item from cache (memory first, then persistent).
        
        Args:
            cache_key: Cache key
            default: Default value if not found
            
        Returns:
            Tuple of (content, timestamp) or default if not found
        """
        # Try memory cache first (fast path)
        mem_result = self._get_from_memory(cache_key)
        if mem_result:
            self._stats["hits"] += 1
            return mem_result
            
        # Try persistent storage
        try:
            result = await self._get_from_persistent(cache_key)
            if result:
                content, timestamp = result
                
                # Check if the result is still valid based on TTL
                if self._is_valid(cache_key, timestamp):
                    self._stats["hits"] += 1
                    
                    # Add to memory cache for faster future lookups
                    self._add_to_memory(cache_key, (content, timestamp))
                    return content, timestamp
                    
        except Exception as e:
            logger.warning(f"Cache get error for {cache_key}: {str(e)}")
        
        self._stats["misses"] += 1
        return default
    
    async def _get_from_persistent(self, cache_key: str) -> Optional[Tuple[str, int]]:
        """
        Get item from persistent storage.
        
        Args:
            cache_key: Cache key
            
        Returns:
            Tuple of (content, timestamp) or None if not found
        """
        if self.storage is None:
            return None
            
        result = await self.storage.get_by_id(cache_key)
        if result and "content" in result:
            content = result["content"]
            timestamp = result.get("create_time", 0)
            return content, timestamp
            
        return None
    
    def _is_valid(self, cache_key: str, timestamp: int) -> bool:
        """
        Check if cache entry is still valid based on TTL.
        
        Args:
            cache_key: Cache key
            timestamp: Timestamp of cache entry
            
        Returns:
            True if valid, False if expired
        """
        cache_type = cache_key.split(":", 1)[0] if ":" in cache_key else "default"
        ttl = CACHE_TTL.get(cache_type, CACHE_TTL["default"])
        
        # Check if the cache entry has expired
        return (int(time.time()) - timestamp) < ttl
    
    async def set(self, cache_data: CacheData) -> None:
        """
        Set item in both memory and persistent cache.
        
        Args:
            cache_data: Cache data object
        """
        if not cache_data.args_hash:
            logger.warning("Attempted to cache item with empty hash")
            return
            
        cache_key = generate_cache_key(
            cache_data.cache_type, 
            "default", 
            cache_data.args_hash
        )
        
        # Add to memory cache
        self._add_to_memory(
            cache_key, 
            (cache_data.content, cache_data.create_time)
        )
        
        # Add to persistent storage
        if self.storage:
            try:
                await self._set_in_persistent(cache_key, cache_data)
                
                # If this is an extraction cache, add to chunk reference
                if cache_data.chunk_id and cache_data.cache_type == "extract":
                    await self._update_chunk_cache_reference(
                        cache_data.chunk_id, 
                        cache_key
                    )
            except Exception as e:
                logger.warning(f"Cache set error for {cache_key}: {str(e)}")
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def _set_in_persistent(self, cache_key: str, cache_data: CacheData) -> None:
        """
        Set item in persistent storage with retry logic.
        
        Args:
            cache_key: Cache key
            cache_data: Cache data object
        """
        if self.storage is None:
            return
            
        # Prepare data for storage
        data = {
            "content": cache_data.content,
            "prompt": cache_data.prompt,
            "create_time": cache_data.create_time,
            "cache_type": cache_data.cache_type,
        }
        
        if cache_data.chunk_id:
            data["chunk_id"] = cache_data.chunk_id
            
        if cache_data.metadata:
            data["metadata"] = cache_data.metadata
            
        # Store in persistent storage
        await self.storage.upsert({cache_key: data})
    
    async def _update_chunk_cache_reference(self, chunk_id: str, cache_key: str) -> None:
        """
        Update chunk's reference to cache entry.
        
        Args:
            chunk_id: Chunk ID
            cache_key: Cache key to reference
        """
        if self.storage is None:
            return
            
        try:
            # Get the chunk data
            chunk_data = await self.storage.get_by_id(chunk_id)
            if not chunk_data:
                return
                
            # Initialize cache list if not present
            if "llm_cache_list" not in chunk_data:
                chunk_data["llm_cache_list"] = []
                
            # Add cache key if not already present
            if cache_key not in chunk_data["llm_cache_list"]:
                chunk_data["llm_cache_list"].append(cache_key)
                await self.storage.upsert({chunk_id: chunk_data})
                
        except Exception as e:
            logger.warning(f"Failed to update chunk cache reference: {str(e)}")
    
    async def get_semantic_match(
        self,
        query: str,
        embedding_func: callable,
        threshold: float = 0.95,
        cache_type: str = "query"
    ) -> Optional[Tuple[str, int, float]]:
        """
        Find semantically similar cached response.
        
        Args:
            query: Query text
            embedding_func: Function to generate embeddings
            threshold: Similarity threshold (0-1)
            cache_type: Cache type to search in
            
        Returns:
            Tuple of (content, timestamp, similarity) or None if not found
        """
        if self.storage is None:
            return None
            
        # Get embedding for query
        try:
            query_embedding = await embedding_func([query])
            if not isinstance(query_embedding, np.ndarray):
                return None
                
            query_embedding = query_embedding.reshape(-1)
        except Exception as e:
            logger.warning(f"Error generating embedding: {str(e)}")
            return None
        
        async with self._lock:
            # Get cached entries for this cache type
            if cache_type not in self._semantic_cache:
                # Initialize semantic cache for this type
                self._semantic_cache[cache_type] = await self._load_semantic_cache(cache_type)
                
            # Find best match
            best_match = None
            best_similarity = -1
            
            for entry in self._semantic_cache[cache_type]:
                cached_embedding = np.array(entry["embedding"])
                
                # Calculate cosine similarity
                similarity = np.dot(query_embedding, cached_embedding) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(cached_embedding)
                )
                
                if similarity > threshold and similarity > best_similarity:
                    best_similarity = similarity
                    best_match = entry
            
            if best_match:
                self._stats["semantic_hits"] += 1
                return best_match["content"], best_match["timestamp"], best_similarity
                
        return None
    
    async def _load_semantic_cache(self, cache_type: str) -> List[Dict[str, Any]]:
        """
        Load semantic cache from persistent storage.
        
        Args:
            cache_type: Cache type to load
            
        Returns:
            List of semantic cache entries
        """
        if self.storage is None:
            return []
            
        try:
            # Query storage for semantic cache entries
            # Implementation depends on storage backend capabilities
            # This is a placeholder for actual implementation
            return []
        except Exception as e:
            logger.warning(f"Error loading semantic cache: {str(e)}")
            return []
    
    @property
    def stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0
        
        stats = {**self._stats}
        stats["hit_rate"] = hit_rate
        
        return stats
    
    async def clear(self, cache_type: Optional[str] = None) -> None:
        """
        Clear cache entries.
        
        Args:
            cache_type: Specific cache type to clear or None for all
        """
        # Clear memory cache
        if cache_type:
            self._memory_cache.pop(cache_type, None)
        else:
            self._memory_cache.clear()
            
        # Clear persistent storage (implementation depends on storage backend)
        # This is a placeholder for actual implementation
        
        # Reset statistics
        if not cache_type:
            self._stats = {
                "hits": 0,
                "misses": 0,
                "memory_hits": 0,
                "semantic_hits": 0,
            }
            
            
# Initialize global tiered cache instance
_global_cache: Optional[TieredCache] = None


def get_global_cache() -> Optional[TieredCache]:
    """Get global tiered cache instance."""
    return _global_cache


def initialize_cache(persistent_storage=None):
    """Initialize global tiered cache."""
    global _global_cache
    _global_cache = TieredCache(persistent_storage)
    return _global_cache


async def get_cached_response(
    key: str,
    default=None
) -> Optional[Tuple[str, int]]:
    """
    Get cached response from global cache.
    
    Args:
        key: Cache key
        default: Default value if not found
        
    Returns:
        Tuple of (content, timestamp) or default if not found
    """
    cache = get_global_cache()
    if not cache:
        return default
        
    return await cache.get(key, default)


async def cache_response(cache_data: CacheData) -> None:
    """
    Cache response in global cache.
    
    Args:
        cache_data: Cache data object
    """
    cache = get_global_cache()
    if not cache:
        return
        
    await cache.set(cache_data)