"""
TealAudit - Versioned Audit Event Types

Defines the versioned audit event schema with security-by-default redaction.
Part of TealTiger v1.1.x - Enterprise Adoption Features (P0.4)
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator
import re

from ..engine.types import PolicyMode, DecisionAction, ReasonCode


# Audit schema version
# Incremented when breaking changes are made to the AuditEvent schema
AUDIT_SCHEMA_VERSION = "1.0.0"


class AuditEventType(str, Enum):
    """
    Audit event type enumeration
    Categorizes different types of audit events for filtering and analysis
    """

    POLICY_EVALUATION = "policy.evaluation"
    GUARDRAIL_CHECK = "guardrail.check"
    LLM_REQUEST = "llm.request"
    LLM_RESPONSE = "llm.response"
    TOOL_EXECUTION = "tool.execution"
    CIRCUIT_STATE_CHANGE = "circuit.state_change"
    ANOMALY_DETECTED = "anomaly.detected"
    COST_THRESHOLD_EXCEEDED = "cost.threshold_exceeded"
    COST_EVALUATION = "cost.evaluation"
    COST_BUDGET_EXCEEDED = "cost.budget_exceeded"


class SafeContent(BaseModel):
    """
    Safe content metadata (redacted)
    Contains metadata about content without exposing raw sensitive data
    """

    hash: Optional[str] = Field(
        None, description="SHA-256 hash of the content (for HASH redaction level)"
    )
    size: Optional[int] = Field(None, description="Size of the content in bytes")
    category: Optional[str] = Field(
        None,
        description="Category or type of content (e.g., 'prompt', 'response', 'tool_params')",
    )


class AuditComponentVersions(BaseModel):
    """
    Component version information
    Tracks which TealTiger components were involved in the event
    """

    sdk: Optional[str] = Field(None, description="SDK version")
    engine: Optional[str] = Field(None, description="TealEngine version")
    guard: Optional[str] = Field(None, description="TealGuard version")
    circuit: Optional[str] = Field(None, description="TealCircuit version")
    monitor: Optional[str] = Field(None, description="TealMonitor version")


BudgetScope = Literal["request", "session", "agent", "tenant"]


class CostMetadata(BaseModel):
    """
    Cost governance metadata
    Standardized cost fields for FinOps and budget tracking
    """

    estimated: Optional[float] = Field(
        None, description="Estimated cost computed prior to provider execution"
    )
    actual: Optional[float] = Field(
        None,
        description="Actual cost computed from provider usage metrics (if available)",
    )
    currency: Optional[str] = Field(
        "USD", description="Currency for cost values (default: USD)"
    )
    budget_scope: Optional[BudgetScope] = Field(
        None, description="Budget scope applied (request/session/agent/tenant)"
    )
    budget_window: Optional[str] = Field(
        None, description="Budget window (e.g., per_request / per_session / daily / hourly)"
    )
    budget_limit: Optional[float] = Field(
        None, description="Budget limit used for evaluation"
    )
    budget_remaining: Optional[float] = Field(
        None, description="Remaining budget at time of evaluation (if tracked)"
    )
    risk_score: Optional[float] = Field(
        None, description="Cost risk score (0-100), if computed separately"
    )
    model: Optional[str] = Field(
        None, description="Model name (if model-aware cost policy applies)"
    )
    model_tier: Optional[str] = Field(
        None, description="Model tier (if model-aware cost policy applies)"
    )


class AuditEvent(BaseModel):
    """
    Versioned audit event

    This is the canonical audit event structure used throughout TealTiger.
    All audit events MUST include schema_version, event_type, timestamp, and correlation_id.

    Security-by-default: Raw prompts and responses are NEVER included by default.
    Use safe_inputs and safe_outputs for redacted content metadata.
    """

    schema_version: str = Field(
        AUDIT_SCHEMA_VERSION, description="Schema version (e.g., '1.0.0')"
    )
    event_type: AuditEventType = Field(..., description="Event type")
    timestamp: str = Field(..., description="Timestamp in ISO 8601 format")
    correlation_id: str = Field(
        ..., description="Correlation ID for request tracing (required)"
    )

    # Optional tracing fields
    trace_id: Optional[str] = Field(
        None, description="Trace ID for distributed tracing (optional)"
    )
    workflow_id: Optional[str] = Field(
        None, description="Workflow ID for governance-grade aggregation (optional)"
    )
    run_id: Optional[str] = Field(
        None, description="Run ID for execution instance tracking (optional)"
    )
    span_id: Optional[str] = Field(
        None, description="Span ID for operation tracking (optional)"
    )
    parent_span_id: Optional[str] = Field(
        None, description="Parent span ID for nested operations (optional)"
    )

    # Policy metadata
    policy_id: Optional[str] = Field(None, description="Policy ID that was evaluated")
    policy_version: Optional[str] = Field(None, description="Policy version")
    mode: Optional[PolicyMode] = Field(
        None, description="Evaluation mode used (ENFORCE, MONITOR, REPORT_ONLY)"
    )

    # Decision metadata
    action: Optional[DecisionAction] = Field(
        None, description="Decision action (ALLOW, DENY, REDACT, etc.)"
    )
    reason_codes: Optional[List[ReasonCode]] = Field(
        None, description="Reason codes explaining the decision"
    )
    risk_score: Optional[float] = Field(None, description="Risk score (0-100)")

    # Agent and provider metadata
    agent_id: Optional[str] = Field(None, description="Agent identifier")
    provider: Optional[str] = Field(
        None, description="LLM provider (e.g., 'openai', 'anthropic')"
    )
    model: Optional[str] = Field(
        None, description="Model name (e.g., 'gpt-4', 'claude-3-opus')"
    )

    # Cost and duration
    cost: Optional[float] = Field(
        None,
        description="Cost (deprecated): prefer metadata.cost.* standardized keys. Kept for backwards compatibility.",
    )
    duration: Optional[float] = Field(
        None, description="Duration of the operation in milliseconds"
    )

    # Safe content (redacted)
    safe_inputs: Optional[SafeContent] = Field(
        None, description="Safe inputs (redacted content metadata)"
    )
    safe_outputs: Optional[SafeContent] = Field(
        None, description="Safe outputs (redacted content metadata)"
    )

    # Error handling
    error: Optional[str] = Field(None, description="Error message if operation failed")

    # Component versions
    component_versions: Optional[AuditComponentVersions] = Field(
        None, description="Component versions involved in the event"
    )

    # Additional metadata
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional metadata (non-sensitive). Cost fields MUST be placed under metadata.cost",
    )

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate ISO 8601 timestamp format"""
        # Basic ISO 8601 format check
        iso_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3,6})?(Z|[+-]\d{2}:\d{2})?$"
        if not re.match(iso_pattern, v):
            raise ValueError(f"Invalid ISO 8601 timestamp format: {v}")
        return v

    @field_validator("correlation_id")
    @classmethod
    def validate_correlation_id(cls, v: str) -> str:
        """Validate correlation_id is non-empty"""
        if not v or not v.strip():
            raise ValueError("correlation_id must be non-empty")
        return v

    model_config = {"use_enum_values": True}


