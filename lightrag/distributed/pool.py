"""
Worker pool implementation for distributed processing.

This module provides a worker pool that manages multiple workers across different
distributed backend technologies.
"""

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional, TypeVar

from ..utils import logger


WorkerID = str
TaskID = str
T = TypeVar('T')


class WorkerPool:
    """
    Manages a pool of workers for distributed task processing.
    
    This class abstracts worker management across different backend technologies,
    handling worker lifecycle, health monitoring, and task assignment.
    """
    
    def __init__(
        self,
        backend: Any,
        num_workers: int = 4,
        max_memory_mb: Optional[int] = None,
        worker_timeout: int = 3600,
    ):
        """
        Initialize a worker pool.
        
        Args:
            backend: Backend module for worker management
            num_workers: Initial number of workers
            max_memory_mb: Maximum memory per worker in megabytes
            worker_timeout: Worker timeout in seconds
        """
        self.backend = backend
        self.target_num_workers = num_workers
        self.max_memory_mb = max_memory_mb
        self.worker_timeout = worker_timeout
        self._workers: Dict[WorkerID, Dict[str, Any]] = {}
        self._initialized = False
        self._lock = asyncio.Lock()
        self._task_assignments: Dict[TaskID, WorkerID] = {}
        self._stats = {
            "active_workers": 0,
            "idle_workers": 0,
            "busy_workers": 0,
            "tasks_queued": 0,
            "tasks_processing": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "avg_task_time_ms": 0,
        }
        
    async def initialize(self) -> None:
        """
        Initialize the worker pool and start workers.
        
        This method starts the initial set of workers and sets up monitoring.
        """
        if self._initialized:
            return
            
        async with self._lock:
            if self._initialized:
                return
                
            # Initialize the backend
            if hasattr(self.backend, "initialize_pool"):
                await self.backend.initialize_pool()
                
            # Start initial workers
            for _ in range(self.target_num_workers):
                await self._start_worker()
                
            # Start monitoring
            asyncio.create_task(self._monitor_workers())
            
            self._initialized = True
            logger.info(f"Worker pool initialized with {len(self._workers)} workers")
            
    async def _start_worker(self) -> WorkerID:
        """
        Start a new worker.
        
        Returns:
            ID of the new worker
        """
        worker_id = f"worker_{uuid.uuid4().hex[:8]}"
        
        # Create worker with backend-specific implementation
        worker_info = await self.backend.create_worker(
            worker_id, 
            max_memory_mb=self.max_memory_mb
        )
        
        # Initialize worker metadata
        self._workers[worker_id] = {
            "id": worker_id,
            "info": worker_info,
            "status": "idle",
            "start_time": time.time(),
            "last_heartbeat": time.time(),
            "tasks_processed": 0,
            "tasks_failed": 0,
            "tasks_queue": 0,
            "current_tasks": set(),
            "avg_task_time": 0,
        }
        
        self._stats["active_workers"] += 1
        self._stats["idle_workers"] += 1
        
        logger.debug(f"Worker {worker_id} started")
        return worker_id
        
    async def _stop_worker(self, worker_id: WorkerID) -> bool:
        """
        Stop a worker.
        
        Args:
            worker_id: ID of the worker to stop
            
        Returns:
            True if worker was stopped successfully, False otherwise
        """
        if worker_id not in self._workers:
            return False
            
        try:
            # Stop worker with backend-specific implementation
            await self.backend.stop_worker(worker_id, self._workers[worker_id]["info"])
            
            # Update statistics
            worker_status = self._workers[worker_id]["status"]
            self._stats["active_workers"] -= 1
            if worker_status == "idle":
                self._stats["idle_workers"] -= 1
            elif worker_status == "busy":
                self._stats["busy_workers"] -= 1
                
            # Remove worker from pool
            del self._workers[worker_id]
            
            logger.debug(f"Worker {worker_id} stopped")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop worker {worker_id}: {e}")
            return False
            
    async def submit_task(self, worker_id: WorkerID, task: Dict[str, Any]) -> bool:
        """
        Submit a task to a specific worker.
        
        Args:
            worker_id: ID of the target worker
            task: Task to submit
            
        Returns:
            True if task was submitted successfully, False otherwise
        """
        if not self._initialized:
            logger.error("Worker pool not initialized")
            if task.get("result_future") and not task["result_future"].done():
                task["result_future"].set_exception(
                    RuntimeError("Worker pool not initialized")
                )
            return False
            
        if worker_id not in self._workers:
            logger.error(f"Worker {worker_id} not found")
            if task.get("result_future") and not task["result_future"].done():
                task["result_future"].set_exception(
                    RuntimeError(f"Worker {worker_id} not found")
                )
            return False
            
        # Track task assignment
        task_id = task["id"]
        self._task_assignments[task_id] = worker_id
        
        # Update worker status
        async with self._lock:
            worker = self._workers[worker_id]
            worker["current_tasks"].add(task_id)
            worker["tasks_queue"] += 1
            worker["status"] = "busy"
            
            # Update stats
            self._stats["tasks_queued"] += 1
            if worker["status"] == "idle":
                self._stats["idle_workers"] -= 1
                self._stats["busy_workers"] += 1
                
        # Submit task with backend-specific implementation
        try:
            success = await self.backend.submit_task(
                worker_id, 
                worker["info"], 
                task,
                self._on_task_complete,
                self._on_task_failed,
            )
            
            if not success and task.get("result_future") and not task["result_future"].done():
                task["result_future"].set_exception(
                    RuntimeError(f"Failed to submit task to worker {worker_id}")
                )
                
            return success
            
        except Exception as e:
            logger.error(f"Error submitting task to worker {worker_id}: {e}")
            if task.get("result_future") and not task["result_future"].done():
                task["result_future"].set_exception(e)
            return False
            
    async def submit_batch(self, worker_id: WorkerID, tasks: List[Dict[str, Any]]) -> bool:
        """
        Submit a batch of tasks to a specific worker.
        
        This is more efficient than submitting individual tasks, as it can
        reduce overhead in task creation and submission.
        
        Args:
            worker_id: ID of the target worker
            tasks: List of tasks to submit
            
        Returns:
            True if all tasks were submitted successfully, False otherwise
        """
        if not self._initialized:
            logger.error("Worker pool not initialized")
            for task in tasks:
                if task.get("result_future") and not task["result_future"].done():
                    task["result_future"].set_exception(
                        RuntimeError("Worker pool not initialized")
                    )
            return False
            
        if worker_id not in self._workers:
            logger.error(f"Worker {worker_id} not found")
            for task in tasks:
                if task.get("result_future") and not task["result_future"].done():
                    task["result_future"].set_exception(
                        RuntimeError(f"Worker {worker_id} not found")
                    )
            return False
            
        # Track task assignments
        for task in tasks:
            task_id = task["id"]
            self._task_assignments[task_id] = worker_id
            
        # Update worker status
        async with self._lock:
            worker = self._workers[worker_id]
            for task in tasks:
                worker["current_tasks"].add(task["id"])
            worker["tasks_queue"] += len(tasks)
            worker["status"] = "busy"
            
            # Update stats
            self._stats["tasks_queued"] += len(tasks)
            if worker["status"] == "idle":
                self._stats["idle_workers"] -= 1
                self._stats["busy_workers"] += 1
                
        # Submit batch with backend-specific implementation
        # If backend doesn't support batch submission, fall back to individual submissions
        try:
            if hasattr(self.backend, "submit_batch"):
                success = await self.backend.submit_batch(
                    worker_id,
                    worker["info"],
                    tasks,
                    self._on_task_complete,
                    self._on_task_failed,
                )
                
                if not success:
                    for task in tasks:
                        if task.get("result_future") and not task["result_future"].done():
                            task["result_future"].set_exception(
                                RuntimeError(f"Failed to submit task batch to worker {worker_id}")
                            )
                            
                return success
            else:
                # Fall back to individual submissions
                results = await asyncio.gather(*[
                    self.backend.submit_task(
                        worker_id,
                        worker["info"],
                        task,
                        self._on_task_complete,
                        self._on_task_failed,
                    )
                    for task in tasks
                ])
                
                # Check if all submissions were successful
                all_successful = all(results)
                
                if not all_successful:
                    for task, success in zip(tasks, results):
                        if not success and task.get("result_future") and not task["result_future"].done():
                            task["result_future"].set_exception(
                                RuntimeError(f"Failed to submit task to worker {worker_id}")
                            )
                            
                return all_successful
                
        except Exception as e:
            logger.error(f"Error submitting task batch to worker {worker_id}: {e}")
            for task in tasks:
                if task.get("result_future") and not task["result_future"].done():
                    task["result_future"].set_exception(e)
            return False
    
    def _on_task_complete(self, task_id: TaskID, result: Any) -> None:
        """
        Callback for task completion.
        
        Args:
            task_id: ID of the completed task
            result: Task result
        """
        if task_id not in self._task_assignments:
            logger.warning(f"Received completion for unknown task {task_id}")
            return
            
        worker_id = self._task_assignments[task_id]
        
        # Update worker status
        worker = self._workers.get(worker_id)
        if worker:
            worker["tasks_processed"] += 1
            worker["current_tasks"].discard(task_id)
            worker["tasks_queue"] = max(0, worker["tasks_queue"] - 1)
            worker["last_heartbeat"] = time.time()
            
            # Update status if queue is empty
            if worker["tasks_queue"] == 0:
                worker["status"] = "idle"
                self._stats["busy_workers"] -= 1
                self._stats["idle_workers"] += 1
                
        # Update stats
        self._stats["tasks_processing"] = max(0, self._stats["tasks_processing"] - 1)
        self._stats["tasks_completed"] += 1
        
        # Remove task assignment
        del self._task_assignments[task_id]
        
        # Complete future if available
        task = getattr(result, "task", None)
        if task and task.get("result_future") and not task["result_future"].done():
            task["result_future"].set_result(result)
            
    def _on_task_failed(self, task_id: TaskID, error: Exception) -> None:
        """
        Callback for task failure.
        
        Args:
            task_id: ID of the failed task
            error: Task error
        """
        if task_id not in self._task_assignments:
            logger.warning(f"Received failure for unknown task {task_id}")
            return
            
        worker_id = self._task_assignments[task_id]
        
        # Update worker status
        worker = self._workers.get(worker_id)
        if worker:
            worker["tasks_failed"] += 1
            worker["current_tasks"].discard(task_id)
            worker["tasks_queue"] = max(0, worker["tasks_queue"] - 1)
            worker["last_heartbeat"] = time.time()
            
            # Update status if queue is empty
            if worker["tasks_queue"] == 0:
                worker["status"] = "idle"
                self._stats["busy_workers"] -= 1
                self._stats["idle_workers"] += 1
                
        # Update stats
        self._stats["tasks_processing"] = max(0, self._stats["tasks_processing"] - 1)
        self._stats["tasks_failed"] += 1
        
        # Remove task assignment
        del self._task_assignments[task_id]
        
        # Complete future if available
        if hasattr(error, "task") and getattr(error, "task", None) is not None:
            task = error.task
            if task.get("result_future") and not task["result_future"].done():
                task["result_future"].set_exception(error)
        else:
            logger.error(f"Task {task_id} failed with error: {error}")
            
    async def _monitor_workers(self) -> None:
        """
        Monitor worker health and handle failures.
        
        This coroutine runs periodically to check worker health, restart failed
        workers, and scale the pool as needed.
        """
        while self._initialized:
            try:
                current_time = time.time()
                
                # Check worker health
                workers_to_restart = []
                for worker_id, worker in list(self._workers.items()):
                    # Check if worker is healthy
                    try:
                        is_healthy = await self.backend.check_worker_health(worker_id, worker["info"])
                        
                        # Handle unhealthy workers
                        if not is_healthy:
                            workers_to_restart.append(worker_id)
                            logger.warning(f"Worker {worker_id} is unhealthy and will be restarted")
                            continue
                            
                        # Check for timeout
                        last_heartbeat = worker.get("last_heartbeat", worker["start_time"])
                        if current_time - last_heartbeat > self.worker_timeout:
                            workers_to_restart.append(worker_id)
                            logger.warning(f"Worker {worker_id} timed out and will be restarted")
                            continue
                            
                    except Exception as e:
                        logger.error(f"Error checking health of worker {worker_id}: {e}")
                        workers_to_restart.append(worker_id)
                    
                # Restart unhealthy workers
                for worker_id in workers_to_restart:
                    await self._restart_worker(worker_id)
                
                # Scale pool if needed
                num_workers = len(self._workers)
                if num_workers < self.target_num_workers:
                    # Start new workers
                    for _ in range(self.target_num_workers - num_workers):
                        await self._start_worker()
                elif num_workers > self.target_num_workers:
                    # Find idle workers to stop
                    idle_workers = [
                        worker_id
                        for worker_id, worker in self._workers.items()
                        if worker["status"] == "idle"
                    ]
                    
                    # Stop excess idle workers
                    excess_count = min(len(idle_workers), num_workers - self.target_num_workers)
                    for i in range(excess_count):
                        await self._stop_worker(idle_workers[i])
                
                # Update statistics
                self._update_stats()
                
                # Wait before next check
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Error in worker monitoring: {e}")
                await asyncio.sleep(30)  # Longer delay on error
                
    async def _restart_worker(self, worker_id: WorkerID) -> Optional[WorkerID]:
        """
        Restart a worker and reassign its tasks.
        
        Args:
            worker_id: ID of the worker to restart
            
        Returns:
            ID of the new worker, or None if restart failed
        """
        if worker_id not in self._workers:
            return None
            
        try:
            # Get tasks from the worker
            worker = self._workers[worker_id]
            task_ids = list(worker["current_tasks"])
            
            # Stop the worker
            await self._stop_worker(worker_id)
            
            # Start a new worker
            new_worker_id = await self._start_worker()
            
            # Handle unfinished tasks
            for task_id in task_ids:
                if task_id in self._task_assignments:
                    # Mark task as failed
                    error = RuntimeError(f"Task {task_id} failed due to worker restart")
                    self._on_task_failed(task_id, error)
                    
            return new_worker_id
            
        except Exception as e:
            logger.error(f"Failed to restart worker {worker_id}: {e}")
            return None
            
    async def scale(self, num_workers: int) -> bool:
        """
        Scale the worker pool to a specific number of workers.
        
        Args:
            num_workers: Target number of workers
            
        Returns:
            True if scaling was successful, False otherwise
        """
        if not self._initialized:
            logger.error("Worker pool not initialized")
            return False
            
        # Update target number of workers
        self.target_num_workers = max(1, num_workers)
        
        # Scaling will happen during the next monitoring cycle
        logger.info(f"Worker pool scaling to {self.target_num_workers} workers")
        return True
        
    async def shutdown(self) -> None:
        """
        Shutdown the worker pool and all workers.
        
        This method stops all workers and cleans up resources. It should be called
        when the worker pool is no longer needed.
        """
        if not self._initialized:
            return
            
        self._initialized = False
        
        # Stop all workers
        for worker_id in list(self._workers.keys()):
            await self._stop_worker(worker_id)
            
        # Shutdown backend
        if hasattr(self.backend, "shutdown_pool"):
            await self.backend.shutdown_pool()
            
        logger.info("Worker pool shut down")
        
    def _update_stats(self) -> None:
        """Update statistics about the worker pool."""
        # Count workers by status
        idle_workers = 0
        busy_workers = 0
        
        for worker in self._workers.values():
            if worker["status"] == "idle":
                idle_workers += 1
            elif worker["status"] == "busy":
                busy_workers += 1
                
        self._stats.update({
            "active_workers": len(self._workers),
            "idle_workers": idle_workers,
            "busy_workers": busy_workers,
        })
        
    @property
    def stats(self) -> Dict[str, Any]:
        """Get statistics about the worker pool."""
        return dict(self._stats)
        
    @property
    def workers(self) -> Dict[WorkerID, Dict[str, Any]]:
        """Get information about all workers."""
        return {worker_id: worker.copy() for worker_id, worker in self._workers.items()}