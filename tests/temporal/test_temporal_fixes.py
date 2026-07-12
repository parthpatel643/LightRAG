"""
Unit tests for temporal logic fixes.

Tests cover:
- Issue #6: Race condition in sequence index generation
- Issue #16: Atomic batch operations
- Issue #17: Transaction support with rollback

Run with:
    pytest tests/test_temporal_fixes.py -v
    pytest tests/test_temporal_fixes.py -v --run-integration  # For integration tests
"""

import asyncio

import pytest

# Import the temporal fixes
from lightrag.temporal import (
    SequenceIndexManager,
    TransactionManager,
    transaction,
)


class MockKVStorage:
    """Mock KV storage for testing."""

    def __init__(self):
        self.data = {}

    async def get_by_id(self, key: str):
        """Get value by ID."""
        if key in self.data:
            return {"value": self.data[key]}
        return None

    async def upsert(self, data: dict):
        """Upsert data."""
        for key, value_dict in data.items():
            self.data[key] = value_dict.get("value")

    async def delete(self, keys: list):
        """Delete keys."""
        for key in keys:
            self.data.pop(key, None)


class TestSequenceIndexManager:
    """Test sequence index generation fixes (Issue #6)."""

    @pytest.mark.asyncio
    async def test_single_allocation(self):
        """Test single sequence index allocation."""
        storage = MockKVStorage()
        manager = SequenceIndexManager(storage)

        # First allocation should be 1
        idx1 = await manager.get_next_sequence_index()
        assert idx1 == 1

        # Second allocation should be 2
        idx2 = await manager.get_next_sequence_index()
        assert idx2 == 2

        # Third allocation should be 3
        idx3 = await manager.get_next_sequence_index()
        assert idx3 == 3

    @pytest.mark.asyncio
    async def test_concurrent_allocation_no_duplicates(self):
        """Test that concurrent allocations don't produce duplicates (Issue #6)."""
        storage = MockKVStorage()
        manager = SequenceIndexManager(storage, lock_timeout=5.0, lock_retry_delay=0.01)

        async def allocate():
            return await manager.get_next_sequence_index()

        # Run 50 concurrent allocations
        tasks = [allocate() for _ in range(50)]
        results = await asyncio.gather(*tasks)

        # All results should be unique
        assert len(results) == len(set(results)), f"Duplicates found in {results}"

        # Results should be consecutive from 1 to 50
        assert min(results) == 1
        assert max(results) == 50
        assert sorted(results) == list(range(1, 51))

    @pytest.mark.asyncio
    async def test_batch_allocation_atomic(self):
        """Test that batch allocation is atomic (Issue #16)."""
        storage = MockKVStorage()
        manager = SequenceIndexManager(storage)

        # Allocate batch of 10
        indices = await manager.get_next_batch_sequence_indices(10)

        assert len(indices) == 10
        assert indices == list(range(1, 11))

        # Next single allocation should be 11
        next_idx = await manager.get_next_sequence_index()
        assert next_idx == 11

        # Another batch of 5
        indices2 = await manager.get_next_batch_sequence_indices(5)
        assert indices2 == list(range(12, 17))

    @pytest.mark.asyncio
    async def test_batch_allocation_no_gaps(self):
        """Test that batch allocation doesn't create gaps."""
        storage = MockKVStorage()
        manager = SequenceIndexManager(storage)

        # Allocate multiple batches
        batch1 = await manager.get_next_batch_sequence_indices(5)
        batch2 = await manager.get_next_batch_sequence_indices(3)
        batch3 = await manager.get_next_batch_sequence_indices(7)

        # All indices should be consecutive
        all_indices = batch1 + batch2 + batch3
        assert all_indices == list(range(1, 16))

    @pytest.mark.asyncio
    async def test_get_current_max_sequence(self):
        """Test getting current max sequence without incrementing."""
        storage = MockKVStorage()
        manager = SequenceIndexManager(storage)

        # Initially should be 0
        max_seq = await manager.get_current_max_sequence()
        assert max_seq == 0

        # After allocation
        await manager.get_next_sequence_index()
        max_seq = await manager.get_current_max_sequence()
        assert max_seq == 1

        # After batch allocation
        await manager.get_next_batch_sequence_indices(5)
        max_seq = await manager.get_current_max_sequence()
        assert max_seq == 6

    @pytest.mark.asyncio
    async def test_reset_sequence(self):
        """Test resetting sequence counter."""
        storage = MockKVStorage()
        manager = SequenceIndexManager(storage)

        # Allocate some indices
        await manager.get_next_batch_sequence_indices(10)

        # Reset to 0
        await manager.reset_sequence(0)

        # Next allocation should be 1
        next_idx = await manager.get_next_sequence_index()
        assert next_idx == 1

    @pytest.mark.asyncio
    async def test_batch_allocation_invalid_count(self):
        """Test that invalid batch count raises error."""
        storage = MockKVStorage()
        manager = SequenceIndexManager(storage)

        with pytest.raises(ValueError, match="count must be > 0"):
            await manager.get_next_batch_sequence_indices(0)

        with pytest.raises(ValueError, match="count must be > 0"):
            await manager.get_next_batch_sequence_indices(-5)


