"""Multi-Stage Defense Pipeline — Type Definitions (Python SDK).

Mirrors the TypeScript pipeline types using Python conventions:
- enum.Enum for PipelineStage and RemediationAction
- @dataclass for all structured types
- snake_case naming throughout
- Type hints using typing module

Module: pipeline/types
Requirements: 11.2, 11.5, 11.6
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PipelineStage(str, Enum):
    """Ordered evaluation phases in the defense pipeline."""

    PRE_EXECUTION = "PRE_EXECUTION"
    """Governance checks before the request reaches the LLM provider."""

    EXECUTION = "EXECUTION"
    """The LLM provider call via ObserveProxy."""

    POST_EXECUTION = "POST_EXECUTION"
    """Governance checks after the LLM response is received."""


class RemediationAction(str, Enum):
    """Actions taken when post-execution modules report policy violations."""

    RESAMPLE = "RESAMPLE"
    """Re-invoke the LLM provider with the original request."""

    REDACT = "REDACT"
    """Strip violating content from the response."""

    DENY_RESPONSE = "DENY_RESPONSE"
    """Discard the response entirely."""


# ---------------------------------------------------------------------------
# Action Severity Ordering (MostRestrictiveWins)
# ---------------------------------------------------------------------------

ACTION_SEVERITY: Dict[str, int] = {
    "DENY": 100,
    "DENY_WRITE": 100,
    "DENY_READ": 100,
    "REQUIRE_APPROVAL": 80,
    "REDACT": 70,
    "REDACT_AND_WRITE": 70,
    "DEGRADE": 60,
    "STORE_SUMMARY_ONLY": 60,
    "TRANSFORM": 50,
    "MONITOR": 10,
    "ALLOW": 0,
}
"""Mapping of action strings to severity integers.

Used by the MostRestrictiveWins merge strategy to determine
which action takes precedence when multiple modules produce
conflicting results within a stage.
"""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ModuleEvalDetail:
    """Per-module evaluation result details within a stage.

    Captures the outcome, timing, and metadata for a single module's
    evaluation during a pipeline stage.
    """

    name: str
    """Module name identifier."""

    version: str
    """Module version string."""

    latency_ms: float
    """Evaluation duration in milliseconds."""

    action: str
    """The action produced by this module (e.g., ALLOW, DENY, MONITOR)."""

    reason_codes: List[str] = field(default_factory=list)
    """Reason codes explaining the module's decision."""

    error: Optional[str] = None
    """Error message if the module threw an exception or timed out."""

    metadata: Optional[Dict[str, Any]] = None
    """Additional module-specific metadata."""


@dataclass
class StageDecision:
    """Decision produced by a single pipeline stage.

    Contains the merged action from all modules at the stage,
    timing information, per-module details, and optional TEEC v2.1
    cryptographic provenance fields.
    """

    action: str
    """The merged action for the stage (most restrictive wins)."""

    reason_codes: List[str]
    """All reason codes from evaluated modules."""

    stage: PipelineStage
    """Which pipeline stage produced this decision."""

    latency_ms: float
    """Stage evaluation duration in milliseconds."""

    module_details: List[ModuleEvalDetail] = field(default_factory=list)
    """Per-module evaluation details."""

    remediation: Optional[Dict[str, Any]] = None
    """Remediation details (PostExecution only).

    When present, contains:
    - action: RemediationAction value
    - triggered_by: module name that triggered the violation
    - attempt: current remediation attempt number
    """

    # TEEC v2.1 fields (present when seal_secret is configured)
    intent_ref: Optional[str] = None
    """SHA-256 hash of the serialized input payload (request or response)."""

    receipt_ref: Optional[str] = None
    """SHA-256 hash linking this decision to the prior decision in the chain."""

    seq: Optional[int] = None
    """Per-agent monotonically increasing sequence number."""

    running_count: Optional[int] = None
    """Global decision counter across all agents."""

    normalization_id: Optional[str] = None
    """SHA-256 hash of the canonically normalized input payload."""

    governance_seal: Optional[Dict[str, Any]] = None
    """Cryptographic seal binding all decision fields.

    When present, contains:
    - hmac: hex-encoded HMAC-SHA256
    - timestamp: Unix milliseconds
    - agent_id: identity of the producing agent
    """


