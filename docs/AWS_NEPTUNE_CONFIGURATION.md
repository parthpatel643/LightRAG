# AWS Neptune + OpenSearch Configuration Guide

**Document Version:** 1.0  
**Last Updated:** 2026-03-05  
**Target:** Production Deployment with 50+ Concurrent Users

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Neptune Cluster Setup](#neptune-cluster-setup)
4. [OpenSearch Integration](#opensearch-integration)
5. [Connection Pooling Configuration](#connection-pooling-configuration)
6. [Retry Logic & Circuit Breaker](#retry-logic--circuit-breaker)
7. [Performance Optimization](#performance-optimization)
8. [Monitoring & Alerts](#monitoring--alerts)
9. [Security Configuration](#security-configuration)
10. [Troubleshooting](#troubleshooting)

---

## Overview

This guide configures AWS Neptune as the graph storage backend for LightRAG with:
- **IAM-based authentication** for secure access
- **OpenSearch integration** for full-text search capabilities
- **Connection pooling** for efficient resource utilization
- **Retry logic** with exponential backoff for resilience
- **Circuit breaker pattern** to prevent cascade failures
- **CloudWatch monitoring** for observability

### Architecture Diagram

```
┌─────────────────┐
│   LightRAG API  │
│   (ECS Tasks)   │
└────────┬────────┘
         │
         ├──────────────────┬──────────────────┐
         │                  │                  │
    ┌────▼────┐        ┌────▼────┐       ┌────▼────┐
    │ Neptune │        │OpenSearch│       │CloudWatch│
    │ Cluster │        │ Domain   │       │  Logs   │
    │         │        │          │       │         │
    │ Primary │◄───────┤ Full-text│       │ Metrics │
    │ Replica │        │  Search  │       │ Alarms  │
    └─────────┘        └──────────┘       └─────────┘
```

---

## Prerequisites

### 1. AWS Account Setup

```bash
# Install AWS CLI
pip install awscli boto3

# Configure AWS credentials
aws configure
# AWS Access Key ID: YOUR_ACCESS_KEY
# AWS Secret Access Key: YOUR_SECRET_KEY
# Default region: us-east-1
# Default output format: json
```

### 2. IAM Permissions

Create an IAM policy for Neptune access:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "neptune-db:connect",
        "neptune-db:ReadDataViaQuery",
        "neptune-db:WriteDataViaQuery",
        "neptune-db:DeleteDataViaQuery"
      ],
      "Resource": "arn:aws:neptune-db:us-east-1:ACCOUNT_ID:cluster-CLUSTER_ID/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "es:ESHttpGet",
        "es:ESHttpPost",
        "es:ESHttpPut",
        "es:ESHttpDelete"
      ],
      "Resource": "arn:aws:es:us-east-1:ACCOUNT_ID:domain/lightrag-opensearch/*"
    }
  ]
}
```

### 3. Python Dependencies

```bash
# Install required packages
pip install gremlinpython boto3 requests-aws4auth tenacity
```

---

## Neptune Cluster Setup

### 1. Create Neptune Cluster

```bash
# Create Neptune cluster via AWS CLI
aws neptune create-db-cluster \
  --db-cluster-identifier lightrag-neptune-cluster \
  --engine neptune \
  --engine-version 1.3.2.0 \
  --master-username admin \
  --master-user-password 'YourSecurePassword123!' \
  --vpc-security-group-ids sg-xxxxxxxxx \
  --db-subnet-group-name lightrag-subnet-group \
  --backup-retention-period 7 \
  --preferred-backup-window "03:00-04:00" \
  --preferred-maintenance-window "mon:04:00-mon:05:00" \
  --enable-iam-database-authentication \
  --tags Key=Environment,Value=Production Key=Application,Value=LightRAG

# Create primary instance
aws neptune create-db-instance \
  --db-instance-identifier lightrag-neptune-primary \
  --db-instance-class db.r5.large \
  --engine neptune \
  --db-cluster-identifier lightrag-neptune-cluster

# Create read replica for high availability
aws neptune create-db-instance \
  --db-instance-identifier lightrag-neptune-replica \
  --db-instance-class db.r5.large \
  --engine neptune \
  --db-cluster-identifier lightrag-neptune-cluster
```

### 2. Enable IAM Authentication

```bash
# Modify cluster to enable IAM auth
aws neptune modify-db-cluster \
  --db-cluster-identifier lightrag-neptune-cluster \
  --enable-iam-database-authentication \
  --apply-immediately
```

### 3. Configure Security Group

```bash
# Allow inbound traffic on port 8182 from ECS tasks
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxxxxxx \
  --protocol tcp \
  --port 8182 \
  --source-group sg-ecs-tasks
```

---

## OpenSearch Integration

### 1. Create OpenSearch Domain

```bash
# Create OpenSearch domain for full-text search
aws opensearch create-domain \
  --domain-name lightrag-opensearch \
  --engine-version OpenSearch_2.11 \
  --cluster-config InstanceType=r6g.large.search,InstanceCount=2 \
  --ebs-options EBSEnabled=true,VolumeType=gp3,VolumeSize=100 \
  --access-policies '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"AWS": "arn:aws:iam::ACCOUNT_ID:role/LightRAG-ECS-Role"},
      "Action": "es:*",
      "Resource": "arn:aws:es:us-east-1:ACCOUNT_ID:domain/lightrag-opensearch/*"
    }]
  }' \
  --vpc-options SubnetIds=subnet-xxxxxxxx,SecurityGroupIds=sg-xxxxxxxxx \
  --encryption-at-rest-options Enabled=true \
  --node-to-node-encryption-options Enabled=true \
  --domain-endpoint-options EnforceHTTPS=true,TLSSecurityPolicy=Policy-Min-TLS-1-2-2019-07