class TestTransactionManager:
    """Test transaction support fixes (Issue #17)."""

    @pytest.mark.asyncio
    async def test_transaction_commit_success(self):
        """Test successful transaction commit."""
        executed_operations = []

        async def op1():
            executed_operations.append("op1")
            return "result1"

        async def op2():
            executed_operations.append("op2")
            return "result2"

        async with transaction() as tx:
            tx.add_operation("op1", op1)
            tx.add_operation("op2", op2)

        assert executed_operations == ["op1", "op2"]
        assert tx.is_committed()
        results = tx.get_results()
        assert results == {"op1": "result1", "op2": "result2"}

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_failure(self):
        """Test that transaction rolls back on failure."""
        executed_operations = []
        rolled_back_operations = []

        async def op1():
            executed_operations.append("op1")
            return "result1"

        async def op2():
            executed_operations.append("op2")
            raise ValueError("Simulated failure")

        async def rollback1():
            rolled_back_operations.append("rollback1")

        with pytest.raises(RuntimeError, match="Transaction failed and rolled back"):
            async with transaction() as tx:
                tx.add_operation("op1", op1, rollback=rollback1)
                tx.add_operation("op2", op2)

        assert executed_operations == ["op1", "op2"]
        assert rolled_back_operations == ["rollback1"]
        assert not tx.is_committed()

    @pytest.mark.asyncio
    async def test_transaction_rollback_order(self):
        """Test that rollback executes in reverse order (LIFO)."""
        rollback_order = []

        async def op1():
            return "result1"

        async def op2():
            return "result2"

        async def op3():
            raise ValueError("Failure at op3")

        async def rollback1():
            rollback_order.append("rollback1")

        async def rollback2():
            rollback_order.append("rollback2")

        with pytest.raises(RuntimeError):
            async with transaction() as tx:
                tx.add_operation("op1", op1, rollback=rollback1)
                tx.add_operation("op2", op2, rollback=rollback2)
                tx.add_operation("op3", op3)

        # Rollback should execute in reverse order (LIFO)
        assert rollback_order == ["rollback2", "rollback1"]

    @pytest.mark.asyncio
    async def test_transaction_partial_rollback(self):
        """Test rollback of only executed operations."""
        executed_operations = []
        rolled_back_operations = []

        async def op1():
            executed_operations.append("op1")

        async def op2():
            executed_operations.append("op2")
            raise ValueError("Failure")

        async def op3():
            executed_operations.append("op3")  # Never executed

        async def rollback1():
            rolled_back_operations.append("rollback1")

        async def rollback2():
            rolled_back_operations.append("rollback2")  # Never executed

        async def rollback3():
            rolled_back_operations.append("rollback3")  # Never executed

        with pytest.raises(RuntimeError):
            async with transaction() as tx:
                tx.add_operation("op1", op1, rollback=rollback1)
                tx.add_operation("op2", op2, rollback=rollback2)
                tx.add_operation("op3", op3, rollback=rollback3)

        # Only op1 executed, so only rollback1 should run
        assert executed_operations == ["op1", "op2"]
        assert rolled_back_operations == ["rollback1"]

    @pytest.mark.asyncio
    async def test_transaction_without_rollback(self):
        """Test transaction with operations that have no rollback."""
        executed_operations = []

        async def op1():
            executed_operations.append("op1")

        async def op2():
            executed_operations.append("op2")
            raise ValueError("Failure")

        with pytest.raises(RuntimeError):
            async with transaction() as tx:
                tx.add_operation("op1", op1)  # No rollback
                tx.add_operation("op2", op2)  # No rollback

        # Operations executed but no rollback
        assert executed_operations == ["op1", "op2"]

    @pytest.mark.asyncio
    async def test_transaction_get_results_before_commit(self):
        """Test that getting results before commit raises error."""
        tx = TransactionManager()

        with pytest.raises(RuntimeError, match="Transaction not committed yet"):
            tx.get_results()

    @pytest.mark.asyncio
    async def test_transaction_with_args_and_kwargs(self):
        """Test transaction operations with arguments."""
        results = []

        async def op_with_args(a, b, c=None):
            results.append((a, b, c))
            return a + b + (c or 0)

        async with transaction() as tx:
            tx.add_operation("op1", op_with_args, args=(1, 2), kwargs={"c": 3})
            tx.add_operation(
                "op2",
                op_with_args,
                args=(10, 20),
            )

        assert results == [(1, 2, 3), (10, 20, None)]
        assert tx.get_results() == {"op1": 6, "op2": 30}


