"""
Distributed processing manager for LightRAG.

This module provides the main interface for configuring and managing distributed processing
in LightRAG, with support for multiple backend types and distribution strategies.
"""

import asyncio
import importlib
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from ..utils import logger
from .config import DistributedConfig, DistributionBackend
from .pool import WorkerPool
from .router import TaskRouter

# Type definitions for better type hinting
T = TypeVar('T')
Task = Dict[str, Any]  # A task object with metadata
WorkerID = str  # Unique identifier for workers
Result = TypeVar('Result')  # Generic task result


class DistributedManager:
    """
    Manager for distributed processing tasks in LightRAG.
    
    This class provides a unified interface for distributing tasks across multiple
    workers using various backend technologies (processes, threads, Ray, Dask, etc.).
    
    Features:
    - Unified API for all supported distribution backends
    - Dynamic worker scaling based on workload
    - Task routing with multiple strategies
    - Task batching for efficiency
    - Comprehensive statistics and monitoring
    """
    
    def __init__(self, config: Optional[DistributedConfig] = None):
        """
        Initialize the distributed manager.
        
        Args:
            config: Configuration for distributed processing
        """
        self.config = config or DistributedConfig()
        self._initialized = False
        self._worker_pool: Optional[WorkerPool] = None
        self._task_router: Optional[TaskRouter] = None
        self._backend_module = None
        self._stats = {
            "tasks_submitted": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "worker_count": 0,
        }
        self._lock = asyncio.Lock()
        
    async def initialize(self) -> bool:
        """
        Initialize the distributed processing system.
        
        This method sets up the backend, worker pool, and task router based on the
        configuration. It must be called before submitting any tasks.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        if self._initialized:
            return True
            
        try:
            async with self._lock:
                if self._initialized:  # Check again within lock
                    return True
                    
                # Skip initialization if distributed processing is disabled
                if not self.config.enabled:
                    logger.info("Distributed processing is disabled. Running in single-process mode.")
                    self._initialized = True
                    return True
                
                # Initialize backend
                await self._init_backend()
                
                # Initialize worker pool
                self._worker_pool = WorkerPool(
                    backend=self._backend_module,
                    num_workers=self.config.num_workers,
                    max_memory_mb=self.config.max_memory_per_worker_mb,
                    worker_timeout=self.config.worker_timeout,
                )
                await self._worker_pool.initialize()
                
                # Initialize task router
                self._task_router = TaskRouter(
                    strategy=self.config.strategy,
                    worker_pool=self._worker_pool,
                    affinity_key_field=self.config.affinity_key_field,
                )
                
                self._stats["worker_count"] = self.config.num_workers
                self._initialized = True
                
                logger.info(
                    f"Distributed processing initialized with {self.config.num_workers} workers "
                    f"using {self.config.backend.value} backend and {self.config.strategy.value} strategy"
                )
                return True
                
        except Exception as e:
            logger.error(f"Failed to initialize distributed processing: {e}")
            return False
            
    async def _init_backend(self) -> None:
        """Initialize the specific backend technology."""
        if self.config.backend == DistributionBackend.PROCESSES:
            # Import the multiprocessing backend
            from .backends import process_backend
            self._backend_module = process_backend
        elif self.config.backend == DistributionBackend.THREADS:
            # Import the threading backend
            from .backends import thread_backend
            self._backend_module = thread_backend
        elif self.config.backend == DistributionBackend.RAY:
            # Dynamic import for optional dependency
            try:
                from .backends import ray_backend
                self._backend_module = ray_backend
                await self._backend_module.initialize(self.config.backend_specific)
            except ImportError:
                raise ImportError(
                    "Ray is not installed. Install with 'pip install ray' to use the Ray backend."
                )
        elif self.config.backend == DistributionBackend.DASK:
            # Dynamic import for optional dependency
            try:
                from .backends import dask_backend
                self._backend_module = dask_backend
                await self._backend_module.initialize(self.config.backend_specific)
            except ImportError:
                raise ImportError(
                    "Dask is not installed. Install with 'pip install dask distributed' "
                    "to use the Dask backend."
                )
        elif self.config.backend == DistributionBackend.CELERY:
            # Dynamic import for optional dependency
            try:
                from .backends import celery_backend
                self._backend_module = celery_backend
                await self._backend_module.initialize(self.config.backend_specific)
            except ImportError:
                raise ImportError(
                    "Celery is not installed. Install with 'pip install celery' "
                    "to use the Celery backend."
                )
        elif self.config.backend == DistributionBackend.REDIS:
            # Dynamic import for optional dependency
            try:
                from .backends import redis_backend
                self._backend_module = redis_backend
                await self._backend_module.initialize(self.config.backend_specific)
            except ImportError:
                raise ImportError(
                    "Redis is not installed. Install with 'pip install redis' "
                    "to use the Redis backend."
                )
        elif self.config.backend == DistributionBackend.CUSTOM:
            # User-provided custom backend
            if "custom_backend_module" not in self.config.backend_specific:
                raise ValueError(
                    "Custom backend requires 'custom_backend_module' in backend_specific config"
                )
                
            module_name = self.config.backend_specific["custom_backend_module"]
            try:
                self._backend_module = importlib.import_module(module_name)
                if hasattr(self._backend_module, "initialize"):
                    await self._backend_module.initialize(self.config.backend_specific)
            except ImportError:
                raise ImportError(f"Failed to import custom backend module: {module_name}")
        else:
            raise ValueError(f"Unsupported backend: {self.config.backend}")
            
    async def submit_task(
        self, 
        func: Callable[..., T], 
        *args, 
        **kwargs
    ) -> asyncio.Future[T]:
        """
        Submit a task for distributed execution.
        
        Args:
            func: Function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Future for the task result
            
        Raises:
            RuntimeError: If the manager is not initialized
        """
        if not self._initialized:
            raise RuntimeError(
                "DistributedManager not initialized. Call initialize() first."
            )
            
        # Create result future
        result_future: asyncio.Future[T] = asyncio.Future()
        
        # Create task object
        task_id = f"task_{self._stats['tasks_submitted']}"
        task = {
            "id": task_id,
            "func": func,
            "args": args,
            "kwargs": kwargs,
            "result_future": result_future,
        }
        
        # Route the task to appropriate worker
        if self._worker_pool and self._task_router:
            worker_id = await self._task_router.route_task(task)
            await self._worker_pool.submit_task(worker_id, task)
            
        # Update statistics
        self._stats["tasks_submitted"] += 1
        
        return result_future
        
    async def submit_batch(
        self, 
        func: Callable[..., T], 
        arg_list: List[Tuple], 
        common_kwargs: Optional[Dict[str, Any]] = None
    ) -> List[asyncio.Future[T]]:
        """
        Submit a batch of similar tasks for distributed execution.
        
        This is more efficient than submitting individual tasks, especially for small tasks.
        
        Args:
            func: Function to execute for all tasks
            arg_list: List of argument tuples, one per task
            common_kwargs: Keyword arguments common to all tasks
            
        Returns:
            List of futures for the task results
            
        Raises:
            RuntimeError: If the manager is not initialized
        """
        if not self._initialized:
            raise RuntimeError(
                "DistributedManager not initialized. Call initialize() first."
            )
            
        futures: List[asyncio.Future[T]] = []
        common_kwargs = common_kwargs or {}
        
        # Create tasks
        tasks = []
        for i, args in enumerate(arg_list):
            result_future: asyncio.Future[T] = asyncio.Future()
            futures.append(result_future)
            
            task_id = f"batch_{self._stats['tasks_submitted']}_{i}"
            task = {
                "id": task_id,
                "func": func,
                "args": args,
                "kwargs": common_kwargs.copy(),
                "result_future": result_future,
                "batch_index": i,
            }
            tasks.append(task)
            
        # Use batch routing for better efficiency
        if self._worker_pool and self._task_router:
            worker_assignments = await self._task_router.route_batch(tasks)
            
            # Group tasks by worker
            worker_tasks: Dict[str, List[Dict]] = {}
            for task, worker_id in zip(tasks, worker_assignments):
                if worker_id not in worker_tasks:
                    worker_tasks[worker_id] = []
                worker_tasks[worker_id].append(task)
                
            # Submit task groups to workers
            await asyncio.gather(*[
                self._worker_pool.submit_batch(worker_id, worker_tasks[worker_id])
                for worker_id in worker_tasks
            ])
            
        # Update statistics
        self._stats["tasks_submitted"] += len(tasks)
        
        return futures
        
    async def map(
        self, 
        func: Callable[[T], Result], 
        items: List[T]
    ) -> List[Result]:
        """
        Apply a function to each item in a list, distributing the work.
        
        Args:
            func: Function to apply to each item
            items: List of items to process
            
        Returns:
            List of results in the same order as the input items
            
        Raises:
            RuntimeError: If the manager is not initialized
        """
        if not items:
            return []
            
        if not self._initialized:
            raise RuntimeError(
                "DistributedManager not initialized. Call initialize() first."
            )
            
        # Create argument tuples for submit_batch
        arg_list = [(item,) for item in items]
        
        # Submit batch
        futures = await self.submit_batch(func, arg_list)
        
        # Wait for all futures to complete
        results = await asyncio.gather(*futures)
        
        return results
        
    async def scale_workers(self, num_workers: int) -> bool:
        """
        Scale the worker pool to a specific number of workers.
        
        Args:
            num_workers: Target number of workers
            
        Returns:
            True if scaling was successful, False otherwise
            
        Raises:
            RuntimeError: If the manager is not initialized
        """
        if not self._initialized:
            raise RuntimeError(
                "DistributedManager not initialized. Call initialize() first."
            )
            
        if not self._worker_pool:
            return False
            
        try:
            result = await self._worker_pool.scale(num_workers)
            if result:
                self._stats["worker_count"] = num_workers
            return result
        except Exception as e:
            logger.error(f"Failed to scale worker pool: {e}")
            return False
            
    async def shutdown(self) -> None:
        """
        Shutdown the distributed processing system.
        
        This method stops all workers and cleans up resources. It should be called
        when distributed processing is no longer needed.
        """
        if not self._initialized:
            return
            
        async with self._lock:
            if self._worker_pool:
                await self._worker_pool.shutdown()
                self._worker_pool = None
                
            # Clean up backend
            if self._backend_module and hasattr(self._backend_module, "shutdown"):
                await self._backend_module.shutdown()
                
            self._initialized = False
            logger.info("Distributed processing system shut down")
            
    @property
    def stats(self) -> Dict[str, Any]:
        """Get statistics about the distributed processing system."""
        if not self._initialized:
            return {"status": "not_initialized", **self._stats}
            
        stats = {**self._stats}
        
        # Add worker pool stats if available
        if self._worker_pool:
            stats.update(self._worker_pool.stats)
            
        return stats


# Global instance for simplified access
_global_manager: Optional[DistributedManager] = None


def get_manager() -> Optional[DistributedManager]:
    """Get the global distributed manager instance."""
    return _global_manager


async def initialize_distributed(config: Optional[DistributedConfig] = None) -> DistributedManager:
    """
    Initialize the global distributed manager.
    
    Args:
        config: Configuration for distributed processing
        
    Returns:
        The initialized distributed manager
    """
    global _global_manager
    
    if _global_manager is None:
        _global_manager = DistributedManager(config)
        
    if not _global_manager._initialized:
        await _global_manager.initialize()
        
    return _global_manager