```

### 2. Create OpenSearch Index

```python
# Python script to create index
import boto3
from requests_aws4auth import AWS4Auth
import requests

# Get AWS credentials
session = boto3.Session()
credentials = session.get_credentials()
region = 'us-east-1'

awsauth = AWS4Auth(
    credentials.access_key,
    credentials.secret_key,
    region,
    'es',
    session_token=credentials.token
)

# OpenSearch endpoint
endpoint = 'https://search-lightrag-opensearch-xxxxx.us-east-1.es.amazonaws.com'

# Create index with mapping
index_name = 'lightrag-entities'
mapping = {
    "mappings": {
        "properties": {
            "entity_name": {"type": "text", "analyzer": "standard"},
            "entity_type": {"type": "keyword"},
            "description": {"type": "text"},
            "workspace": {"type": "keyword"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"}
        }
    },
    "settings": {
        "number_of_shards": 2,
        "number_of_replicas": 1,
        "index": {
            "max_result_window": 10000
        }
    }
}

response = requests.put(
    f'{endpoint}/{index_name}',
    auth=awsauth,
    json=mapping,
    headers={'Content-Type': 'application/json'}
)

print(f"Index creation response: {response.status_code}")
print(response.text)
```

---

## Connection Pooling Configuration

### 1. Environment Variables

Add to `.env`:

```bash
############################
### Neptune Configuration
############################

# Neptune cluster endpoint (writer endpoint)
NEPTUNE_ENDPOINT=lightrag-neptune-cluster.cluster-xxxxx.us-east-1.neptune.amazonaws.com
NEPTUNE_PORT=8182
NEPTUNE_REGION=us-east-1

# IAM authentication (recommended for production)
NEPTUNE_USE_IAM=true

# Connection pooling settings
NEPTUNE_MAX_CONNECTIONS=100          # Maximum concurrent connections
NEPTUNE_MIN_CONNECTIONS=10           # Minimum pool size
NEPTUNE_CONNECTION_TIMEOUT=30        # Connection timeout in seconds
NEPTUNE_IDLE_TIMEOUT=300             # Close idle connections after 5 minutes
NEPTUNE_MAX_CONNECTION_LIFETIME=3600 # Recycle connections after 1 hour

# Retry configuration
NEPTUNE_MAX_RETRIES=3                # Number of retry attempts
NEPTUNE_RETRY_BACKOFF=0.5            # Initial backoff in seconds
NEPTUNE_RETRY_BACKOFF_MAX=5.0        # Maximum backoff in seconds
NEPTUNE_RETRY_JITTER=true            # Add random jitter to backoff

# Circuit breaker configuration
NEPTUNE_CIRCUIT_BREAKER_ENABLED=true
NEPTUNE_CIRCUIT_BREAKER_THRESHOLD=5  # Failures before opening circuit
NEPTUNE_CIRCUIT_BREAKER_TIMEOUT=60   # Seconds before attempting reset
NEPTUNE_CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS=3  # Test calls in half-open state

# Query optimization
NEPTUNE_QUERY_TIMEOUT=30             # Query timeout in seconds
NEPTUNE_BATCH_SIZE=100               # Batch size for bulk operations
NEPTUNE_ENABLE_QUERY_CACHE=true      # Enable query result caching
NEPTUNE_QUERY_CACHE_TTL=300          # Cache TTL in seconds

# OpenSearch integration
NEPTUNE_OPENSEARCH_ENDPOINT=https://search-lightrag-opensearch-xxxxx.us-east-1.es.amazonaws.com
NEPTUNE_OPENSEARCH_INDEX=lightrag-entities
NEPTUNE_OPENSEARCH_TIMEOUT=10        # OpenSearch request timeout
NEPTUNE_OPENSEARCH_MAX_RETRIES=3     # OpenSearch retry attempts

# Monitoring
NEPTUNE_ENABLE_METRICS=true          # Enable CloudWatch metrics
NEPTUNE_METRICS_NAMESPACE=LightRAG/Neptune
NEPTUNE_ENABLE_SLOW_QUERY_LOG=true   # Log slow queries
NEPTUNE_SLOW_QUERY_THRESHOLD_MS=1000 # Threshold for slow query logging
```

### 2. Enhanced Neptune Implementation

Create `lightrag/kg/neptune_connection_pool.py`:

```python
"""
Neptune Connection Pool Manager with Retry Logic and Circuit Breaker
"""

import asyncio
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import random

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)
from gremlin_python.driver import client, serializer

