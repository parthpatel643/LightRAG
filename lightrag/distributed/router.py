"""
Task routing for distributed processing.

This module provides task routing strategies to efficiently distribute tasks
across workers based on different criteria like load balancing, content affinity, etc.
"""

import hashlib
from typing import Any, Dict, List

from .config import DistributionStrategy


class TaskRouter:
    """
    Routes tasks to appropriate workers using configurable strategies.
    
    This class implements different routing strategies like round-robin,
    load-based, and content affinity to efficiently distribute tasks.
    """
    
    def __init__(
        self,
        strategy: DistributionStrategy,
        worker_pool,
        affinity_key_field: str = "doc_id",
    ):
        """
        Initialize the task router.
        
        Args:
            strategy: Routing strategy to use
            worker_pool: Worker pool to route tasks to
            affinity_key_field: Field in task metadata used for content affinity
        """
        self.strategy = strategy
        self.worker_pool = worker_pool
        self.affinity_key_field = affinity_key_field
        self._last_worker_index = 0
        self._affinity_mappings = {}  # Maps content keys to worker IDs
        
    async def route_task(self, task: Dict[str, Any]) -> str:
        """
        Route a single task to an appropriate worker.
        
        Args:
            task: Task to route
            
        Returns:
            ID of the selected worker
            
        Raises:
            ValueError: If no workers are available
        """
        # Get available workers
        workers = self.worker_pool.workers
        
        if not workers:
            raise ValueError("No workers available for task routing")
            
        worker_ids = list(workers.keys())
        
        # Apply routing strategy
        if self.strategy == DistributionStrategy.ROUND_ROBIN:
            return self._round_robin_route(worker_ids)
            
        elif self.strategy == DistributionStrategy.LOAD_BASED:
            return self._load_based_route(workers)
            
        elif self.strategy == DistributionStrategy.CONTENT_HASH:
            return self._content_hash_route(task, worker_ids)
            
        elif self.strategy == DistributionStrategy.PRIORITY:
            return self._priority_route(task, workers)
            
        else:  # Default to round robin
            return self._round_robin_route(worker_ids)
            
    async def route_batch(self, tasks: List[Dict[str, Any]]) -> List[str]:
        """
        Route a batch of tasks to appropriate workers.
        
        This method is more efficient than routing tasks individually, as it
        can optimize the distribution of the entire batch at once.
        
        Args:
            tasks: List of tasks to route
            
        Returns:
            List of worker IDs for each task
            
        Raises:
            ValueError: If no workers are available
        """
        # Get available workers
        workers = self.worker_pool.workers
        
        if not workers:
            raise ValueError("No workers available for task routing")
            
        worker_ids = list(workers.keys())
        
        # Apply routing strategy
        if self.strategy == DistributionStrategy.ROUND_ROBIN:
            return [self._round_robin_route(worker_ids) for _ in tasks]
            
        elif self.strategy == DistributionStrategy.LOAD_BASED:
            return self._batch_load_based_route(tasks, workers)
            
        elif self.strategy == DistributionStrategy.CONTENT_HASH:
            return [self._content_hash_route(task, worker_ids) for task in tasks]
            
        elif self.strategy == DistributionStrategy.PRIORITY:
            return [self._priority_route(task, workers) for task in tasks]
            
        else:  # Default to round robin
            return [self._round_robin_route(worker_ids) for _ in tasks]
            
    def _round_robin_route(self, worker_ids: List[str]) -> str:
        """
        Route tasks in a round-robin fashion.
        
        Args:
            worker_ids: List of available worker IDs
            
        Returns:
            Selected worker ID
        """
        if not worker_ids:
            raise ValueError("No workers available")
            
        # Get the next worker in round-robin fashion
        worker_id = worker_ids[self._last_worker_index % len(worker_ids)]
        
        # Update the index for next time
        self._last_worker_index = (self._last_worker_index + 1) % len(worker_ids)
        
        return worker_id
        
    def _load_based_route(self, workers: Dict[str, Dict[str, Any]]) -> str:
        """
        Route tasks based on worker load.
        
        Args:
            workers: Dictionary of worker information
            
        Returns:
            Selected worker ID
        """
        if not workers:
            raise ValueError("No workers available")
            
        # Find the worker with the lowest queue size
        worker_id = min(
            workers.keys(),
            key=lambda wid: workers[wid]["tasks_queue"]
        )
        
        return worker_id
        
    def _batch_load_based_route(
        self, 
        tasks: List[Dict[str, Any]],
        workers: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        """
        Route a batch of tasks based on worker load.
        
        This method optimizes the distribution of the entire batch to minimize
        load imbalance across workers.
        
        Args:
            tasks: List of tasks to route
            workers: Dictionary of worker information
            
        Returns:
            List of worker IDs for each task
        """
        if not workers:
            raise ValueError("No workers available")
            
        # Create a copy of worker loads to track simulated assignment
        worker_loads = {wid: workers[wid]["tasks_queue"] for wid in workers}
        
        # Assign tasks to workers
        assignments = []
        for task in tasks:
            # Find worker with lowest load
            worker_id = min(
                worker_loads.keys(),
                key=lambda wid: worker_loads[wid]
            )
            
            # Update simulated load
            worker_loads[worker_id] += 1
            
            assignments.append(worker_id)
            
        return assignments
        
    def _content_hash_route(self, task: Dict[str, Any], worker_ids: List[str]) -> str:
        """
        Route tasks based on content affinity.
        
        This method ensures related tasks (based on content key) are routed to
        the same worker for better locality.
        
        Args:
            task: Task to route
            worker_ids: List of available worker IDs
            
        Returns:
            Selected worker ID
        """
        if not worker_ids:
            raise ValueError("No workers available")
            
        # Get content key from task
        content_key = None
        kwargs = task.get("kwargs", {})
        
        # Check in kwargs first
        if self.affinity_key_field in kwargs:
            content_key = kwargs[self.affinity_key_field]
        # Then check in the task itself
        elif self.affinity_key_field in task:
            content_key = task[self.affinity_key_field]
        
        # If no content key found, use round robin
        if not content_key:
            return self._round_robin_route(worker_ids)
            
        # Convert content key to string
        content_key_str = str(content_key)
        
        # Check if we already have a mapping for this content key
        if content_key_str in self._affinity_mappings:
            worker_id = self._affinity_mappings[content_key_str]
            
            # Check if the worker still exists
            if worker_id in worker_ids:
                return worker_id
                
        # Create new mapping using hash
        hash_val = int(hashlib.md5(content_key_str.encode()).hexdigest(), 16)
        worker_index = hash_val % len(worker_ids)
        worker_id = worker_ids[worker_index]
        
        # Store mapping for future use
        self._affinity_mappings[content_key_str] = worker_id
        
        return worker_id
        
    def _priority_route(self, task: Dict[str, Any], workers: Dict[str, Dict[str, Any]]) -> str:
        """
        Route tasks based on priority.
        
        This method routes high-priority tasks to less busy workers and
        low-priority tasks to more busy workers.
        
        Args:
            task: Task to route
            workers: Dictionary of worker information
            
        Returns:
            Selected worker ID
        """
        if not workers:
            raise ValueError("No workers available")
            
        # Get task priority (default to normal)
        priority = task.get("priority", 5)  # 1-10 scale, 10 being highest
        
        # For high-priority tasks, use less busy workers
        if priority > 7:
            # Find least busy worker
            worker_id = min(
                workers.keys(),
                key=lambda wid: workers[wid]["tasks_queue"]
            )
        # For normal-priority tasks, use load-based routing
        elif 3 <= priority <= 7:
            worker_id = self._load_based_route(workers)
        # For low-priority tasks, use more busy workers
        else:
            # Find moderately busy worker (not the most busy to avoid overload)
            sorted_workers = sorted(
                workers.keys(),
                key=lambda wid: workers[wid]["tasks_queue"]
            )
            
            # Use worker at 2/3 of the sorted list (busy but not overwhelmed)
            index = min(len(sorted_workers) - 1, int(len(sorted_workers) * 2 / 3))
            worker_id = sorted_workers[index]
            
        return worker_id
        
    def update_strategy(self, strategy: DistributionStrategy) -> None:
        """
        Update the routing strategy.
        
        Args:
            strategy: New routing strategy to use
        """
        self.strategy = strategy
        
        # Reset any strategy-specific state
        if strategy != DistributionStrategy.CONTENT_HASH:
            self._affinity_mappings = {}