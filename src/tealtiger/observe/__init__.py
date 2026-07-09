"""
TealTiger observe() — Zero-config LLM instrumentation module.

Provides a single-function wrapper that instruments any supported LLM provider
client with cost tracking, audit logging, behavioral baseline construction,
and PII detection — all without configuration files or policy definitions.

Usage:
    from tealtiger.observe import observe, freeze, unfreeze

    client = observe(OpenAI())
    # client is now instrumented with full visibility

Requirements: 8.1, 8.4
"""

from tealtiger.observe.types import (
    ObserveConfig,
    ObserveCostSummary,
    BaselineResult,
    PIIDetectionSummary,
)
from tealtiger.observe.errors import UnsupportedProviderError, FrozenAgentError
from tealtiger.observe.observe import observe
from tealtiger.observe.freeze_registry import freeze, unfreeze
from tealtiger.core.engine.v2_1.errors import SealConfigurationError


__all__ = [
    # Main API functions
    "observe",
    "freeze",
    "unfreeze",
    # Types
    "ObserveConfig",
    "ObserveCostSummary",
    "BaselineResult",
    "PIIDetectionSummary",
    # Errors
    "UnsupportedProviderError",
    "FrozenAgentError",
    "SealConfigurationError",
]
