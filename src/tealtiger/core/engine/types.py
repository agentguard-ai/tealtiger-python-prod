"""Type definitions for TealTiger SDK v1.1.x Enterprise Adoption Features.

This module defines the core types for:
- P0.1: Policy Rollout Modes (ENFORCE, MONITOR, REPORT_ONLY)
- P0.2: Deterministic Decision Contract (stable typed Decision object)
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PolicyMode(str, Enum):
    """Policy rollout modes for safe policy deployment.
    
    Part of P0.1: Policy Rollout Modes
    """

    ENFORCE = "ENFORCE"
    """Block violations, allow compliant requests (production mode)"""

    MONITOR = "MONITOR"
    """Allow all requests but log violations (observability mode)"""

    REPORT_ONLY = "REPORT_ONLY"
    """Allow all requests, no violation logging (testing mode)"""


class DecisionAction(str, Enum):
    """Actions that can be taken on a request.
    
    Part of P0.2: Deterministic Decision Contract
    """

    ALLOW = "ALLOW"
    """Request is allowed to proceed"""

    DENY = "DENY"
    """Request is blocked"""

    REDACT = "REDACT"
    """Redact sensitive content"""

    TRANSFORM = "TRANSFORM"
    """Request is modified before proceeding"""

    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    """Require manual approval"""

    DEGRADE = "DEGRADE"
    """Degrade service quality"""


class ReasonCode(str, Enum):
    """Standardized reason codes for decisions.
    
    Part of P0.2: Deterministic Decision Contract
    """

    # Policy compliance
    POLICY_COMPLIANT = "POLICY_COMPLIANT"
    """Request complies with all policies"""

    POLICY_PASSED = "POLICY_PASSED"
    """Policy evaluation passed"""

    POLICY_VIOLATION = "POLICY_VIOLATION"
    """Request violates one or more policies"""

    # Content safety
    PII_DETECTED = "PII_DETECTED"
    """Personally Identifiable Information detected"""

    PROMPT_INJECTION_DETECTED = "PROMPT_INJECTION_DETECTED"
    """Prompt injection attempt detected"""

    HARMFUL_CONTENT_DETECTED = "HARMFUL_CONTENT_DETECTED"
    """Harmful content detected"""

    UNSAFE_CODE_DETECTED = "UNSAFE_CODE_DETECTED"
    """Unsafe code detected"""

    CODE_LENGTH_EXCEEDED = "CODE_LENGTH_EXCEEDED"
    """Code length exceeded"""

    BLOCKED_FUNCTION_DETECTED = "BLOCKED_FUNCTION_DETECTED"
    """Blocked function detected"""

    # Tool misuse (ASI02)
    TOOL_NOT_ALLOWED = "TOOL_NOT_ALLOWED"
    """Tool is not allowed"""

    TOOL_PARAMETER_INVALID = "TOOL_PARAMETER_INVALID"
    """Tool parameter is invalid"""

    TOOL_RATE_LIMIT_EXCEEDED = "TOOL_RATE_LIMIT_EXCEEDED"
    """Tool rate limit exceeded"""

    TOOL_SIZE_LIMIT_EXCEEDED = "TOOL_SIZE_LIMIT_EXCEEDED"
    """Tool size limit exceeded"""

    # Identity violations
    PERMISSION_DENIED = "PERMISSION_DENIED"
    """Permission denied"""

    FORBIDDEN_ACTION = "FORBIDDEN_ACTION"
    """Forbidden action"""

    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    """Authentication failed"""

    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    """Authorization failed"""

    # Cost governance (FinOps)
    COST_LIMIT_EXCEEDED = "COST_LIMIT_EXCEEDED"
    """Cost limit exceeded"""

    COST_BUDGET_EXCEEDED = "COST_BUDGET_EXCEEDED"
    """Cost budget exceeded"""

    COST_THRESHOLD_APPROACHING = "COST_THRESHOLD_APPROACHING"
    """Cost threshold approaching"""

    COST_ANOMALY_DETECTED = "COST_ANOMALY_DETECTED"
    """Cost anomaly detected"""

    MODEL_TIER_NOT_ALLOWED = "MODEL_TIER_NOT_ALLOWED"
    """Model tier not allowed"""

    MODEL_DOWNGRADED = "MODEL_DOWNGRADED"
    """Model downgraded"""

    PROMPT_TRUNCATED_FOR_COST = "PROMPT_TRUNCATED_FOR_COST"
    """Prompt truncated for cost"""

    APPROVAL_REQUIRED_FOR_COST = "APPROVAL_REQUIRED_FOR_COST"
    """Approval required for cost"""

    # Behavioral violations
    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    """Anomaly detected"""

    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    """Rate limit exceeded"""

    # Circuit breaker
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    """Circuit breaker is open"""

    CIRCUIT_HALF_OPEN = "CIRCUIT_HALF_OPEN"
    """Circuit breaker is in half-open state"""

    # Mode-specific
    MONITOR_MODE_VIOLATION = "MONITOR_MODE_VIOLATION"
    """Monitor mode violation"""

    REPORT_ONLY_MODE = "REPORT_ONLY_MODE"
    """Report only mode"""

    # General
    INVALID_REQUEST = "INVALID_REQUEST"
    """Request is invalid or malformed"""


class ModeConfig(BaseModel):
    """Configuration for policy rollout modes.
    
    Part of P0.1: Policy Rollout Modes
    
    Priority: policy-specific > environment-specific > global default
    """

    default: PolicyMode = Field(
        default=PolicyMode.ENFORCE,
        description="Global default mode for all policies",
        alias="defaultMode",
    )

    environment: Dict[str, PolicyMode] = Field(
        default_factory=dict,
        description="Environment-specific mode overrides (e.g., {'staging': 'MONITOR'})",
    )

    policy: Dict[str, PolicyMode] = Field(
        default_factory=dict,
        description="Policy-specific mode overrides (e.g., {'pii-detection': 'ENFORCE'})",
    )

    class Config:
        """Pydantic configuration."""

        # Allow both 'default' and 'defaultMode' for API compatibility
        populate_by_name = True


class Decision(BaseModel):
    """Deterministic decision contract for policy evaluation.
    
    Part of P0.2: Deterministic Decision Contract
    
    This is the stable, typed decision object returned by all TealTiger components
    (TealEngine, TealGuard, TealCircuit, TealAudit).
    """

    action: DecisionAction = Field(
        ...,
        description="Action to take (ALLOW, DENY, TRANSFORM)",
    )

    reason_codes: List[ReasonCode] = Field(
        ...,
        description="Standardized reason codes explaining the decision",
    )

    risk_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Risk score (0-100, where 0 is no risk and 100 is maximum risk)",
    )

    mode: PolicyMode = Field(
        ...,
        description="Policy mode that produced this decision",
    )

    policy_id: str = Field(
        ...,
        description="ID of the policy that made the decision",
    )

    policy_version: str = Field(
        ...,
        description="Version of the policy",
    )

    component_versions: Dict[str, str] = Field(
        ...,
        description="Versions of TealTiger components (sdk, engine, guard, circuit, monitor)",
    )

    correlation_id: str = Field(
        ...,
        description="Correlation ID for tracing (from ExecutionContext)",
    )

    reason: str = Field(
        ...,
        description="Human-readable reason for the decision",
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the decision",
    )

    # Optional fields for distributed tracing
    trace_id: Optional[str] = Field(
        None,
        description="Distributed trace ID (OpenTelemetry compatible)",
    )

    workflow_id: Optional[str] = Field(
        None,
        description="Workflow identifier for multi-step processes",
    )

    run_id: Optional[str] = Field(
        None,
        description="Run identifier for workflow executions",
    )

    span_id: Optional[str] = Field(
        None,
        description="Span ID for distributed tracing",
    )

    parent_span_id: Optional[str] = Field(
        None,
        description="Parent span ID for distributed tracing",
    )

    # Optional fields for transformed requests
    transformed_request: Optional[Dict[str, Any]] = Field(
        None,
        description="Transformed request if action is TRANSFORM",
    )

    provider: Optional[str] = Field(
        None,
        description="LLM provider (openai, anthropic, etc.)",
    )
