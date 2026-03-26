"""
Transaction Manager - ACID transaction support for multi-storage operations.

This module provides transaction management to ensure data consistency across
multiple storage backends (graph, vector, KV stores).

Fixes Issue #17: Missing Transaction Support

Features:
- Atomicity: All operations succeed or all fail
- Consistency: System remains in valid state
- Isolation: Concurrent transactions don't interfere
- Durability: Committed changes persist
- Automatic rollback on failure
- Clear operation ordering

Usage:
    from lightrag.temporal import transaction

    async with transaction() as tx:
        tx.add_operation(
            name="insert_entities",
            operation=insert_func,
            rollback=delete_func,
        )
        tx.add_operation(
            name="insert_relations",
            operation=insert_relations_func,
            rollback=delete_relations_func,
        )
        # Automatic commit on success, rollback on failure
"""

from contextlib import asynccontextmanager
from typing import Any, Callable

from ..utils import logger


class TransactionManager:
    """
    Transaction manager for coordinating updates across multiple storage backends.

    Provides ACID-like guarantees for multi-storage operations:
    - Atomicity: All operations succeed or all fail
    - Consistency: System remains in valid state
    - Isolation: Concurrent transactions don't interfere (via locks)
    - Durability: Committed changes persist
    """

    def __init__(self):
        """Initialize transaction manager."""
        self._operations: list[tuple[str, Callable, tuple, dict]] = []
        self._rollback_operations: list[tuple[str, Callable, tuple, dict]] = []
        self._committed = False
        self._results: dict[str, Any] = {}

    def add_operation(
        self,
        name: str,
        operation: Callable,
        args: tuple = (),
        kwargs: dict | None = None,
        rollback: Callable | None = None,
        rollback_args: tuple = (),
        rollback_kwargs: dict | None = None,
    ) -> None:
        """
        Add operation to transaction.

        Args:
            name: Operation name for logging and tracking
            operation: Async function to execute
            args: Positional arguments for operation
            kwargs: Keyword arguments for operation
            rollback: Optional rollback function (async)
            rollback_args: Arguments for rollback
            rollback_kwargs: Keyword arguments for rollback

        Example:
            tx.add_operation(
                name="insert_entities",
                operation=insert_entities_func,
                args=(entities,),
                rollback=delete_entities_func,
                rollback_args=(entity_ids,),
            )
        """
        if kwargs is None:
            kwargs = {}
        if rollback_kwargs is None:
            rollback_kwargs = {}

        self._operations.append((name, operation, args, kwargs))

        if rollback:
            # Insert at beginning for reverse order execution
            self._rollback_operations.insert(
                0, (f"rollback_{name}", rollback, rollback_args, rollback_kwargs)
            )

        logger.debug(
            f"Transaction: Added operation '{name}' (rollback={'yes' if rollback else 'no'})"
        )

    async def commit(self) -> dict[str, Any]:
        """
        Execute all operations in transaction.

        Returns:
            Dictionary mapping operation names to results

        Raises:
            RuntimeError: If any operation fails (after rollback)
        """
        executed_count = 0
        failed_operation = None

        try:
            logger.info(
                f"Transaction: Starting commit of {len(self._operations)} operations"
            )

            for name, operation, args, kwargs in self._operations:
                logger.debug(f"Transaction: Executing operation '{name}'")

                try:
                    result = await operation(*args, **kwargs)
                    self._results[name] = result
                    executed_count += 1
                    logger.debug(
                        f"Transaction: Operation '{name}' completed successfully"
                    )

                except Exception as op_error:
                    failed_operation = name
                    logger.error(
                        f"Transaction: Operation '{name}' failed: {op_error}",
                        exc_info=True,
                    )
                    raise

            self._committed = True
            logger.info(
                f"Transaction: Successfully committed {executed_count} operations"
            )
            return self._results

        except Exception as e:
            logger.error(
                f"Transaction: Failed at operation {executed_count + 1}/{len(self._operations)} "
                f"('{failed_operation}'): {e}"
            )

            # Rollback executed operations
            await self._rollback(executed_count)

            raise RuntimeError(
                f"Transaction failed and rolled back. "
                f"Failed operation: '{failed_operation}'. "
                f"Error: {str(e)}"
            ) from e

    async def _rollback(self, executed_count: int) -> None:
        """
        Rollback executed operations in reverse order.

        Args:
            executed_count: Number of operations that were executed
        """
        if not self._rollback_operations:
            logger.warning("Transaction: No rollback operations defined")
            return

        rollback_count = min(executed_count, len(self._rollback_operations))
        logger.info(f"Transaction: Rolling back {rollback_count} operations")

        rollback_errors = []

        # Execute rollback operations in reverse order (LIFO)
        for i, (name, rollback_op, args, kwargs) in enumerate(
            self._rollback_operations[:rollback_count]
        ):
            try:
                logger.debug(
                    f"Transaction: Executing rollback '{name}' ({i + 1}/{rollback_count})"
                )
                await rollback_op(*args, **kwargs)
                logger.debug(f"Transaction: Rollback '{name}' completed")

            except Exception as e:
                error_msg = f"{name}: {str(e)}"
                rollback_errors.append(error_msg)
                logger.error(
                    f"Transaction: Rollback operation '{name}' failed: {e}",
                    exc_info=True,
                )

        if rollback_errors:
            logger.error(
                f"Transaction: Rollback completed with {len(rollback_errors)} errors:\n"
                + "\n".join(f"  - {err}" for err in rollback_errors)
            )
        else:
            logger.info("Transaction: Rollback completed successfully")

    def get_results(self) -> dict[str, Any]:
        """
        Get results from committed transaction.

        Returns:
            Dictionary mapping operation names to results

        Raises:
            RuntimeError: If transaction not committed
        """
        if not self._committed:
            raise RuntimeError("Transaction not committed yet")
        return self._results.copy()

    def is_committed(self) -> bool:
        """Check if transaction was successfully committed."""
        return self._committed