from lightrag.utils import logger


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker pattern implementation for Neptune connections.
    
    Prevents cascade failures by temporarily blocking requests when
    error threshold is exceeded.
    """
    
    threshold: int = 5  # Failures before opening circuit
    timeout: int = 60   # Seconds before attempting reset
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
                logger.info("Circuit breaker: Closing circuit after successful test calls")
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
            logger.error(f"Circuit breaker: Opening circuit after {self.failure_count} failures")
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
        self.circuit_breaker = CircuitBreaker(
            threshold=circuit_breaker_threshold,
            timeout=circuit_breaker_timeout,
        ) if circuit_breaker_enabled else None
        
        # Connection pool
        self._pool: list[client.Client] = []
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
    
    async def get_connection(self) -> client.Client:
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
    
    async def _create_connection(self) -> client.Client:
        """Create a new Neptune connection"""
        url = f"wss://{self.endpoint}:{self.port}/gremlin"
        
        headers = {}
        if self.use_iam:
            from lightrag.kg.neptune_impl import NeptuneIAMAuth
            iam_auth = NeptuneIAMAuth(self.endpoint, self.port, self.region)
            headers = iam_auth.get_signed_headers()
        
        conn = client.Client(
            url=url,
            traversal_source="g",
            message_serializer=serializer.GraphSONSerializersV3d0(),
            headers=headers if headers else None,
        )
        
        logger.debug(f"Created new Neptune connection (total active: {self._active_connections})")
        return conn
    
    async def release_connection(self, conn: client.Client):
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
                        self.retry_backoff * (2 ** attempt),
                        self.retry_backoff_max
                    )
                    if self.retry_jitter:
                        backoff *= (0.5 + random.random() * 0.5)
                    
                    logger.warning(
                        f"Query failed (attempt {attempt + 1}/{self.max_retries + 1}), "
                        f"retrying in {backoff:.2f}s: {str(e)[:100]}"
                    )
                    
                    self._metrics["retried_requests"] += 1
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"Query failed after {self.max_retries + 1} attempts: {e}")
                    raise
    
    def _update_avg_response_time(self, elapsed_ms: float):
        """Update average response time metric"""
        current_avg = self._metrics["avg_response_time_ms"]
        total = self._metrics["successful_requests"]
        self._metrics["avg_response_time_ms"] = (
            (current_avg * (total - 1) + elapsed_ms) / total
        )
    
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
```

---

## Retry Logic & Circuit Breaker

### Implementation in neptune_impl.py

Update `lightrag/kg/neptune_impl.py` to use the connection pool:

```python
# Add to imports
from lightrag.kg.neptune_connection_pool import NeptuneConnectionPool

# Update NeptuneGraphStorage class
@final
@dataclass
class NeptuneGraphStorage(BaseGraphStorage):
    _connection_pool: NeptuneConnectionPool = field(
        default=None, repr=False, init=False, compare=False
    )
    
    async def initialize(self):
        """Initialize Neptune connection pool"""
        async with get_data_init_lock():
            # Get configuration
            endpoint = os.environ.get("NEPTUNE_ENDPOINT")
            port = int(os.environ.get("NEPTUNE_PORT", "8182"))
            region = os.environ.get("NEPTUNE_REGION", "us-east-1")
            use_iam = os.environ.get("NEPTUNE_USE_IAM", "true").lower() == "true"
            
            # Connection pool settings
            max_connections = int(os.environ.get("NEPTUNE_MAX_CONNECTIONS", "100"))
            min_connections = int(os.environ.get("NEPTUNE_MIN_CONNECTIONS", "10"))
            connection_timeout = int(os.environ.get("NEPTUNE_CONNECTION_TIMEOUT", "30"))
            
            # Retry settings
            max_retries = int(os.environ.get("NEPTUNE_MAX_RETRIES", "3"))
            retry_backoff = float(os.environ.get("NEPTUNE_RETRY_BACKOFF", "0.5"))
            retry_backoff_max = float(os.environ.get("NEPTUNE_RETRY_BACKOFF_MAX", "5.0"))
            
            # Circuit breaker settings
            circuit_breaker_enabled = os.environ.get(
                "NEPTUNE_CIRCUIT_BREAKER_ENABLED", "true"
            ).lower() == "true"
            circuit_breaker_threshold = int(
                os.environ.get("NEPTUNE_CIRCUIT_BREAKER_THRESHOLD", "5")
            )
            circuit_breaker_timeout = int(
                os.environ.get("NEPTUNE_CIRCUIT_BREAKER_TIMEOUT", "60")
            )
            
            # Create connection pool
            self._connection_pool = NeptuneConnectionPool(
                endpoint=endpoint,
                port=port,
                region=region,
                use_iam=use_iam,
                max_connections=max_connections,
                min_connections=min_connections,
                connection_timeout=connection_timeout,
                max_retries=max_retries,
                retry_backoff=retry_backoff,
                retry_backoff_max=retry_backoff_max,
                circuit_breaker_enabled=circuit_breaker_enabled,
                circuit_breaker_threshold=circuit_breaker_threshold,
                circuit_breaker_timeout=circuit_breaker_timeout,
            )
            
            # Test connection
            if not await self._connection_pool.health_check():
                raise NeptuneConnectionError("Failed to connect to Neptune")
            
            logger.info(f"Neptune connection pool initialized: {endpoint}")
    
    async def _submit_query(self, query: str) -> Any:
        """Submit query using connection pool with retry logic"""
        return await self._connection_pool.execute_with_retry(query)
    
    async def finalize(self):
        """Close connection pool"""
        if self._connection_pool:
            await self._connection_pool.close_all()
```

---

## Performance Optimization

### 1. Query Optimization

```python
# Batch operations for better performance
NEPTUNE_BATCH_SIZE=100

# Example: Batch insert entities
async def batch_insert_entities(entities: list):
    batch_size = int(os.environ.get("NEPTUNE_BATCH_SIZE", "100"))
    
    for i in range(0, len(entities), batch_size):
        batch = entities[i:i + batch_size]
        
        # Build batch query
        query = "g"
        for entity in batch:
            query += f".addV('entity').property('name', '{entity['name']}')"
        
        await connection_pool.execute_with_retry(query)
```

### 2. Index Configuration

```gremlin
// Create indexes for frequently queried properties
g.tx().open()
mgmt = graph.openManagement()

// Index on entity name
name = mgmt.getPropertyKey('name')
mgmt.buildIndex('byName', Vertex.class).addKey(name).buildCompositeIndex()

// Index on workspace
workspace = mgmt.getPropertyKey('workspace')
mgmt.buildIndex('byWorkspace', Vertex.class).addKey(workspace).buildCompositeIndex()

// Commit index creation
mgmt.commit()
```

### 3. Query Caching

```python
# Enable query result caching
NEPTUNE_ENABLE_QUERY_CACHE=true
NEPTUNE_QUERY_CACHE_TTL=300  # 5 minutes

# Implementation
from functools import lru_cache
import hashlib

@lru_cache(maxsize=1000)
def get_cached_query_result(query_hash: str):
    # Cache implementation
    pass
```

---

## Monitoring & Alerts

### 1. CloudWatch Metrics

```python
# Send custom metrics to CloudWatch
import boto3

cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')

def send_neptune_metrics(metrics: dict):
    """Send Neptune connection pool metrics to CloudWatch"""
    cloudwatch.put_metric_data(
        Namespace='LightRAG/Neptune',
        MetricData=[
            {
                'MetricName': 'ActiveConnections',
                'Value': metrics['active_connections'],
                'Unit': 'Count'
            },
            {
                'MetricName': 'FailedRequests',
                'Value': metrics['failed_requests'],
                'Unit': 'Count'
            },
            {
                'MetricName': 'AvgResponseTime',
                'Value': metrics['avg_response_time_ms'],
                'Unit': 'Milliseconds'
            },
            {
                'MetricName': 'CircuitBreakerOpen',
                'Value': 1 if metrics['circuit_breaker_state'] == 'open' else 0,
                'Unit': 'Count'
            }
        ]
    )
```

### 2. CloudWatch Alarms

```bash
# Create alarm for high error rate
aws cloudwatch put-metric-alarm \
  --alarm-name lightrag-neptune-high-error-rate \
  --alarm-description "Alert when Neptune error rate exceeds 5%" \
  --metric-name FailedRequests \
  --namespace LightRAG/Neptune \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 50 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:lightrag-alerts

# Create alarm for circuit breaker open
aws cloudwatch put-metric-alarm \
  --alarm-name lightrag-neptune-circuit-breaker-open \
  --alarm-description "Alert when Neptune circuit breaker opens" \
  --metric-name CircuitBreakerOpen \
  --namespace LightRAG/Neptune \
  --statistic Maximum \
  --period 60 \
  --evaluation-periods 1 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:lightrag-critical-alerts
```

### 3. Slow Query Logging

```python
# Log slow queries for optimization
NEPTUNE_ENABLE_SLOW_QUERY_LOG=true
NEPTUNE_SLOW_QUERY_THRESHOLD_MS=1000

# Implementation
async def execute_with_logging(query: str):
    start_time = time.time()
    result = await connection_pool.execute_with_retry(query)
    elapsed_ms = (time.time() - start_time) * 1000
    
    if elapsed_ms > int(os.environ.get("NEPTUNE_SLOW_QUERY_THRESHOLD_MS", "1000")):
        logger.warning(
            f"Slow query detected ({elapsed_ms:.2f}ms): {query[:200]}..."
        )
    
    return result
```

---

## Security Configuration

### 1. VPC Configuration

```bash
# Ensure Neptune is in private subnet
aws neptune modify-db-cluster \
  --db-cluster-identifier lightrag-neptune-cluster \
  --vpc-security-group-ids sg-private-subnet

# No public accessibility
aws neptune modify-db-instance \
  --db-instance-identifier lightrag-neptune-primary \
  --no-publicly-accessible
```

### 2. Encryption

```bash
# Enable encryption at rest
aws neptune modify-db-cluster \
  --db-cluster-identifier lightrag-neptune-cluster \
  --storage-encrypted \
  --kms-key-id arn:aws:kms:us-east-1:ACCOUNT_ID:key/xxxxx

# Enable encryption in transit (TLS)
# Neptune enforces TLS by default on port 8182
```

### 3. IAM Policies

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "neptune-db:connect"
      ],
      "Resource": "arn:aws:neptune-db:us-east-1:ACCOUNT_ID:cluster-CLUSTER_ID/*",
      "Condition": {
        "StringEquals": {
          "neptune-db:QueryLanguage": "Gremlin"
        }
      }
    }
  ]
}
```

---

## Troubleshooting

### Common Issues

#### 1. Connection Timeout

**Symptom:** `NeptuneConnectionError: Connection timeout`

**Solution:**
```bash
# Increase timeout
NEPTUNE_CONNECTION_TIMEOUT=60

# Check security group rules
aws ec2 describe-security-groups --group-ids sg-xxxxxxxxx

# Verify VPC routing
aws ec2 describe-route-tables --filters "Name=vpc-id,Values=vpc-xxxxxxxx"
```

#### 2. Circuit Breaker Open

**Symptom:** `Circuit breaker is open, rejecting request`

**Solution:**
```bash
# Check Neptune cluster status
aws neptune describe-db-clusters --db-cluster-identifier lightrag-neptune-cluster

# Review CloudWatch logs
aws logs tail /aws/neptune/lightrag-neptune-cluster --follow

# Manually reset circuit breaker (restart application)
# Or wait for timeout period (default 60s)
```

#### 3. IAM Authentication Failure

**Symptom:** `IAM authentication failed: Invalid credentials`

**Solution:**
```bash
# Verify IAM role has correct permissions
aws iam get-role-policy --role-name LightRAG-ECS-Role --policy-name NeptuneAccess

# Check AWS credentials
aws sts get-caller-identity

# Verify Neptune IAM auth is enabled
aws neptune describe-db-clusters \
  --db-cluster-identifier lightrag-neptune-cluster \
  --query 'DBClusters[0].IAMDatabaseAuthenticationEnabled'
```

#### 4. High Latency

**Symptom:** Queries taking >1 second

**Solution:**
```bash
# Check Neptune instance size
aws neptune describe-db-instances \
  --db-instance-identifier lightrag-neptune-primary

# Review slow query logs
# Enable Neptune audit logs
aws neptune modify-db-cluster \
  --db-cluster-identifier lightrag-neptune-cluster \
  --enable-cloudwatch-logs-exports audit

# Optimize queries with indexes
# Consider upgrading instance class
```

---

## Performance Benchmarks

### Expected Performance

| Metric | Target | Notes |
|--------|--------|-------|
| **Connection Pool Utilization** | 60-80% | Optimal range |
| **Query Response Time (p50)** | <100ms | Simple queries |
| **Query Response Time (p95)** | <500ms | Complex traversals |
| **Batch Insert Rate** | 1000+ entities/sec | With batch size 100 |
| **Circuit Breaker Trips** | <1/hour | In healthy system |
| **Connection Errors** | <0.1% | Of total requests |

### Load Testing

```python
# Load test script
import asyncio
import time
from lightrag.kg.neptune_connection_pool import NeptuneConnectionPool

async def load_test(pool: NeptuneConnectionPool, num_requests: int):
    """Run load test on Neptune connection pool"""
    
    async def single_request():
        try:
            await pool.execute_with_retry("g.V().limit(10)")
            return True
        except Exception:
            return False
    
    start_time = time.time()
    results = await asyncio.gather(*[single_request() for _ in range(num_requests)])
    elapsed = time.time() - start_time
    
    success_count = sum(results)
    print(f"Completed {num_requests} requests in {elapsed:.2f}s")
    print(f"Success rate: {success_count/num_requests*100:.2f}%")
    print(f"Throughput: {num_requests/elapsed:.2f} req/s")
    print(f"Metrics: {pool.get_metrics()}")

# Run test
pool = NeptuneConnectionPool(endpoint="your-endpoint", port=8182)
asyncio.run(load_test(pool, 1000))
```

---

## Next Steps

1. **Deploy Neptune Cluster** - Follow setup instructions
2. **Configure Connection Pool** - Add environment variables to `.env`
3. **Test Connection** - Run health check script
4. **Enable Monitoring** - Set up CloudWatch alarms
5. **Load Test** - Verify performance under load
6. **Migrate Data** - Follow migration guide (see `docs/AWS_MIGRATION_STRATEGY.md`)

---

## Additional Resources

- [AWS Neptune Documentation](https://docs.aws.amazon.com/neptune/)
- [Gremlin Query Language](https://tinkerpop.apache.org/docs/current/reference/)
- [OpenSearch Documentation](https://opensearch.org/docs/latest/)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Connection Pooling Best Practices](https://aws.amazon.com/blogs/database/best-practices-for-amazon-neptune/)

---

**Document Status:** ✅ Complete  
**Next Document:** `docs/AWS_MILVUS_CONFIGURATION.md`