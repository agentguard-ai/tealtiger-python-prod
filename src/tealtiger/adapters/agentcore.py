"""TealTiger v1.3 — AWS AgentCore Governance Plugin (Python SDK).

Hooks into the AgentCore pre-action and post-action lifecycle stages.
Evaluates tool calls, memory writes, and inter-agent messages through
TealTiger's governance pipeline. Propagates TealTiger correlation IDs
into AgentCore's observability traces.

Module: adapters/agentcore
Requirements: 14.5, 14.6, 14.7, 14.8
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from .base import BaseGovernanceAdapter, PlatformDecision, PlatformType
from ..core.engine.v1_3 import DecisionV13, GovernanceRequest

__all__ = [
    "AgentCoreActionType",
    "AgentCoreAction",
    "AgentCoreDecision",
    "AgentCorePostActionRecord",
    "AgentCoreAdapterConfig",
    "AgentCorePlugin",
]


# ── AgentCore-Specific Types ─────────────────────────────────────

AgentCoreActionType = Literal[
    "tool_call",
    "memory_write",
    "memory_read",
    "inter_agent_message",
    "response_generation",
    "planning",
]


@dataclass
class AgentCoreAction:
    """AgentCore action — represents an action in the agent lifecycle."""

    action_id: str
    """Unique action identifier."""

    type: AgentCoreActionType
    """Type of action."""

    agent_id: str
    """Agent performing the action."""

    tool_name: Optional[str] = None
    """Tool name (for tool_call type)."""

    tool_input: Optional[Dict[str, Any]] = None
    """Tool input parameters."""

    content: Optional[str] = None
    """Content being processed."""

    target_agent_id: Optional[str] = None
    """Target agent (for inter_agent_message)."""

    memory_scope: Optional[str] = None
    """Memory scope (for memory operations)."""

    session_id: Optional[str] = None
    """Session ID."""

    trace_context: Optional[Dict[str, str]] = None
    """Trace context for observability (traceId, spanId, parentSpanId)."""

    metadata: Optional[Dict[str, Any]] = None
    """Additional metadata."""


@dataclass
class AgentCoreDecision:
    """AgentCore decision — the response format expected by AgentCore runtime."""

    allowed: bool = True
    """Whether the action is allowed."""

    action: Literal["proceed", "block", "modify"] = "proceed"
    """Action to take: proceed, block, or modify."""

    reason: Optional[str] = None
    """Reason for the decision."""

    reason_codes: Optional[List[str]] = None
    """Reason codes from governance evaluation."""

    modified_content: Optional[str] = None
    """Modified content (when action is 'modify')."""

    risk_score: Optional[int] = None
    """Risk score (0-100)."""

    correlation_id: Optional[str] = None
    """TealTiger correlation ID for trace propagation."""

    metadata: Optional[Dict[str, Any]] = None
    """Additional metadata."""


@dataclass
class AgentCorePostActionRecord:
    """Post-action audit record."""

    action: AgentCoreAction
    """Action that was executed."""

    result: Any = None
    """Result of the action."""

    correlation_id: str = ""
    """TealTiger correlation ID."""

    timestamp: int = 0
    """Unix ms timestamp."""


@dataclass
class AgentCoreAdapterConfig:
    """Configuration for the AgentCore governance plugin."""

    environment: str = "production"
    """Environment identifier."""

    enable_post_action_audit: bool = True
    """Whether to evaluate post-action results."""

    evaluate_action_types: List[AgentCoreActionType] = field(
        default_factory=lambda: [
            "tool_call",
            "memory_write",
            "inter_agent_message",
            "response_generation",
        ]
    )
    """Action types to evaluate (default: all except memory_read and planning)."""


# ── AgentCore Governance Plugin ───────────────────────────────────

class AgentCorePlugin(BaseGovernanceAdapter):
    """AgentCorePlugin — Governance plugin for AWS AgentCore.

    Hooks into the agent lifecycle at pre-action and post-action stages.
    Evaluates tool calls, memory writes, and inter-agent messages through
    TealTiger's governance pipeline.

    Usage:
        ```python
        plugin = AgentCorePlugin()
        await plugin.initialize(engine)

        # Pre-action hook
        decision = await plugin.pre_action(action)
        if not decision.allowed:
            # Block the action
            pass

        # Post-action hook (audit)
        await plugin.post_action(action, result)
        ```
    """

    def __init__(self, config: Optional[AgentCoreAdapterConfig] = None) -> None:
        self._adapter_config = config or AgentCoreAdapterConfig()
        self._post_action_records: List[AgentCorePostActionRecord] = []

    @property
    def platform(self) -> PlatformType:
        return "agentcore"

    async def evaluate(self, platform_request: Any) -> PlatformDecision:
        """Evaluate a platform-generic request (implements GovernanceAdapter)."""
        if isinstance(platform_request, AgentCoreAction):
            action = platform_request
        elif isinstance(platform_request, dict):
            action = AgentCoreAction(**platform_request)
        else:
            action = platform_request

        decision = await self.pre_action(action)
        return PlatformDecision(
            allowed=decision.allowed,
            reason_codes=decision.reason_codes or [],
            metadata=decision.metadata or {},
        )

    async def pre_action(self, action: AgentCoreAction) -> AgentCoreDecision:
        """Pre-action governance hook.

        Called before an agent action is executed. Evaluates the action
        through TealTiger's governance pipeline and returns a decision.
        """
        # Skip evaluation for action types not in the configured list
        if action.type not in self._adapter_config.evaluate_action_types:
            return AgentCoreDecision(
                allowed=True,
                action="proceed",
                correlation_id=self._generate_correlation_id(),
            )

        # Translate AgentCore action → GovernanceRequest
        governance_request = self._translate_to_governance_request(action)

        # Evaluate via TealEngine
        decision = await self._evaluate_via_engine(governance_request)

        # Generate correlation ID for trace propagation
        correlation_id = self._generate_correlation_id()

        # Translate Decision → AgentCore decision
        return self._translate_to_agentcore_decision(decision, correlation_id)

    async def post_action(self, action: AgentCoreAction, result: Any) -> None:
        """Post-action audit hook.

        Called after an agent action completes. Records the action result
        for audit purposes and propagates correlation IDs.
        """
        if not self._adapter_config.enable_post_action_audit:
            return

        record = AgentCorePostActionRecord(
            action=action,
            result=result,
            correlation_id=self._generate_correlation_id(),
            timestamp=int(time.time() * 1000),
        )
        self._post_action_records.append(record)

    def get_post_action_records(self) -> List[AgentCorePostActionRecord]:
        """Get post-action audit records (for testing/debugging)."""
        return list(self._post_action_records)

    def clear_post_action_records(self) -> None:
        """Clear post-action audit records."""
        self._post_action_records.clear()

    def _translate_to_governance_request(
        self, action: AgentCoreAction
    ) -> GovernanceRequest:
        """Translate an AgentCore action into a TealTiger GovernanceRequest."""
        action_class = self._resolve_action_class(action)

        action_attributes: Dict[str, Any] = {
            "action_id": action.action_id,
            "action_type": action.type,
            "agent_id": action.agent_id,
            "session_id": action.session_id,
        }

        tool: Optional[str] = None

        # Add tool-specific attributes
        if action.type == "tool_call" and action.tool_name:
            tool = action.tool_name
            action_attributes["tool_name"] = action.tool_name
            action_attributes["tool_input"] = action.tool_input

        # Add inter-agent message attributes
        if action.type == "inter_agent_message" and action.target_agent_id:
            action_attributes["target_agent_id"] = action.target_agent_id

        # Add memory operation attributes
        if action.type in ("memory_write", "memory_read") and action.memory_scope:
            action_attributes["memory_scope"] = action.memory_scope

        # Propagate trace context
        if action.trace_context:
            action_attributes["trace_id"] = action.trace_context.get("traceId", "")
            action_attributes["span_id"] = action.trace_context.get("spanId", "")
            action_attributes["parent_span_id"] = action.trace_context.get(
                "parentSpanId", ""
            )

        return GovernanceRequest(
            correlation_id=self._generate_correlation_id(),
            content=action.content or "",
            model=action.agent_id,
            tool=tool,
            action_class=action_class,
            action_attributes=action_attributes,
        )

    def _resolve_action_class(self, action: AgentCoreAction) -> str:
        """Resolve the action class from an AgentCore action type."""
        mapping: Dict[str, str] = {
            "tool_call": "TOOL_INVOKE",
            "memory_write": "MEMORY_WRITE",
            "memory_read": "READ",
            "inter_agent_message": "TOOL_INVOKE",
            "response_generation": "REASONING",
            "planning": "PLAN",
        }
        return mapping.get(action.type, "TOOL_INVOKE")

    def _translate_to_agentcore_decision(
        self, decision: DecisionV13, correlation_id: str
    ) -> AgentCoreDecision:
        """Translate a TealTiger Decision into an AgentCore decision."""
        if decision.action == "ALLOW":
            action: Literal["proceed", "block", "modify"] = "proceed"
        elif decision.action == "MODIFY":
            action = "modify"
        else:
            action = "block"

        result = AgentCoreDecision(
            allowed=decision.action in ("ALLOW", "MODIFY"),
            action=action,
            correlation_id=correlation_id,
            reason_codes=decision.reason_codes if decision.reason_codes else None,
            risk_score=decision.risk_score,
            metadata={
                "policy_version": decision.policy_version,
                "evaluated_by": "tealtiger",
            },
        )

        if decision.reason_codes:
            result.reason = ", ".join(decision.reason_codes)

        return result
