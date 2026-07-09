"""
Shared types for the observe() zero-config instrumentation module.

These types define the dataclasses for ObserveProxy, provider detection,
cost tracking, behavioral baseline, and PII scanning in the Python SDK.

Requirements: 8.1, 8.4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Literal, Optional, Any


# --- Provider Types ---

SupportedProvider = Literal[
    'openai',
    'anthropic',
    'gemini',
    'bedrock',
    'azure-openai',
    'cohere',
    'mistral',
    'deepseek',
    'groq',
    'xai',
    'together',
    'hf-tgi',
]
"""The 12 supported LLM provider types that observe() can wrap."""


@dataclass
class ToolCallInfo:
    """Information about a tool call detected in a provider response."""

    tool_name: str
    argument_count: int
    arguments_hash: str
    """SHA-256 hash of the serialized arguments."""


@dataclass
class ProviderSignature:
    """Provider-specific signature defining how to interact with a provider client."""

    provider: str  # One of SupportedProvider values
    intercept_methods: List[str]
    """Method paths that indicate LLM API calls to intercept."""
    usage_extractor: Callable[[Any], Optional[Any]]
    """Extract token usage from this provider's response."""
    model_extractor: Callable[[Any, Any], str]
    """Extract model name from request/response."""
    tool_call_extractor: Callable[[Any], List[ToolCallInfo]]
    """Extract tool calls from the response."""


# --- Observe Config ---

@dataclass
class ObserveConfig:
    """
    Optional configuration for observe().

    If omitted, agent_id and session_id are auto-generated as UUID v4.
    When governance is enabled, TEEC v2.1 decisions are produced for
    each intercepted call.
    """

    agent_id: Optional[str] = None
    """Agent identifier. Auto-generated UUID v4 if omitted."""
    session_id: Optional[str] = None
    """Session identifier. Auto-generated UUID v4 if omitted."""
    baseline_window: int = 100
    """Number of requests for baseline computation. Default: 100."""
    governance: bool = False
    """When True, enable TEEC v2.1 governance decision production."""
    governance_seal_secret: Optional[str] = None
    """Seal secret for HMAC computation. Required when governance=True."""


# --- Cost Types ---

@dataclass
class CostBreakdownSummary:
    """Breakdown of cost by category."""

    input_cost: float = 0.0
    output_cost: float = 0.0
    image_cost: float = 0.0
    audio_cost: float = 0.0


@dataclass
class ObserveCostSummary:
    """
    Summary of accumulated cost for a session or agent.

    Named ObserveCostSummary to avoid collision with tealtiger.cost.types.CostSummary.
    """

    total_cost: float = 0.0
    """Total accumulated cost in USD."""
    request_count: int = 0
    """Number of requests processed."""
    has_pricing_gaps: bool = False
    """Whether any request had pricing unavailable."""
    breakdown: CostBreakdownSummary = field(default_factory=CostBreakdownSummary)
    """Breakdown by cost category."""


@dataclass
class RequestCostResult:
    """Cost result for a single request."""

    request_id: str = ""
    cost: float = 0.0
    pricing_unavailable: bool = False
    breakdown: CostBreakdownSummary = field(default_factory=CostBreakdownSummary)


# --- Baseline Types ---

@dataclass
class BaselineSample:
    """A single sample for behavioral baseline computation."""

    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    tool_call_count: int = 0


@dataclass
class PercentileStats:
    """Percentile statistics (P50, P95, P99) for a metric."""

    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0


@dataclass
class BaselineStats:
    """Computed statistics for all tracked metrics in the baseline."""

    latency_ms: PercentileStats = field(default_factory=PercentileStats)
    input_tokens: PercentileStats = field(default_factory=PercentileStats)
    output_tokens: PercentileStats = field(default_factory=PercentileStats)
    cost_usd: PercentileStats = field(default_factory=PercentileStats)
    tool_call_count: PercentileStats = field(default_factory=PercentileStats)


@dataclass
class BaselineResult:
    """Result of behavioral baseline computation."""

    is_complete: bool = False
    """Whether the baseline has collected enough samples."""
    sample_count: int = 0
    """Number of samples collected so far."""
    window_size: int = 100
    """Target window size."""
    stats: Optional[BaselineStats] = None
    """Computed statistics (None if baseline is incomplete)."""


# --- PII Types ---

@dataclass
class PIIDetectionSummary:
    """Summary of PII detections in a payload."""

    count: int = 0
    """Number of PII instances detected."""
    types: List[str] = field(default_factory=list)
    """Types found (e.g., ['email', 'ssn'])."""
    phase: str = "request"
    """Whether detection was in 'request' or 'response'."""
