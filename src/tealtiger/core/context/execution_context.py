"""ExecutionContext for request tracking and traceability.

TealTiger SDK v1.1.x - Enterprise Adoption Features
P0.3: Correlation IDs and Traceability

This module defines ExecutionContext for request tracking across all TealTiger components.
"""

import re
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ExecutionContext(BaseModel):
    """Execution context for request tracking and traceability.
    
    Contains correlation ID, trace ID, and optional governance metadata.
    
    Attributes:
        correlation_id: Unique correlation ID for request tracing (UUID v4)
        trace_id: Optional trace ID for distributed tracing (OpenTelemetry-compatible)
        workflow_id: Optional workflow ID for governance-grade aggregation
        run_id: Optional run ID for execution instance tracking
        span_id: Optional span ID for operation tracking
        parent_span_id: Optional parent span ID for nested operations
        tenant_id: Optional tenant ID for multi-tenancy
        application: Optional application name
        environment: Optional environment (e.g., 'production', 'staging', 'development')
        agent_purpose: Optional agent purpose or role
        session_id: Optional session ID for multi-request conversations
        user_id: Optional user ID for user-level tracking
        created_at: Timestamp when context was created (ISO 8601)
        metadata: Additional custom metadata
    """

    correlation_id: str = Field(
        ...,
        description="Unique correlation ID for request tracing (UUID v4)",
    )

    trace_id: Optional[str] = Field(
        None,
        description="Optional trace ID for distributed tracing (OpenTelemetry-compatible)",
    )

    workflow_id: Optional[str] = Field(
        None,
        description="Optional workflow ID for governance-grade aggregation",
    )

    run_id: Optional[str] = Field(
        None,
        description="Optional run ID for execution instance tracking",
    )

    span_id: Optional[str] = Field(
        None,
        description="Optional span ID for operation tracking",
    )

    parent_span_id: Optional[str] = Field(
        None,
        description="Optional parent span ID for nested operations",
    )

    tenant_id: Optional[str] = Field(
        None,
        description="Optional tenant ID for multi-tenancy",
    )

    application: Optional[str] = Field(
        None,
        description="Optional application name",
    )

    environment: Optional[str] = Field(
        None,
        description="Optional environment (e.g., 'production', 'staging', 'development')",
    )

    agent_purpose: Optional[str] = Field(
        None,
        description="Optional agent purpose or role",
    )

    session_id: Optional[str] = Field(
        None,
        description="Optional session ID for multi-request conversations",
    )

    user_id: Optional[str] = Field(
        None,
        description="Optional user ID for user-level tracking",
    )

    created_at: Optional[str] = Field(
        None,
        description="Timestamp when context was created (ISO 8601)",
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional custom metadata",
    )

    class Config:
        """Pydantic configuration."""

        # Allow extra fields for forward compatibility
        extra = "allow"


class ExecutionContextOptions(BaseModel):
    """Options for creating an ExecutionContext.
    
    All fields are optional. If correlation_id is not provided, it will be auto-generated.
    """

    correlation_id: Optional[str] = Field(
        None,
        description="Existing correlation ID (if not provided, will be auto-generated)",
    )

    trace_id: Optional[str] = Field(
        None,
        description="Trace ID for distributed tracing",
    )

    workflow_id: Optional[str] = Field(
        None,
        description="Workflow ID for governance-grade aggregation",
    )

    run_id: Optional[str] = Field(
        None,
        description="Run ID for execution instance tracking",
    )

    span_id: Optional[str] = Field(
        None,
        description="Span ID for operation tracking",
    )

    parent_span_id: Optional[str] = Field(
        None,
        description="Parent span ID for nested operations",
    )

    tenant_id: Optional[str] = Field(
        None,
        description="Tenant ID for multi-tenancy",
    )

    application: Optional[str] = Field(
        None,
        description="Application name",
    )

    environment: Optional[str] = Field(
        None,
        description="Environment",
    )

    agent_purpose: Optional[str] = Field(
        None,
        description="Agent purpose or role",
    )

    session_id: Optional[str] = Field(
        None,
        description="Session ID",
    )

    user_id: Optional[str] = Field(
        None,
        description="User ID",
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional custom metadata",
    )

    class Config:
        """Pydantic configuration."""

        # Allow extra fields for forward compatibility
        extra = "allow"


# HTTP header names for context propagation
# Follows W3C Trace Context and OpenTelemetry conventions
CONTEXT_HEADERS = {
    "CORRELATION_ID": "x-correlation-id",
    "TRACE_ID": "traceparent",
    "WORKFLOW_ID": "x-workflow-id",
    "RUN_ID": "x-run-id",
    "SPAN_ID": "x-span-id",
    "PARENT_SPAN_ID": "x-parent-span-id",
    "TENANT_ID": "x-tenant-id",
    "APPLICATION": "x-application",
    "ENVIRONMENT": "x-environment",
    "AGENT_PURPOSE": "x-agent-purpose",
    "SESSION_ID": "x-session-id",
    "USER_ID": "x-user-id",
}


def is_valid_uuid_v4(uuid: str) -> bool:
    """Validates that a string is a valid UUID v4.
    
    Args:
        uuid: The string to validate
        
    Returns:
        True if valid UUID v4, False otherwise
    """
    uuid_v4_regex = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    return bool(uuid_v4_regex.match(uuid))


def is_valid_correlation_id(correlation_id: str) -> bool:
    """Validates that a correlation ID is valid (non-empty string, preferably UUID v4).
    
    Args:
        correlation_id: The correlation ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    return isinstance(correlation_id, str) and len(correlation_id) > 0


def validate_execution_context(context: ExecutionContext) -> None:
    """Validates that an ExecutionContext has all required fields.
    
    Args:
        context: The context to validate
        
    Raises:
        ValueError: If context is invalid
    """
    if not context:
        raise ValueError("ExecutionContext is required")

    if not is_valid_correlation_id(context.correlation_id):
        raise ValueError("ExecutionContext must have a non-empty correlation_id")