@pytest.mark.integration
class TestTemporalIntegration:
    """Integration tests for temporal fixes."""

    @pytest.mark.asyncio
    async def test_concurrent_sequence_allocation_stress(self):
        """Stress test with many concurrent allocations."""
        storage = MockKVStorage()
        manager = SequenceIndexManager(
            storage, lock_timeout=10.0, lock_retry_delay=0.01
        )

        async def allocate():
            return await manager.get_next_sequence_index()

        # Run 200 concurrent allocations
        tasks = [allocate() for _ in range(200)]
        results = await asyncio.gather(*tasks)

        # All results should be unique
        assert len(results) == len(set(results)), "Duplicates found!"
        assert sorted(results) == list(range(1, 201))

    @pytest.mark.asyncio
    async def test_mixed_single_and_batch_allocations(self):
        """Test mixing single and batch allocations."""
        storage = MockKVStorage()
        manager = SequenceIndexManager(storage)

        results = []

        # Mix of single and batch allocations
        results.append(await manager.get_next_sequence_index())  # 1
        results.extend(await manager.get_next_batch_sequence_indices(5))  # 2-6
        results.append(await manager.get_next_sequence_index())  # 7
        results.extend(await manager.get_next_batch_sequence_indices(3))  # 8-10
        results.append(await manager.get_next_sequence_index())  # 11

        # Should be consecutive
        assert results == list(range(1, 12))

    @pytest.mark.asyncio
    async def test_transaction_with_sequence_allocation(self):
        """Test transaction with sequence allocation operations."""
        storage = MockKVStorage()
        manager = SequenceIndexManager(storage)

        allocated_indices = []

        async def allocate_batch():
            indices = await manager.get_next_batch_sequence_indices(5)
            allocated_indices.extend(indices)
            return indices

        async def allocate_single():
            idx = await manager.get_next_sequence_index()
            allocated_indices.append(idx)
            return idx

        async with transaction() as tx:
            tx.add_operation("batch1", allocate_batch)
            tx.add_operation("single1", allocate_single)
            tx.add_operation("batch2", allocate_batch)

        # Should have allocated 11 indices total (5 + 1 + 5)
        assert len(allocated_indices) == 11
        assert allocated_indices == list(range(1, 12))


@pytest.mark.performance
class TestTemporalPerformance:
    """Performance tests for temporal operations."""

    @pytest.mark.asyncio
    async def test_batch_allocation_performance(self):
        """Test that batch allocation is faster than sequential."""
        import time

        storage = MockKVStorage()
        manager = SequenceIndexManager(storage, lock_retry_delay=0.001)

        # Measure sequential allocation
        start = time.time()
        for _ in range(100):
            await manager.get_next_sequence_index()
        sequential_time = time.time() - start

        # Reset
        await manager.reset_sequence(0)

        # Measure batch allocation
        start = time.time()
        await manager.get_next_batch_sequence_indices(100)
        batch_time = time.time() - start

        # Batch should be significantly faster (at least 2x)
        assert batch_time < sequential_time / 2, (
            f"Batch ({batch_time:.3f}s) not faster than sequential ({sequential_time:.3f}s)"
        )


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])

#
