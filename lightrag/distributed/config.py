"""
Configuration for LightRAG distributed processing.

This module provides configuration classes for setting up distributed processing
with various backends and strategies.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class DistributionStrategy(str, Enum):
    """Strategy for distributing workloads across workers."""
    
    ROUND_ROBIN = "round_robin"  # Simple round-robin assignment of tasks
    LOAD_BASED = "load_based"    # Based on worker load/capacity
    CONTENT_HASH = "content_hash" # Hash-based routing for content affinity
    PRIORITY = "priority"        # Based on task priority
    CUSTOM = "custom"            # Custom routing function


class DistributionBackend(str, Enum):
    """Backend for distributed processing."""
    
    PROCESSES = "processes"   # Local multiprocessing
    THREADS = "threads"       # Threaded processing (useful for I/O bound tasks)
    RAY = "ray"              # Ray distributed computing framework
    DASK = "dask"            # Dask distributed computing framework
    CELERY = "celery"        # Celery task queue
    REDIS = "redis"          # Redis-based task distribution
    CUSTOM = "custom"        # Custom backend implementation


@dataclass
class DistributedConfig:
    """
    Configuration for distributed processing.
    
    This class contains all configuration parameters for setting up and tuning
    distributed processing capabilities in LightRAG.
    """
    
    # Basic configuration
    enabled: bool = False  # Whether distributed processing is enabled
    backend: DistributionBackend = DistributionBackend.PROCESSES  # Processing backend
    strategy: DistributionStrategy = DistributionStrategy.LOAD_BASED  # Distribution strategy
    
    # Resource configuration
    num_workers: int = 0  # Number of workers (0 = auto based on CPU count)
    max_memory_per_worker_mb: Optional[int] = None  # Memory limit per worker
    worker_timeout: int = 3600  # Worker timeout in seconds
    
    # Queue configuration
    queue_size: int = 1000  # Maximum queue size for pending tasks
    batch_size: int = 10  # Batch size for task processing
    
    # Task routing
    affinity_key_field: str = "doc_id"  # Field used for content-based affinity
    
    # Performance tuning
    use_shared_memory: bool = True  # Use shared memory for data passing
    prefetch_factor: int = 2  # How many batches to prefetch
    
    # Advanced options
    backend_specific: Dict[str, Any] = field(default_factory=dict)  # Backend-specific options
    
    def __post_init__(self):
        """Validate and normalize configuration."""
        import multiprocessing
        
        # Auto-configure number of workers if not specified
        if self.num_workers <= 0:
            # Leave 1 core for the main process
            self.num_workers = max(1, multiprocessing.cpu_count() - 1)
            
        # Validate batch size
        if self.batch_size <= 0:
            self.batch_size = 1
            
        # Initialize backend-specific defaults
        if self.backend == DistributionBackend.RAY:
            ray_defaults = {
                "address": "auto",  # Connect to existing Ray cluster if available
                "include_dashboard": True,
                "runtime_env": {},
            }
            # Update with user settings, preserving defaults for unspecified values
            self.backend_specific = {**ray_defaults, **self.backend_specific}
            
        elif self.backend == DistributionBackend.DASK:
            dask_defaults = {
                "scheduler": "processes",  # processes or threads
                "temporary_directory": None,
            }
            self.backend_specific = {**dask_defaults, **self.backend_specific}
            
        elif self.backend == DistributionBackend.CELERY:
            celery_defaults = {
                "broker_url": "redis://localhost:6379/0",
                "result_backend": "redis://localhost:6379/0",
            }
            self.backend_specific = {**celery_defaults, **self.backend_specific}
            
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "enabled": self.enabled,
            "backend": self.backend.value,
            "strategy": self.strategy.value,
            "num_workers": self.num_workers,
            "max_memory_per_worker_mb": self.max_memory_per_worker_mb,
            "worker_timeout": self.worker_timeout,
            "queue_size": self.queue_size,
            "batch_size": self.batch_size,
            "affinity_key_field": self.affinity_key_field,
            "use_shared_memory": self.use_shared_memory,
            "prefetch_factor": self.prefetch_factor,
            "backend_specific": self.backend_specific,
        }
        
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "DistributedConfig":
        """Create configuration from dictionary."""
        # Convert string enum values to enum instances
        if "backend" in config_dict and isinstance(config_dict["backend"], str):
            config_dict["backend"] = DistributionBackend(config_dict["backend"])
            
        if "strategy" in config_dict and isinstance(config_dict["strategy"], str):
            config_dict["strategy"] = DistributionStrategy(config_dict["strategy"])
            
        return cls(**{k: v for k, v in config_dict.items() if k in cls.__annotations__})
        
    def is_local(self) -> bool:
        """Check if the backend is local (processes or threads)."""
        return self.backend in [DistributionBackend.PROCESSES, DistributionBackend.THREADS]
        
    def is_remote(self) -> bool:
        """Check if the backend is remote (distributed across machines)."""
        return not self.is_local()