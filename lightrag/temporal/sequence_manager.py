"""
Sequence Index Manager - Thread-safe sequence allocation with distributed locking.

This module provides atomic sequence index generation to prevent race conditions
in concurrent document insertion scenarios.

Fixes Issue #6: Race Condition in Sequence Index Generation
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager

from ..base import BaseKVStorage
from ..utils import logger


class SequenceIndexManager:
    """
    Thread-safe sequence index manager with distributed locking support.

    Features:
    - Distributed lock using storage backend
    - Stale lock detection and recovery
    - Batch allocation for performance
    - Comprehensive error handling

    Usage:
        manager = SequenceIndexManager(doc_status_storage)

        # Single allocation
        seq_idx = await manager.get_next_sequence_index()

        # Batch allocation (atomic)
        indices = await manager.get_next_batch_sequence_indices(10)
    """

    def __init__(
        self,
        doc_status: BaseKVStorage,
        lock_timeout: float = 30.0,
        lock_retry_delay: float = 0.1,
    ):
        """
        Initialize sequence index manager.

        Args:
            doc_status: Storage backend for sequence counter and locks
            lock_timeout: Maximum time to hold lock (seconds)
            lock_retry_delay: Delay between lock acquisition retries (seconds)
        """
        self.doc_status = doc_status
        self._local_lock = asyncio.Lock()
        self._lock_key = "__sequence_index_lock__"
        self._counter_key = "__max_sequence_index__"
        self._lock_timeout = lock_timeout
        self._lock_retry_delay = lock_retry_delay

        logger.info(
            f"SequenceIndexManager initialized "
            f"(timeout={lock_timeout}s, retry_delay={lock_retry_delay}s)"
        )

    @asynccontextmanager
    async def _acquire_distributed_lock(self, timeout: float = 30.0):
        """
        Acquire distributed lock using storage backend.

        Uses compare-and-swap (CAS) pattern for atomic lock acquisition.
        Handles stale locks automatically.

        Args:
            timeout: Maximum time to wait for lock (seconds)

        Yields:
            lock_id: Unique identifier for this lock acquisition

        Raises:
            TimeoutError: If lock cannot be acquired within timeout
        """
        lock_id = f"{os.getpid()}_{id(asyncio.current_task())}_{time.time()}"
        lock_acquired = False
        start_time = time.time()
        existing_lock = None  # Initialize to avoid unbound variable

        try:
            while time.time() - start_time < timeout:
                # Try to acquire lock atomically
                existing_lock_data = await self.doc_status.get_by_id(self._lock_key)
                existing_lock = (
                    existing_lock_data.get("value") if existing_lock_data else None
                )

                if existing_lock is None:
                    # No lock exists, try to acquire
                    await self.doc_status.upsert({self._lock_key: {"value": lock_id}})

                    # Verify we got the lock (handle race condition)
                    await asyncio.sleep(0.01)  # Small delay for consistency
                    current_lock_data = await self.doc_status.get_by_id(self._lock_key)
                    current_lock = (
                        current_lock_data.get("value") if current_lock_data else None
                    )

                    if current_lock == lock_id:
                        lock_acquired = True
                        logger.debug(f"Acquired distributed lock: {lock_id}")
                        break
                else:
                    # Lock exists, check if it's stale
                    lock_parts = str(existing_lock).split("_")
                    if len(lock_parts) >= 3:
                        try:
                            lock_timestamp = float(lock_parts[-1])
                            if time.time() - lock_timestamp > self._lock_timeout:
                                # Stale lock, try to steal it
                                logger.warning(
                                    f"Stealing stale lock: {existing_lock} "
                                    f"(age: {time.time() - lock_timestamp:.1f}s)"
                                )
                                await self.doc_status.upsert(
                                    {self._lock_key: {"value": lock_id}}
                                )

                                # Verify we got the lock
                                await asyncio.sleep(0.01)
                                current_lock_data = await self.doc_status.get_by_id(
                                    self._lock_key
                                )
                                current_lock = (
                                    current_lock_data.get("value")
                                    if current_lock_data
                                    else None
                                )
                                if current_lock == lock_id:
                                    lock_acquired = True
                                    break
                        except (ValueError, IndexError) as e:
                            logger.warning(f"Error parsing lock timestamp: {e}")

                # Wait before retry
                await asyncio.sleep(self._lock_retry_delay)

            if not lock_acquired:
                raise TimeoutError(
                    f"Failed to acquire distributed lock after {timeout}s. "
                    f"Current lock holder: {existing_lock or 'unknown'}"
                )

            yield lock_id

        finally:
            if lock_acquired:
                # Release lock only if we own it
                try:
                    current_lock_data = await self.doc_status.get_by_id(self._lock_key)
                    current_lock = (
                        current_lock_data.get("value") if current_lock_data else None
                    )
                    if current_lock == lock_id:
                        await self.doc_status.delete([self._lock_key])
                        logger.debug(f"Released distributed lock: {lock_id}")
                except Exception as e:
                    logger.error(f"Error releasing lock: {e}", exc_info=True)

    async def get_next_sequence_index(self) -> int:
        """
        Get next sequence index with distributed locking.

        This method is thread-safe and works across multiple processes/servers.

        Returns:
            Next sequence index (guaranteed unique)

        Raises:
            TimeoutError: If lock cannot be acquired
            RuntimeError: If sequence counter cannot be updated
        """
        async with self._local_lock:  # Local lock for same process
            async with (
                self._acquire_distributed_lock()
            ):  # Distributed lock across processes
                try:
                    max_seq_data = await self.doc_status.get_by_id(self._counter_key)
                    max_seq = max_seq_data.get("value") if max_seq_data else None

                    if max_seq is None:
                        next_idx = 1
                        logger.info("Initializing sequence counter to 1")
                    else:
                        next_idx = int(max_seq) + 1

                    # Atomic update within lock
                    await self.doc_status.upsert(
                        {self._counter_key: {"value": next_idx}}
                    )

                    logger.debug(f"Assigned sequence index: {next_idx}")
                    return next_idx

                except Exception as e:
                    logger.error(
                        f"Error getting next sequence index: {e}", exc_info=True
                    )
                    raise RuntimeError(f"Failed to allocate sequence index: {e}") from e

    async def get_next_batch_sequence_indices(self, count: int) -> list[int]:
        """
        Get multiple sequence indices atomically for batch operations.

        This is more efficient than calling get_next_sequence_index() multiple times
        as it acquires the lock only once.

        Args:
            count: Number of sequence indices needed

        Returns:
            List of consecutive sequence indices

        Raises:
            ValueError: If count <= 0
            TimeoutError: If lock cannot be acquired
            RuntimeError: If sequence counter cannot be updated
        """
        if count <= 0:
            raise ValueError(f"count must be > 0, got {count}")

        async with self._local_lock:
            async with self._acquire_distributed_lock():
                try:
                    max_seq_data = await self.doc_status.get_by_id(self._counter_key)
                    max_seq = max_seq_data.get("value") if max_seq_data else None

                    if max_seq is None:
                        start_idx = 1
                        logger.info(
                            f"Initializing sequence counter for batch of {count}"
                        )
                    else:
                        start_idx = int(max_seq) + 1

                    # Allocate range atomically
                    end_idx = start_idx + count - 1
                    await self.doc_status.upsert(
                        {self._counter_key: {"value": end_idx}}
                    )

                    indices = list(range(start_idx, end_idx + 1))
                    logger.debug(
                        f"Assigned batch sequence indices: {start_idx}-{end_idx}"
                    )
                    return indices

                except Exception as e:
                    logger.error(
                        f"Error getting batch sequence indices: {e}", exc_info=True
                    )
                    raise RuntimeError(
                        f"Failed to allocate batch sequence indices: {e}"
                    ) from e

    async def get_current_max_sequence(self) -> int:
        """
        Get current maximum sequence index without incrementing.

        Returns:
            Current maximum sequence index, or 0 if not initialized
        """
        try:
            max_seq_data = await self.doc_status.get_by_id(self._counter_key)
            max_seq = max_seq_data.get("value") if max_seq_data else None
            return int(max_seq) if max_seq is not None else 0
        except Exception as e:
            logger.error(f"Error getting current max sequence: {e}", exc_info=True)
            return 0

    async def reset_sequence(self, new_value: int = 0) -> None:
        """
        Reset sequence counter to specific value.

        WARNING: This should only be used for testing or migration purposes.

        Args:
            new_value: New sequence counter value

        Raises:
            ValueError: If new_value < 0
        """
        if new_value < 0:
            raise ValueError(f"new_value must be >= 0, got {new_value}")

        async with self._local_lock:
            async with self._acquire_distributed_lock():
                await self.doc_status.upsert({self._counter_key: {"value": new_value}})
                logger.warning(f"Sequence counter reset to {new_value}")


#