def is_valid_audit_event_type(event_type: Any) -> bool:
    """
    Validates that an AuditEventType value is valid

    Args:
        event_type: The event type to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        AuditEventType(event_type)
        return True
    except (ValueError, TypeError):
        return False


def validate_audit_event(event: AuditEvent) -> None:
    """
    Validates that an AuditEvent has all required fields

    Args:
        event: The audit event to validate

    Raises:
        ValueError: if event is invalid
    """
    if not event:
        raise ValueError("AuditEvent is required")

    if not event.schema_version or not isinstance(event.schema_version, str):
        raise ValueError("AuditEvent must have a valid schema_version")

    if not is_valid_audit_event_type(event.event_type):
        raise ValueError(f"Invalid audit event type: {event.event_type}")

    if not event.timestamp or not isinstance(event.timestamp, str):
        raise ValueError("AuditEvent must have a valid ISO 8601 timestamp")

    if not event.correlation_id or not isinstance(event.correlation_id, str):
        raise ValueError("AuditEvent must have a non-empty correlation_id")


def create_audit_event(
    event_type: AuditEventType,
    correlation_id: str,
    **kwargs: Any,
) -> AuditEvent:
    """
    Creates a new AuditEvent with required fields

    Args:
        event_type: Event type
        correlation_id: Correlation ID for tracing
        **kwargs: Optional partial event data

    Returns:
        Complete AuditEvent with defaults
    """
    event = AuditEvent(
        schema_version=AUDIT_SCHEMA_VERSION,
        event_type=event_type,
        timestamp=datetime.utcnow().isoformat() + "Z",
        correlation_id=correlation_id,
        **kwargs,
    )

    validate_audit_event(event)
    return event