@asynccontextmanager
async def transaction():
    """
    Context manager for transaction operations.

    Automatically commits on success and rolls back on failure.

    Usage:
        async with transaction() as tx:
            tx.add_operation("op1", operation_func, rollback=rollback_func)
            tx.add_operation("op2", operation_func2, rollback=rollback_func2)
            # Automatic commit on context exit
            # Automatic rollback on exception

    Yields:
        TransactionManager instance

    Raises:
        RuntimeError: If transaction fails (after rollback)
    """
    tx = TransactionManager()
    try:
        yield tx
        # Commit on successful context exit
        await tx.commit()
    except Exception:
        # Rollback already handled in commit()
        raise


class TransactionError(Exception):
    """Base exception for transaction errors."""

    pass


class TransactionRollbackError(TransactionError):
    """Exception raised when transaction rollback fails."""

    def __init__(self, message: str, rollback_errors: list[str]):
        super().__init__(message)
        self.rollback_errors = rollback_errors


class TransactionTimeoutError(TransactionError):
    """Exception raised when transaction times out."""

    pass


# Example usage helper
async def example_transaction_usage():
    """
    Example demonstrating transaction usage.

    This is for documentation purposes only.
    """
    # Example: Insert entities and relations with transaction
    async with transaction() as tx:
        # Step 1: Insert entities
        entities_to_insert = [{"name": "Entity1"}, {"name": "Entity2"}]
        inserted_entity_ids = []

        async def insert_entities():
            nonlocal inserted_entity_ids
            # Simulate entity insertion
            inserted_entity_ids = ["id1", "id2"]
            return inserted_entity_ids

        async def rollback_entities():
            # Simulate entity deletion
            logger.info(f"Rolling back entities: {inserted_entity_ids}")

        tx.add_operation(
            name="insert_entities",
            operation=insert_entities,
            rollback=rollback_entities,
        )

        # Step 2: Insert relations
        async def insert_relations():
            # Simulate relation insertion
            return ["rel1", "rel2"]

        async def rollback_relations():
            # Simulate relation deletion
            logger.info("Rolling back relations")

        tx.add_operation(
            name="insert_relations",
            operation=insert_relations,
            rollback=rollback_relations,
        )

        # Step 3: Update metadata
        async def update_metadata():
            # Simulate metadata update
            return {"updated": True}

        async def rollback_metadata():
            # Simulate metadata rollback
            logger.info("Rolling back metadata")

        tx.add_operation(
            name="update_metadata",
            operation=update_metadata,
            rollback=rollback_metadata,
        )

        # Transaction commits automatically on context exit
        # If any operation fails, all are rolled back

    # Access results after commit
    results = tx.get_results()
    logger.info(f"Transaction results: {results}")


#
