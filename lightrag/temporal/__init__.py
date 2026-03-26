"""
Temporal module for LightRAG - Thread-safe sequence management and transaction support.

This module provides critical fixes for temporal logic issues:
- Issue #6: Race condition in sequence index generation
- Issue #16: Atomic batch operations
- Issue #17: Transaction support with rollback

Usage:
    from lightrag.temporal import SequenceIndexManager, TransactionManager, transaction

    # Sequence management
    manager = SequenceIndexManager(doc_status_storage)
    seq_idx = await manager.get_next_sequence_index()

    # Transaction support
    async with transaction() as tx:
        tx.add_operation("op1", operation_func, rollback=rollback_func)
        # Automatic commit/rollback
"""

from .edge_cases import (
    EdgeCaseHandler,
    handle_empty_results,
    safe_concurrent_delete,
    validate_version_format,
)
from .filtering import (
    filter_by_date,
    filter_by_version,
)
from .i18n import (
    I18nError,
    I18nWarning,
    add_language,
    get_language,
    get_message,
    get_supported_languages,
    set_language,
)
from .sequence_manager import SequenceIndexManager
from .transaction_manager import (
    TransactionError,
    TransactionManager,
    TransactionRollbackError,
    TransactionTimeoutError,
    transaction,
)
from .utils import (
    DateValidator,
    TemporalUtils,
    validate_and_parse_date,
)

__all__ = [
    # Sequence Management
    "SequenceIndexManager",
    # Transaction Management
    "TransactionManager",
    "transaction",
    "TransactionError",
    "TransactionRollbackError",
    "TransactionTimeoutError",
    # Utilities
    "TemporalUtils",
    "DateValidator",
    "validate_and_parse_date",
    # Filtering
    "filter_by_version",
    "filter_by_date",
    # Edge Case Handling
    "validate_version_format",
    "handle_empty_results",
    "safe_concurrent_delete",
    "EdgeCaseHandler",
    # Internationalization
    "get_message",
    "set_language",
    "get_language",
    "get_supported_languages",
    "add_language",
    "I18nError",
    "I18nWarning",
]

#
