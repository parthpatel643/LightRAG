"""
Distributed processing capabilities for LightRAG.

This module provides tools and utilities for distributing LightRAG workloads
across multiple processes or machines to improve throughput and scalability.
"""

__all__ = [
    "DistributedManager",
    "WorkerPool",
    "DistributedConfig",
    "TaskRouter",
    "initialize_distributed",
]

from .manager import DistributedManager
from .pool import WorkerPool
from .config import DistributedConfig
from .router import TaskRouter

# Import this function for simplified initialization
from .manager import initialize_distributed