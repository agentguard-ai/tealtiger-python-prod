"""Context management for TealTiger SDK v1.1.x Enterprise Adoption Features.

This module provides ExecutionContext and ContextManager for request tracing
and context propagation.

Part of P0.3: Correlation IDs and Traceability
"""

from .execution_context import (
    ExecutionContext,
    ExecutionContextOptions,
    CONTEXT_HEADERS,
    is_valid_uuid_v4,
    is_valid_correlation_id,
    validate_execution_context,
)
from .context_manager import (
    ContextManager,
    generate_uuid_v4,
    generate_correlation_id,
    generate_span_id,
    generate_trace_id,
)

__all__ = [
    "ExecutionContext",
    "ExecutionContextOptions",
    "CONTEXT_HEADERS",
    "is_valid_uuid_v4",
    "is_valid_correlation_id",
    "validate_execution_context",
    "ContextManager",
    "generate_uuid_v4",
    "generate_correlation_id",
    "generate_span_id",
    "generate_trace_id",
]
