"""
Neptune Connection Pool Manager with Retry Logic and Circuit Breaker

This module provides a production-ready connection pool for AWS Neptune with:
- Connection pooling with configurable min/max connections
- Automatic retry with exponential backoff and jitter
- Circuit breaker pattern for fault tolerance
- Connection health checks
- CloudWatch metrics integration
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

try:
    from gremlin_python.driver import client, serializer
except ImportError:
    client = None
    serializer = None

from lightrag.utils import logger


class CircuitState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker pattern implementation for Neptune connections.

    Prevents cascade failures by temporarily blocking requests when
    error threshold is exceeded.
    """

    threshold: int = 5  # Failures before opening circuit
    timeout: int = 60  # Seconds before attempting reset
    half_open_max_calls: int = 3  # Test calls in half-open state

    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    failure_count: int = field(default=0, init=False)
    last_failure_time: float = field(default=0.0, init=False)
    half_open_calls: int = field(default=0, init=False)

    def record_success(self):
        """Record successful operation"""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                logger.info(
                    "Circuit breaker: Closing circuit after successful test calls"
                )
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_calls = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            logger.warning("Circuit breaker: Test call failed, reopening circuit")
            self.state = CircuitState.OPEN
            self.half_open_calls = 0
        elif self.failure_count >= self.threshold:
            logger.error(
                f"Circuit breaker: Opening circuit after {self.failure_count} failures"
            )
            self.state = CircuitState.OPEN

    def can_attempt(self) -> bool:
        """Check if request can be attempted"""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if timeout has elapsed
            if time.time() - self.last_failure_time >= self.timeout:
                logger.info("Circuit breaker: Attempting half-open state")
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False

        # HALF_OPEN state
        return True

    def get_state(self) -> str:
        """Get current circuit state"""
        return self.state.value


