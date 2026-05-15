"""TealTiger v1.3 — Governance Adapter Base (Python SDK).

Defines the GovernanceAdapter Protocol and BaseGovernanceAdapter abstract class
for all platform adapters. All adapters translate between platform-specific
contracts and TealTiger's GovernanceRequest, using the same TealEngineV13
evaluation logic internally.

Cross-platform guarantee: identical inputs → identical Decisions regardless
of which platform adapter is used.

Module: adapters/base
Requirements: 14.13, 14.14, 14.16
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Protocol, runtime_checkable

from ..core.engine.v1_3 import DecisionV13, GovernanceRequest, TealEngineV13

__all__ = [
    "PlatformType",
    "PlatformDecision",
    "GovernanceAdapter",
    "BaseGovernanceAdapter",
]


# ── Types ─────────────────────────────────────────────────────────

PlatformType = Literal["bedrock", "agentcore", "azure"]
"""Supported platform identifiers."""


@dataclass
class PlatformDecision:
    """Platform-agnostic decision returned by all adapters.

    Adapters translate this into platform-specific response formats.
    """

    allowed: bool
    """Whether the action is allowed."""

    reason_codes: List[str] = field(default_factory=list)
    """Reason codes from governance evaluation."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional metadata from the decision."""


# ── Protocol ──────────────────────────────────────────────────────

@runtime_checkable
class GovernanceAdapter(Protocol):
    """Common interface for all platform governance adapters.

    Each adapter:
    1. Accepts platform-specific request formats
    2. Translates them to TealTiger's GovernanceRequest
    3. Evaluates via TealEngineV13
    4. Translates the Decision back to platform-specific format
    """

    @property
    def platform(self) -> PlatformType:
        """Platform identifier."""
        ...

    async def evaluate(self, platform_request: Any) -> PlatformDecision:
        """Evaluate a platform-specific request through the governance pipeline.

        Args:
            platform_request: Platform-specific request object.

        Returns:
            Platform-agnostic decision.
        """
        ...

    async def initialize(self, engine: TealEngineV13) -> None:
        """Initialize the adapter with a TealEngine instance.

        Must be called before evaluate().

        Args:
            engine: TealEngineV13 instance for governance evaluation.
        """
        ...


# ── Abstract Base Class ───────────────────────────────────────────

class BaseGovernanceAdapter(ABC):
    """Abstract base class for platform governance adapters.

    Provides shared functionality:
    - Engine initialization and lifecycle
    - Correlation ID generation
    - Common translation helpers

    Subclasses implement platform-specific request/response translation.
    """

    _engine: Optional[TealEngineV13] = None

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Platform identifier."""
        ...

    async def initialize(self, engine: TealEngineV13) -> None:
        """Initialize the adapter with a TealEngine instance."""
        self._engine = engine

    @abstractmethod
    async def evaluate(self, platform_request: Any) -> PlatformDecision:
        """Evaluate a platform-specific request.

        Subclasses must implement this to translate platform requests.
        """
        ...

    async def _evaluate_via_engine(self, request: GovernanceRequest) -> DecisionV13:
        """Evaluate a GovernanceRequest via the engine.

        Used by subclasses after translating platform-specific requests.

        Raises:
            RuntimeError: If the adapter has not been initialized.
        """
        if self._engine is None:
            raise RuntimeError(
                f"{self.platform} adapter not initialized. "
                "Call initialize(engine) first."
            )
        return await self._engine.evaluate(request)

    def _to_platform_decision(self, decision: DecisionV13) -> PlatformDecision:
        """Convert a DecisionV13 to a PlatformDecision."""
        return PlatformDecision(
            allowed=decision.action == "ALLOW",
            reason_codes=decision.reason_codes,
            metadata={
                "risk_score": decision.risk_score,
                "policy_version": decision.policy_version,
                "automation_level": decision.automation_level,
                "control_id": decision.control_id,
                "owasp_category": decision.owasp_category,
            },
        )

    @staticmethod
    def _generate_correlation_id() -> str:
        """Generate a UUID v4 for correlation IDs."""
        return str(uuid.uuid4())