@dataclass
class PipelineTimingMetadata:
    """Detailed timing metadata for a pipeline execution.

    All timestamps are Unix milliseconds. Null values indicate
    stages that were not reached (e.g., execution/post-execution
    when blocked at pre-execution).
    """

    pipeline_entry: float
    """Timestamp when the pipeline execution started."""

    pre_execution_start: float
    """Timestamp when pre-execution evaluation began."""

    pre_execution_end: float
    """Timestamp when pre-execution evaluation completed."""

    execution_start: Optional[float] = None
    """Timestamp when execution stage began (None if blocked pre-execution)."""

    execution_end: Optional[float] = None
    """Timestamp when execution stage completed."""

    post_execution_start: Optional[float] = None
    """Timestamp when post-execution evaluation began."""

    post_execution_end: Optional[float] = None
    """Timestamp when post-execution evaluation completed."""

    hook_time_ms: float = 0.0
    """Total accumulated hook execution time in milliseconds."""

    remediation_attempts: List[Dict[str, float]] = field(default_factory=list)
    """List of remediation attempt timing records.

    Each entry contains:
    - start: timestamp when remediation attempt began
    - end: timestamp when remediation attempt completed
    """


@dataclass
class ExecutionMetadata:
    """Metadata extracted from the LLM provider response via ObserveProxy."""

    model: str
    """Model identifier used for the request."""

    latency_ms: float
    """Provider call duration in milliseconds."""

    usage: Dict[str, int] = field(default_factory=lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    })
    """Token usage breakdown (input_tokens, output_tokens, total_tokens)."""

    cost_usd: float = 0.0
    """Estimated cost in USD for the provider call."""


@dataclass
class ExecutionResult:
    """Result from the execution stage (LLM provider call)."""

    success: bool
    """Whether the provider call completed successfully."""

    response: Any = None
    """The raw LLM provider response (None on failure)."""

    metadata: Optional[ExecutionMetadata] = None
    """Provider response metadata (None on failure)."""

    error: Optional[Dict[str, str]] = None
    """Error details when the provider call fails.

    When present, contains:
    - message: human-readable error description
    - code: optional error code from the provider
    """