class NeptuneConnectionPool:
    """
    Connection pool manager for Neptune with retry logic and circuit breaker.

    Features:
    - Connection pooling with configurable min/max connections
    - Automatic retry with exponential backoff
    - Circuit breaker pattern for fault tolerance
    - Connection health checks
    - Metrics collection
    """

    def __init__(
        self,
        endpoint: str,
        port: int = 8182,
        region: str = "us-east-1",
        use_iam: bool = True,
        max_connections: int = 100,
        min_connections: int = 10,
        connection_timeout: int = 30,
        idle_timeout: int = 300,
        max_connection_lifetime: int = 3600,
        max_retries: int = 3,
        retry_backoff: float = 0.5,
        retry_backoff_max: float = 5.0,
        retry_jitter: bool = True,
        circuit_breaker_enabled: bool = True,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: int = 60,
    ):
        if client is None:
            raise ImportError(
                "gremlinpython is required for Neptune connection pool. "
                "Install with: pip install gremlinpython"
            )

        self.endpoint = endpoint
        self.port = port
        self.region = region
        self.use_iam = use_iam

        # Connection pool settings
        self.max_connections = max_connections
        self.min_connections = min_connections
        self.connection_timeout = connection_timeout
        self.idle_timeout = idle_timeout
        self.max_connection_lifetime = max_connection_lifetime

        # Retry settings
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.retry_backoff_max = retry_backoff_max
        self.retry_jitter = retry_jitter

        # Circuit breaker
        self.circuit_breaker_enabled = circuit_breaker_enabled
        self.circuit_breaker = (
            CircuitBreaker(
                threshold=circuit_breaker_threshold,
                timeout=circuit_breaker_timeout,
            )
            if circuit_breaker_enabled
            else None
        )

        # Connection pool
        self._pool: list[Any] = []
        self._pool_lock = asyncio.Lock()
        self._active_connections = 0
        self._total_requests = 0
        self._failed_requests = 0

        # Metrics
        self._metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "retried_requests": 0,
            "circuit_breaker_open_count": 0,
            "avg_response_time_ms": 0.0,
        }

    async def get_connection(self) -> Any:
        """
        Get a connection from the pool or create a new one.

        Returns:
            Gremlin client connection

        Raises:
            Exception: If circuit breaker is open or max connections reached
        """
        # Check circuit breaker
        if self.circuit_breaker_enabled and not self.circuit_breaker.can_attempt():
            self._metrics["circuit_breaker_open_count"] += 1
            raise Exception(
                f"Circuit breaker is {self.circuit_breaker.get_state()}, "
                "rejecting request to prevent cascade failure"
            )

        async with self._pool_lock:
            # Try to reuse existing connection
            if self._pool:
                conn = self._pool.pop()
                self._active_connections += 1
                return conn

            # Create new connection if under limit
            if self._active_connections < self.max_connections:
                conn = await self._create_connection()
                self._active_connections += 1
                return conn

            # Wait for available connection
            logger.warning(
                f"Connection pool exhausted ({self._active_connections}/{self.max_connections}), "
                "waiting for available connection"
            )

        # Wait and retry
        await asyncio.sleep(0.1)
        return await self.get_connection()

    async def _create_connection(self) -> Any:
        """Create a new Neptune connection"""
        url = f"wss://{self.endpoint}:{self.port}/gremlin"

        headers = {}
        if self.use_iam:
            try:
                from lightrag.kg.neptune_impl import NeptuneIAMAuth

                iam_auth = NeptuneIAMAuth(self.endpoint, self.port, self.region)
                headers = iam_auth.get_signed_headers()
            except ImportError:
                logger.warning(
                    "NeptuneIAMAuth not available, using connection without IAM"
                )

        conn = client.Client(
            url=url,
            traversal_source="g",
            message_serializer=serializer.GraphSONSerializersV3d0(),
            headers=headers if headers else None,
        )

        logger.debug(
            f"Created new Neptune connection (total active: {self._active_connections})"
        )
        return conn

    async def release_connection(self, conn: Any):
        """Return connection to the pool"""
        async with self._pool_lock:
            if len(self._pool) < self.min_connections:
                self._pool.append(conn)
            else:
                # Close excess connections
                try:
                    await asyncio.to_thread(conn.close)
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")

            self._active_connections -= 1

    async def execute_with_retry(self, query: str) -> Any:
        """
        Execute query with retry logic and circuit breaker.

        Args:
            query: Gremlin query string

        Returns:
            Query results

        Raises:
            Exception: If all retries fail or circuit breaker is open
        """
        self._metrics["total_requests"] += 1
        start_time = time.time()

        for attempt in range(self.max_retries + 1):
            try:
                conn = await self.get_connection()

                try:
                    # Execute query
                    result = await asyncio.to_thread(
                        lambda: conn.submit(query).all().result()
                    )

                    # Record success
                    if self.circuit_breaker_enabled:
                        self.circuit_breaker.record_success()

                    self._metrics["successful_requests"] += 1

                    # Update metrics
                    elapsed_ms = (time.time() - start_time) * 1000
                    self._update_avg_response_time(elapsed_ms)

                    return result

                finally:
                    await self.release_connection(conn)

            except Exception as e:
                self._metrics["failed_requests"] += 1

                if self.circuit_breaker_enabled:
                    self.circuit_breaker.record_failure()

                if attempt < self.max_retries:
                    # Calculate backoff with jitter
                    backoff = min(
                        self.retry_backoff * (2**attempt), self.retry_backoff_max
                    )
                    if self.retry_jitter:
                        backoff *= 0.5 + random.random() * 0.5

                    logger.warning(
                        f"Query failed (attempt {attempt + 1}/{self.max_retries + 1}), "
                        f"retrying in {backoff:.2f}s: {str(e)[:100]}"
                    )

                    self._metrics["retried_requests"] += 1
                    await asyncio.sleep(backoff)
                else:
                    logger.error(
                        f"Query failed after {self.max_retries + 1} attempts: {e}"
                    )
                    raise

    def _update_avg_response_time(self, elapsed_ms: float):
        """Update average response time metric"""
        current_avg = self._metrics["avg_response_time_ms"]
        total = self._metrics["successful_requests"]
        if total > 0:
            self._metrics["avg_response_time_ms"] = (
                current_avg * (total - 1) + elapsed_ms
            ) / total
        else:
            self._metrics["avg_response_time_ms"] = elapsed_ms

    def get_metrics(self) -> dict:
        """Get connection pool metrics"""
        return {
            **self._metrics,
            "active_connections": self._active_connections,
            "pooled_connections": len(self._pool),
            "circuit_breaker_state": (
                self.circuit_breaker.get_state()
                if self.circuit_breaker_enabled
                else "disabled"
            ),
        }

    async def health_check(self) -> bool:
        """
        Perform health check on Neptune connection.

        Returns:
            True if healthy, False otherwise
        """
        try:
            await self.execute_with_retry("g.V().limit(1)")
            return True
        except Exception as e:
            logger.error(f"Neptune health check failed: {e}")
            return False

    async def close_all(self):
        """Close all connections in the pool"""
        async with self._pool_lock:
            for conn in self._pool:
                try:
                    await asyncio.to_thread(conn.close)
                except Exception as e:
                    logger.warning(f"Error closing pooled connection: {e}")

            self._pool.clear()
            self._active_connections = 0

        logger.info("All Neptune connections closed")


#
