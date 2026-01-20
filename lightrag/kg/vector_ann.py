"""
Approximate Nearest Neighbor (ANN) algorithm optimizations for vector databases.

This module provides optimized ANN algorithms and configurations for various
vector database backends to improve search performance and accuracy.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

import numpy as np

from ..utils import logger


class ANNAlgorithm(str, Enum):
    """ANN algorithm types supported by LightRAG."""
    
    FLAT = "flat"  # Exact search (no approximation)
    HNSW = "hnsw"  # Hierarchical Navigable Small World graphs
    IVF_FLAT = "ivf_flat"  # Inverted File with Flat storage
    IVF_PQ = "ivf_pq"  # Inverted File with Product Quantization
    ANNOY = "annoy"  # Approximate Nearest Neighbors Oh Yeah
    SCANN = "scann"  # Scalable Compressed Approximate Nearest Neighbors
    FAISS_GPU = "faiss_gpu"  # FAISS GPU implementation


@dataclass
class ANNConfig:
    """
    Configuration for ANN algorithms with optimized defaults.
    
    This configuration provides sensible defaults for different ANN algorithms
    based on best practices and empirical testing for RAG systems.
    """
    
    algorithm: ANNAlgorithm = ANNAlgorithm.HNSW
    metric_type: str = "cosine"  # cosine, l2, dot, etc.
    
    # HNSW parameters
    hnsw_m: int = 16  # Number of bidirectional links created per node during insertion
    hnsw_ef_construction: int = 128  # Size of the dynamic list for the nearest neighbors
    hnsw_ef_search: int = 128  # Size of the dynamic list for the nearest neighbors at search time
    
    # IVF parameters
    ivf_nlist: int = 100  # Number of clusters/cells (more for larger datasets)
    ivf_nprobe: int = 10  # Number of clusters to visit during search
    
    # PQ parameters 
    pq_m: int = 8  # Number of subquantizers
    pq_nbits: int = 8  # Number of bits per subquantizer (usually 8)
    
    # ANNOY parameters
    annoy_n_trees: int = 50  # More trees = more accuracy, but slower
    
    # GPU parameters
    gpu_id: int = 0  # GPU ID to use for FAISS_GPU
    
    # Performance tuning
    search_batch_size: int = 512  # Batch size for queries
    build_batch_size: int = 10000  # Batch size for index building
    use_batching: bool = True  # Use batching for index operations
    
    # Resource limits
    max_gpu_memory: Optional[int] = None  # Maximum GPU memory to use (in MB)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for storage backends."""
        return {k: v for k, v in self.__dict__.items() if v is not None}
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "ANNConfig":
        """Create config from dictionary."""
        return cls(**{k: v for k, v in config_dict.items() if k in cls.__annotations__})
    
    def optimize_for_dimension(self, dimension: int) -> "ANNConfig":
        """
        Optimize configuration for a specific embedding dimension.
        
        Args:
            dimension: Vector dimension
            
        Returns:
            Optimized ANNConfig instance
        """
        # Create a new instance to avoid modifying the original
        config = ANNConfig(**self.__dict__)
        
        # Adjust HNSW parameters based on dimension
        if dimension <= 128:
            config.hnsw_m = 12
            config.hnsw_ef_construction = 80
        elif dimension <= 512:
            config.hnsw_m = 16
            config.hnsw_ef_construction = 128
        elif dimension <= 1024:
            config.hnsw_m = 24
            config.hnsw_ef_construction = 200
        else:
            config.hnsw_m = 32
            config.hnsw_ef_construction = 400
            
        # Adjust IVF parameters based on dimension
        if dimension > 512:
            config.ivf_nprobe = min(20, config.ivf_nprobe)
            
        # Adjust PQ parameters based on dimension
        if config.algorithm == ANNAlgorithm.IVF_PQ:
            # For PQ, we want m * nbits divisible by dimension
            config.pq_m = max(4, dimension // 32)  # Reasonable default
            
        return config
    
    def optimize_for_dataset_size(self, dataset_size: int) -> "ANNConfig":
        """
        Optimize configuration for a specific dataset size.
        
        Args:
            dataset_size: Number of vectors in the dataset
            
        Returns:
            Optimized ANNConfig instance
        """
        # Create a new instance to avoid modifying the original
        config = ANNConfig(**self.__dict__)
        
        # Adjust IVF parameters based on dataset size
        if dataset_size < 1000:
            config.ivf_nlist = max(1, dataset_size // 10)
            config.ivf_nprobe = min(10, config.ivf_nlist)
        elif dataset_size < 10000:
            config.ivf_nlist = dataset_size // 50
        elif dataset_size < 100000:
            config.ivf_nlist = dataset_size // 100
        elif dataset_size < 1000000:
            config.ivf_nlist = dataset_size // 500
        else:
            config.ivf_nlist = dataset_size // 1000
            
        # Adjust HNSW parameters based on dataset size
        if dataset_size > 100000:
            config.hnsw_ef_construction = min(512, config.hnsw_ef_construction * 2)
            
        # For very large datasets, increase batch sizes
        if dataset_size > 1000000:
            config.build_batch_size = 50000
            
        return config


def create_optimized_index_config(
    backend: str,
    dimension: int,
    dataset_size: int,
    algorithm: Optional[str] = None,
    metric_type: str = "cosine"
) -> Dict[str, Any]:
    """
    Create optimized index configuration for different vector database backends.
    
    Args:
        backend: Database backend type ('qdrant', 'milvus', 'faiss', 'pgvector', etc.)
        dimension: Vector dimension
        dataset_size: Approximate number of vectors
        algorithm: Optional algorithm override
        metric_type: Distance metric type
        
    Returns:
        Dictionary with optimized configuration for the specified backend
    """
    # Start with baseline configuration
    ann_config = ANNConfig(
        algorithm=ANNAlgorithm(algorithm) if algorithm else ANNAlgorithm.HNSW,
        metric_type=metric_type
    )
    
    # Apply dimension and dataset size optimizations
    ann_config = ann_config.optimize_for_dimension(dimension)
    ann_config = ann_config.optimize_for_dataset_size(dataset_size)
    
    # Convert to backend-specific configuration
    if backend.lower() == "qdrant":
        return _create_qdrant_config(ann_config, dimension)
    elif backend.lower() == "milvus":
        return _create_milvus_config(ann_config, dimension)
    elif backend.lower() == "pgvector":
        return _create_pgvector_config(ann_config, dimension)
    elif backend.lower() == "faiss":
        return _create_faiss_config(ann_config, dimension)
    elif backend.lower() == "redis":
        return _create_redis_config(ann_config, dimension)
    else:
        logger.warning(f"Unknown backend '{backend}', using generic configuration")
        return ann_config.to_dict()


def _create_qdrant_config(config: ANNConfig, dimension: int) -> Dict[str, Any]:
    """Create optimized configuration for Qdrant."""
    if config.algorithm == ANNAlgorithm.HNSW:
        return {
            "vectors_config": {
                "size": dimension,
                "distance": config.metric_type,
            },
            "hnsw_config": {
                "m": config.hnsw_m,
                "ef_construct": config.hnsw_ef_construction,
                "full_scan_threshold": min(dimension * 10, 10000),
            },
            "optimizers_config": {
                "default_segment_number": 2 if dimension <= 512 else 4,
                "memmap_threshold": 20000,
            },
            "params": {
                "ef": config.hnsw_ef_search,
            }
        }
    else:
        # Qdrant currently only supports HNSW
        logger.warning(f"Qdrant only supports HNSW, ignoring algorithm {config.algorithm}")
        return _create_qdrant_config(ANNConfig(algorithm=ANNAlgorithm.HNSW), dimension)


def _create_milvus_config(config: ANNConfig, dimension: int) -> Dict[str, Any]:
    """Create optimized configuration for Milvus."""
    if config.algorithm == ANNAlgorithm.HNSW:
        return {
            "metric_type": config.metric_type.upper(),
            "index_type": "HNSW",
            "params": {
                "M": config.hnsw_m,
                "efConstruction": config.hnsw_ef_construction,
                "ef": config.hnsw_ef_search,
            }
        }
    elif config.algorithm in [ANNAlgorithm.IVF_FLAT, ANNAlgorithm.IVF_PQ]:
        index_type = "IVF_FLAT" if config.algorithm == ANNAlgorithm.IVF_FLAT else "IVF_PQ"
        return {
            "metric_type": config.metric_type.upper(),
            "index_type": index_type,
            "params": {
                "nlist": config.ivf_nlist,
                "nprobe": config.ivf_nprobe,
                "m": config.pq_m if config.algorithm == ANNAlgorithm.IVF_PQ else None
            }
        }
    elif config.algorithm == ANNAlgorithm.FLAT:
        return {
            "metric_type": config.metric_type.upper(),
            "index_type": "FLAT",
            "params": {}
        }
    else:
        logger.warning(f"Milvus doesn't support {config.algorithm}, falling back to HNSW")
        return _create_milvus_config(ANNConfig(algorithm=ANNAlgorithm.HNSW), dimension)


def _create_pgvector_config(config: ANNConfig, dimension: int) -> Dict[str, Any]:
    """Create optimized configuration for pgvector."""
    if config.algorithm == ANNAlgorithm.HNSW:
        return {
            "vector_index_type": "hnsw",
            "hnsw_m": config.hnsw_m,
            "hnsw_ef_construction": config.hnsw_ef_construction,
            "hnsw_ef": config.hnsw_ef_search,
            "dimension": dimension,
            "distance_func": "cosine_distance" if config.metric_type == "cosine" else "l2_distance"
        }
    elif config.algorithm == ANNAlgorithm.IVF_FLAT:
        return {
            "vector_index_type": "ivfflat",
            "ivfflat_lists": config.ivf_nlist,
            "dimension": dimension,
            "probes": config.ivf_nprobe,
            "distance_func": "cosine_distance" if config.metric_type == "cosine" else "l2_distance"
        }
    else:
        logger.warning(f"pgvector doesn't support {config.algorithm}, falling back to HNSW")
        return _create_pgvector_config(ANNConfig(algorithm=ANNAlgorithm.HNSW), dimension)


def _create_faiss_config(config: ANNConfig, dimension: int) -> Dict[str, Any]:
    """Create optimized configuration for FAISS."""
    metric_type_map = {"cosine": "IP", "l2": "L2", "dot": "IP"}
    metric = metric_type_map.get(config.metric_type, "IP")
    
    if config.algorithm == ANNAlgorithm.HNSW:
        return {
            "description": f"HNSW{dimension},{metric},M={config.hnsw_m},efConstruction={config.hnsw_ef_construction}",
            "metric_type": metric,
            "parameters": {
                "M": config.hnsw_m,
                "efConstruction": config.hnsw_ef_construction,
                "efSearch": config.hnsw_ef_search,
                "dimension": dimension,
            }
        }
    elif config.algorithm == ANNAlgorithm.IVF_FLAT:
        return {
            "description": f"IVF{config.ivf_nlist},Flat,{metric}",
            "metric_type": metric,
            "parameters": {
                "nlist": config.ivf_nlist,
                "nprobe": config.ivf_nprobe,
                "dimension": dimension,
            }
        }
    elif config.algorithm == ANNAlgorithm.IVF_PQ:
        return {
            "description": f"IVF{config.ivf_nlist},PQ{config.pq_m}x{config.pq_nbits},{metric}",
            "metric_type": metric,
            "parameters": {
                "nlist": config.ivf_nlist,
                "nprobe": config.ivf_nprobe,
                "m": config.pq_m,
                "nbits": config.pq_nbits,
                "dimension": dimension,
            }
        }
    elif config.algorithm == ANNAlgorithm.FLAT:
        return {
            "description": f"Flat,{metric}",
            "metric_type": metric,
            "parameters": {
                "dimension": dimension,
            }
        }
    elif config.algorithm == ANNAlgorithm.FAISS_GPU:
        return {
            "description": f"IVF{config.ivf_nlist},Flat,{metric},GPU{config.gpu_id}",
            "metric_type": metric,
            "parameters": {
                "nlist": config.ivf_nlist,
                "nprobe": config.ivf_nprobe,
                "dimension": dimension,
                "gpu_id": config.gpu_id,
                "max_gpu_memory_mb": config.max_gpu_memory,
            }
        }
    else:
        logger.warning(f"FAISS doesn't directly support {config.algorithm}, falling back to HNSW")
        return _create_faiss_config(ANNConfig(algorithm=ANNAlgorithm.HNSW), dimension)


def _create_redis_config(config: ANNConfig, dimension: int) -> Dict[str, Any]:
    """Create optimized configuration for Redis."""
    if config.algorithm == ANNAlgorithm.HNSW:
        return {
            "M": config.hnsw_m,
            "EF": config.hnsw_ef_search,
            "EF_CONSTRUCTION": config.hnsw_ef_construction,
            "DISTANCE_METRIC": "COSINE" if config.metric_type == "cosine" else "L2",
            "TYPE": "HNSW",
            "DIM": dimension,
            "INITIAL_CAP": min(10000, dimension * 20),
        }
    elif config.algorithm == ANNAlgorithm.FLAT:
        return {
            "TYPE": "FLAT",
            "DIM": dimension,
            "DISTANCE_METRIC": "COSINE" if config.metric_type == "cosine" else "L2",
            "INITIAL_CAP": min(10000, dimension * 20),
        }
    else:
        logger.warning(f"Redis doesn't support {config.algorithm}, falling back to HNSW")
        return _create_redis_config(ANNConfig(algorithm=ANNAlgorithm.HNSW), dimension)


def normalize_vectors_for_metric(
    vectors: np.ndarray,
    metric_type: str
) -> np.ndarray:
    """
    Normalize vectors based on the metric type.
    
    Args:
        vectors: NumPy array of vectors to normalize
        metric_type: Metric type ('cosine', 'l2', 'dot')
        
    Returns:
        Normalized vectors
    """
    if metric_type.lower() in ["cosine", "angular"]:
        # Normalize for cosine similarity
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        # Avoid division by zero
        norms[norms == 0] = 1.0
        return vectors / norms
    else:
        # For L2 and dot product, no normalization needed
        return vectors


def optimize_batch_size(
    dimension: int,
    vector_count: int,
    max_ram_mb: int = 4000
) -> int:
    """
    Calculate optimal batch size based on vector dimension and available RAM.
    
    Args:
        dimension: Vector dimension
        vector_count: Number of vectors
        max_ram_mb: Maximum RAM to use (in MB)
        
    Returns:
        Optimal batch size
    """
    # Each float32 value is 4 bytes
    vector_size_bytes = dimension * 4
    
    # Allow for overhead (metadata, indices, etc.)
    overhead_factor = 1.5
    
    # Calculate batch size based on RAM limit
    max_ram_bytes = max_ram_mb * 1024 * 1024
    max_vectors = max_ram_bytes / (vector_size_bytes * overhead_factor)
    
    # Constrain batch size to be at least 10 and at most vector_count
    batch_size = min(max(int(max_vectors), 10), vector_count)
    
    # Round to nearest power of 2 for better memory alignment
    # Find the nearest power of 2 (either up or down, whichever is closer)
    log2 = np.log2(batch_size)
    lower = 2 ** int(np.floor(log2))
    upper = 2 ** int(np.ceil(log2))
    
    if batch_size - lower < upper - batch_size:
        return lower
    else:
        return upper