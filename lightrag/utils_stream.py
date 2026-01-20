from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Callable, List, Optional, Tuple, TypeVar

from .utils import logger

T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')

class AsyncStreamBuffer:
    """
    Buffer for processing streaming data with windowing and sliding techniques.
    
    This class provides efficient processing of streaming data with configurable
    window sizes and step sizes, allowing for overlapping windows or skipped data.
    
    Features:
    - Configurable window size and step size
    - Support for overlapping windows (when step_size < window_size)
    - In-place processing to minimize memory copies
    - Streaming processing to avoid loading entire dataset into memory
    
    Usage:
        buffer = AsyncStreamBuffer(window_size=10, step_size=5)
        
        # Add data incrementally
        await buffer.add_items([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        
        # Process complete windows as they become available
        async for window in buffer:
            print(window)  # [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
            
        # Add more data
        await buffer.add_items([11, 12, 13, 14, 15])
        
        # Get next window with step_size=5
        async for window in buffer:
            print(window)  # [6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    """
    
    def __init__(self, window_size: int = 10, step_size: Optional[int] = None):
        """
        Initialize the stream buffer.
        
        Args:
            window_size: Number of items in each processing window
            step_size: Number of items to advance window each time.
                       If None, defaults to window_size (non-overlapping windows)
        """
        self.window_size = window_size
        self.step_size = step_size or window_size
        self.buffer: List[Any] = []
        self._window_ready = asyncio.Event()
        self._closed = False
        
    async def add_items(self, items: List[Any]) -> None:
        """
        Add multiple items to the buffer.
        
        Args:
            items: List of items to add
        """
        if self._closed:
            raise RuntimeError("Cannot add items to a closed buffer")
        
        self.buffer.extend(items)
        
        # Signal if we have enough items to form a complete window
        if len(self.buffer) >= self.window_size:
            self._window_ready.set()
    
    async def add_item(self, item: Any) -> None:
        """
        Add a single item to the buffer.
        
        Args:
            item: Item to add to buffer
        """
        await self.add_items([item])
    
    async def close(self) -> None:
        """Mark the buffer as closed (no more data will be added)."""
        self._closed = True
        # Ensure any waiting consumers are notified
        self._window_ready.set()
    
    def __aiter__(self) -> AsyncIterator[List[Any]]:
        """Return asynchronous iterator for the buffer."""
        return self
    
    async def __anext__(self) -> List[Any]:
        """
        Get the next window of items when ready.
        
        Returns:
            Window of items of size window_size
            
        Raises:
            StopAsyncIteration: When buffer is closed and no complete window is available
        """
        # Wait until we have enough data or the stream is closed
        if len(self.buffer) < self.window_size and not self._closed:
            # Reset the event for next notification
            self._window_ready.clear()
            await self._window_ready.wait()
        
        # Check if we have enough data for a complete window
        if len(self.buffer) >= self.window_size:
            # Extract a window
            window = self.buffer[:self.window_size]
            
            # Advance the buffer by step_size (or fewer if at end)
            advance = min(self.step_size, len(self.buffer))
            self.buffer = self.buffer[advance:]
            
            # Reset window ready flag if we don't have enough data for the next window
            if len(self.buffer) < self.window_size:
                self._window_ready.clear()
                
            return window
        
        # No more complete windows and stream is closed
        raise StopAsyncIteration


class BatchProcessor:
    """
    Process data in optimized batches with adaptive sizing.
    
    This class handles batching of data for efficient processing, particularly
    useful for operations like database queries or embedding generation where
    batching improves throughput.
    
    Features:
    - Dynamic batch size based on current workload
    - Automatic rate limiting
    - Progress tracking
    - Concurrency control
    
    Usage:
        processor = BatchProcessor(
            process_func=my_processing_function,
            batch_size=50,
            max_concurrency=10
        )
        
        results = await processor.process_items(large_list_of_items)
    """
    
    def __init__(
        self,
        process_func: Callable[[List[T]], List[V]],
        batch_size: int = 50,
        max_concurrency: int = 5,
        adaptive_sizing: bool = True,
    ):
        """
        Initialize the batch processor.
        
        Args:
            process_func: Function to process each batch of items
            batch_size: Initial/maximum number of items per batch
            max_concurrency: Maximum number of concurrent batch processes
            adaptive_sizing: Whether to adapt batch size based on performance
        """
        self.process_func = process_func
        self.batch_size = batch_size
        self.max_batch_size = batch_size
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.adaptive_sizing = adaptive_sizing
        
    async def _process_batch(self, batch: List[T]) -> Tuple[List[V], float]:
        """
        Process a single batch and measure performance.
        
        Args:
            batch: List of items to process
            
        Returns:
            Tuple of (processed results, seconds per item)
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            results = await self.process_func(batch)
        except Exception as e:
            logger.error(f"Error processing batch: {str(e)}")
            # Return empty results on error
            return [], 0
            
        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time
        items_per_second = len(batch) / duration if duration > 0 else 0
        
        return results, items_per_second
    
    def _adjust_batch_size(self, items_per_second: float) -> None:
        """
        Adjust batch size based on processing performance.
        
        Args:
            items_per_second: Processing rate from last batch
        """
        if not self.adaptive_sizing:
            return
            
        # Simple heuristic to adjust batch size
        if items_per_second > 100:
            # If processing is fast, increase batch size
            self.batch_size = min(self.batch_size * 1.2, self.max_batch_size)
        elif items_per_second < 20:
            # If processing is slow, decrease batch size
            self.batch_size = max(int(self.batch_size * 0.8), 1)
    
    async def process_items(self, items: List[T]) -> List[V]:
        """
        Process a list of items in optimized batches.
        
        Args:
            items: List of items to process
            
        Returns:
            List of processed results
        """
        if not items:
            return []
            
        all_results = []
        total_items = len(items)
        processed_count = 0
        
        # Create batches
        batches = [
            items[i:i + self.batch_size]
            for i in range(0, len(items), self.batch_size)
        ]
        
        async def process_batch_with_semaphore(batch):
            async with self.semaphore:
                return await self._process_batch(batch)
        
        # Process all batches with controlled concurrency
        batch_tasks = [
            asyncio.create_task(process_batch_with_semaphore(batch))
            for batch in batches
        ]
        
        # Process results as they complete
        for task in asyncio.as_completed(batch_tasks):
            results, items_per_second = await task
            all_results.extend(results)
            processed_count += len(results)
            
            # Adjust batch size based on performance
            self._adjust_batch_size(items_per_second)
            
            # Log progress periodically
            if processed_count % 1000 == 0 or processed_count == total_items:
                logger.debug(f"Processed {processed_count}/{total_items} items ({processed_count/total_items:.1%})")
        
        return all_results


async def process_in_parallel(
    items: List[T],
    process_func: Callable[[T], K],
    max_concurrency: int = 10
) -> List[K]:
    """
    Process items in parallel with controlled concurrency.
    
    Args:
        items: List of items to process
        process_func: Async function to process each item
        max_concurrency: Maximum number of concurrent processing tasks
        
    Returns:
        List of processed results in the same order as input items
    """
    semaphore = asyncio.Semaphore(max_concurrency)
    
    async def process_with_semaphore(item, index):
        async with semaphore:
            result = await process_func(item)
            return index, result
    
    # Create tasks for all items
    tasks = [
        asyncio.create_task(process_with_semaphore(item, i))
        for i, item in enumerate(items)
    ]
    
    # Wait for all tasks to complete
    results = await asyncio.gather(*tasks)
    
    # Sort results back to original order
    ordered_results = [r for _, r in sorted(results, key=lambda x: x[0])]
    
    return ordered_results