@dataclass
class PipelineResult:
    """Composite result from a complete pipeline execution.

    Contains the final governance outcome, the LLM response (when allowed),
    all stage decisions, timing metadata, and remediation details.
    """

    allowed: bool
    """Whether the response was ultimately delivered to the caller."""

    response: Any = None
    """The LLM response (None when blocked/denied)."""

    pre_decision: Optional[StageDecision] = None
    """Pre-execution stage decision."""

    post_decision: Optional[StageDecision] = None
    """Post-execution stage decision (None if blocked pre-execution)."""

    blocked_stage: Optional[PipelineStage] = None
    """Stage that caused blocking, if any."""

    total_latency_ms: float = 0.0
    """Wall-clock time from pipeline entry to result (ms)."""

    resample_count: int = 0
    """Number of resample attempts (0 if none)."""

    remediation_action: Optional[RemediationAction] = None
    """Final remediation action taken, or None."""

    redacted: bool = False
    """Whether the response was redacted."""

    remediation_exhausted: bool = False
    """Whether the resample budget was exhausted."""

    provider_error: bool = False
    """Whether the provider threw an error."""

    provider_error_details: Optional[Dict[str, str]] = None
    """Provider error details (message, code) when provider_error is True."""

    decisions: List[StageDecision] = field(default_factory=list)
    """Chronologically ordered stage decisions."""

    timing: Optional[PipelineTimingMetadata] = None
    """Detailed timing metadata."""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the pipeline result to a JSON-compatible dictionary.

        Produces a complete, lossless representation of the pipeline execution
        suitable for audit logging and offline analysis.
        """
        result: Dict[str, Any] = {
            "allowed": self.allowed,
            "response": self.response,
            "pre_decision": _stage_decision_to_dict(self.pre_decision),
            "post_decision": _stage_decision_to_dict(self.post_decision),
            "blocked_stage": self.blocked_stage.value if self.blocked_stage else None,
            "total_latency_ms": self.total_latency_ms,
            "resample_count": self.resample_count,
            "remediation_action": (
                self.remediation_action.value if self.remediation_action else None
            ),
            "redacted": self.redacted,
            "remediation_exhausted": self.remediation_exhausted,
            "provider_error": self.provider_error,
            "provider_error_details": self.provider_error_details,
            "decisions": [
                _stage_decision_to_dict(d) for d in self.decisions
            ],
            "timing": _timing_to_dict(self.timing),
        }
        return result


@dataclass
class PipelineRequest:
    """Input to the defense pipeline.

    Wraps the raw LLM request payload with optional correlation
    and context information.
    """

    payload: Dict[str, Any]
    """The raw request payload to send to the LLM provider."""

    correlation_id: Optional[str] = None
    """Correlation ID for tracing (auto-generated if omitted)."""

    context: Optional[Dict[str, Any]] = None
    """Additional context for module evaluation."""


@dataclass
class PipelineConfig:
    """Configuration for the DefensePipeline.

    Specifies registered modules per stage, failure policy,
    TEEC v2.1 settings, and lifecycle hooks.
    """

    pre_execution_modules: List[Any] = field(default_factory=list)
    """Modules to run at the PRE_EXECUTION stage (TealModule implementations)."""

    post_execution_modules: List[Any] = field(default_factory=list)
    """Modules to run at the POST_EXECUTION stage (TealModule implementations)."""

    observe_proxy: Optional[Any] = None
    """Existing ObserveProxy instance; if omitted, one is created wrapping provider_client."""

    provider_client: Optional[Any] = None
    """Raw provider client (required if observe_proxy not provided)."""

    seal_secret: Optional[str] = None
    """TEEC v2.1 seal secret — presence enables cryptographic provenance."""

    resample_budget: int = 2
    """Maximum resample attempts for post-execution remediation."""

    fail_closed: bool = True
    """Whether module failures block the request (True) or proceed with monitoring (False)."""

    module_timeout_ms: int = 5000
    """Module evaluation timeout in milliseconds."""

    agent_id: Optional[str] = None
    """Agent identifier for TEEC v2.1 scoping."""

    hooks: Optional[PipelineHooks] = None
    """Pipeline lifecycle hooks."""


@dataclass
class PipelineHooks:
    """Lifecycle hook callbacks for pipeline observability and extension.

    All hooks are optional. Hook exceptions are logged but never propagated —
    hooks observe but do not modify pipeline behavior.
    """

    before_pre_execution: Optional[
        Callable[["PipelineRequest"], Union[None, Awaitable[None]]]
    ] = None
    """Called with the request before pre-execution modules run."""

    after_pre_execution: Optional[
        Callable[["StageDecision"], Union[None, Awaitable[None]]]
    ] = None
    """Called with the stage decision after pre-execution completes."""

    before_execution: Optional[
        Callable[["PipelineRequest"], Union[None, Awaitable[None]]]
    ] = None
    """Called with the request before the provider call."""

    after_execution: Optional[
        Callable[[Any, "ExecutionMetadata"], Union[None, Awaitable[None]]]
    ] = None
    """Called with the response and metadata after the provider call."""

    before_post_execution: Optional[
        Callable[[Any, "PipelineRequest"], Union[None, Awaitable[None]]]
    ] = None
    """Called with the response and request before post-execution modules run."""

    after_post_execution: Optional[
        Callable[["StageDecision"], Union[None, Awaitable[None]]]
    ] = None
    """Called with the stage decision after post-execution completes."""

    on_remediation: Optional[
        Callable[
            ["RemediationAction", "StageDecision", int],
            Union[None, Awaitable[None]],
        ]
    ] = None
    """Called with the action, decision, and attempt count on each remediation."""


# ---------------------------------------------------------------------------
# Serialization Helpers
# ---------------------------------------------------------------------------


def _module_eval_detail_to_dict(detail: ModuleEvalDetail) -> Dict[str, Any]:
    """Serialize a ModuleEvalDetail to a dictionary."""
    result: Dict[str, Any] = {
        "name": detail.name,
        "version": detail.version,
        "latency_ms": detail.latency_ms,
        "action": detail.action,
        "reason_codes": detail.reason_codes,
    }
    if detail.error is not None:
        result["error"] = detail.error
    if detail.metadata is not None:
        result["metadata"] = detail.metadata
    return result


def _stage_decision_to_dict(
    decision: Optional[StageDecision],
) -> Optional[Dict[str, Any]]:
    """Serialize a StageDecision to a dictionary."""
    if decision is None:
        return None

    result: Dict[str, Any] = {
        "action": decision.action,
        "reason_codes": decision.reason_codes,
        "stage": decision.stage.value,
        "latency_ms": decision.latency_ms,
        "module_details": [
            _module_eval_detail_to_dict(d) for d in decision.module_details
        ],
    }

    if decision.remediation is not None:
        result["remediation"] = decision.remediation
    if decision.intent_ref is not None:
        result["intent_ref"] = decision.intent_ref
    if decision.receipt_ref is not None:
        result["receipt_ref"] = decision.receipt_ref
    if decision.seq is not None:
        result["seq"] = decision.seq
    if decision.running_count is not None:
        result["running_count"] = decision.running_count
    if decision.normalization_id is not None:
        result["normalization_id"] = decision.normalization_id
    if decision.governance_seal is not None:
        result["governance_seal"] = decision.governance_seal

    return result


def _timing_to_dict(
    timing: Optional[PipelineTimingMetadata],
) -> Optional[Dict[str, Any]]:
    """Serialize PipelineTimingMetadata to a dictionary."""
    if timing is None:
        return None

    return {
        "pipeline_entry": timing.pipeline_entry,
        "pre_execution_start": timing.pre_execution_start,
        "pre_execution_end": timing.pre_execution_end,
        "execution_start": timing.execution_start,
        "execution_end": timing.execution_end,
        "post_execution_start": timing.post_execution_start,
        "post_execution_end": timing.post_execution_end,
        "hook_time_ms": timing.hook_time_ms,
        "remediation_attempts": timing.remediation_attempts,
    }
