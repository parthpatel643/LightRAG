from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from typing import AsyncGenerator, AsyncIterator, Callable, Dict, TypeVar

from .utils import logger

T = TypeVar('T')

class StreamingProcessor:
    """
    Stream-based document processor for memory-efficient handling of large documents.
    
    This class implements a generator-based streaming approach to process large documents
    without loading the entire content into memory at once. It uses an adaptive buffer 
    strategy and processes chunks in a streaming fashion.
    
    Benefits:
    - Reduces peak memory usage during document processing
    - Allows immediate processing as data becomes available
    - Compatible with existing LightRAG processing pipeline
    
    Usage:
        processor = StreamingProcessor(chunk_size=8192)
        async for processed_chunk in processor.process_stream(input_stream, processing_func):
            # Handle processed chunk
    """
    
    def __init__(self, chunk_size: int = 8192, buffer_limit: int = 10_485_760):
        """
        Initialize the streaming processor.
        
        Args:
            chunk_size: Size of individual processing chunks in bytes
            buffer_limit: Maximum size of internal buffer in bytes
        """
        self.chunk_size = chunk_size
        self.buffer_limit = buffer_limit
        self._stats: Dict[str, int] = defaultdict(int)
    
    async def process_stream(
        self, 
        input_stream: AsyncIterator[bytes], 
        processing_func: Callable[[str], T]
    ) -> AsyncGenerator[T, None]:
        """
        Process an input stream in a memory-efficient way.
        
        Args:
            input_stream: Async iterator yielding bytes chunks
            processing_func: Function to process each text chunk
            
        Yields:
            Processed chunks as they become available
        """
        buffer = b""
        self._stats["total_bytes"] = 0
        self._stats["peak_buffer_size"] = 0
        
        async for chunk in input_stream:
            buffer += chunk
            self._stats["total_bytes"] += len(chunk)
            
            # Update peak buffer size stat
            current_buffer_size = len(buffer)
            if current_buffer_size > self._stats["peak_buffer_size"]:
                self._stats["peak_buffer_size"] = current_buffer_size
            
            # Process complete chunks when buffer exceeds chunk size
            while len(buffer) >= self.chunk_size:
                # Process a chunk
                process_chunk = buffer[:self.chunk_size]
                buffer = buffer[self.chunk_size:]
                
                # Decode and process
                try:
                    text_chunk = process_chunk.decode('utf-8')
                    yield processing_func(text_chunk)
                except Exception as e:
                    logger.error(f"Error processing chunk: {str(e)}")
                    
                # Yield control to event loop occasionally to prevent blocking
                await asyncio.sleep(0)
                
            # Adaptive buffer management: if buffer exceeds limit, force process
            if len(buffer) > self.buffer_limit:
                cutoff = len(buffer) // 2
                process_chunk = buffer[:cutoff]
                buffer = buffer[cutoff:]
                
                try:
                    text_chunk = process_chunk.decode('utf-8', errors='replace')
                    yield processing_func(text_chunk)
                except Exception as e:
                    logger.error(f"Error processing emergency chunk: {str(e)}")
                    
                await asyncio.sleep(0)
                
        # Process any remaining data in buffer
        if buffer:
            try:
                text_chunk = buffer.decode('utf-8', errors='replace')
                yield processing_func(text_chunk)
            except Exception as e:
                logger.error(f"Error processing final chunk: {str(e)}")
    
    @property
    def stats(self) -> Dict[str, int]:
        """Get processing statistics."""
        return dict(self._stats)


def get_memory_usage() -> Dict[str, float]:
    """
    Get current memory usage statistics in MB.
    
    Returns:
        Dictionary with memory usage statistics:
        - rss: Resident Set Size (physical memory used)
        - vms: Virtual Memory Size
        - shared: Shared memory size
        - data: Process private data size (heap)
        - uss: Unique Set Size (memory unique to this process)
        - pss: Proportional Set Size (shared memory divided by sharing processes)
    """
    try:
        import psutil
        process = psutil.Process()
        mem_info = process.memory_info()
        
        result = {
            "rss": mem_info.rss / (1024 * 1024),  # MB
            "vms": mem_info.vms / (1024 * 1024),  # MB
        }
        
        # Add advanced metrics if available
        try:
            mem_full_info = process.memory_full_info()
            result.update({
                "uss": mem_full_info.uss / (1024 * 1024),  # MB
                "pss": getattr(mem_full_info, "pss", 0) / (1024 * 1024),  # MB
                "swap": getattr(mem_full_info, "swap", 0) / (1024 * 1024),  # MB
            })
        except Exception:
            # If full_info is not available on this platform
            pass
            
        return result
        
    except ImportError:
        # If psutil is not available, return a simpler metric
        return {"total": sys.getsizeof(0)}


class AsyncGeneratorWrapper:
    """
    Helper class to convert a synchronous generator to an asynchronous one.
    
    This allows using regular generators in async contexts without blocking the event loop.
    
    Usage:
        # Convert sync generator to async
        async_gen = AsyncGenerator(sync_generator)
        async for item in async_gen:
            # Process item asynchronously
    """
    
    def __init__(self, gen_func, *args, **kwargs):
        """
        Initialize with a generator function and its arguments.
        
        Args:
            gen_func: Generator function or iterator
            *args: Positional arguments for generator function
            **kwargs: Keyword arguments for generator function
        """
        self.gen = gen_func(*args, **kwargs) if callable(gen_func) else gen_func
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        try:
            # Yield control periodically to event loop
            await asyncio.sleep(0)
            return next(self.gen)
        except StopIteration:
            raise StopAsyncIteration


async def stream_large_file(file_path: str, chunk_size: int = 8192) -> AsyncGenerator:
    """
    Stream a large file with minimal memory usage.
    
    Args:
        file_path: Path to file to stream
        chunk_size: Size of chunks to read
        
    Returns:
        AsyncGenerator yielding file chunks
    """
    async def _file_reader():
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                yield chunk
    
    return AsyncGeneratorWrapper(_file_reader)