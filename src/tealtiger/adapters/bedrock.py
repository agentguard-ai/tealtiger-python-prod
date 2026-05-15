"""TealTiger v1.3 — AWS Bedrock Agents Guardrail Adapter (Python SDK).

Conforms to the Bedrock Guardrails API contract. Translates Bedrock
guardrail events into TealTiger GovernanceRequests and returns
ALLOW/DENY in the format expected by the Bedrock Agents runtime.

Module: adapters/bedrock
Requirements: 14.1, 14.2, 14.3, 14.4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from .base import BaseGovernanceAdapter, PlatformDecision, PlatformType
from ..core.engine.v1_3 import DecisionV13, GovernanceRequest

__all__ = [
    "BedrockGuardrailEvent",
    "BedrockGuardrailResponse",
    "BedrockAdapterConfig",
    "BedrockGuardrailAdapter",
]


# ── Bedrock-Specific Types ────────────────────────────────────────

BedrockGuardrailEventType = Literal[
    "PRE_PROCESSING",
    "ORCHESTRATION",
    "KNOWLEDGE_BASE_RESPONSE_GENERATION",
    "POST_PROCESSING",
]


@dataclass
class BedrockGuardrailEvent:
    """Bedrock guardrail event — the input from Bedrock Agents runtime."""

    message_version: str = "1.0"
    """Event message version."""

    source: BedrockGuardrailEventType = "ORCHESTRATION"
    """Source of the event in the Bedrock lifecycle."""

    input_text: Optional[str] = None
    """Input text to evaluate."""

    output_text: Optional[str] = None
    """Output text to evaluate (for post-processing)."""

    agent: Optional[Dict[str, str]] = None
    """Agent information (name, id, alias, version)."""

    action_group: Optional[Dict[str, Any]] = None
    """Action group information (for tool invocations)."""

    knowledge_base: Optional[Dict[str, str]] = None
    """Knowledge base information."""

    session_attributes: Optional[Dict[str, str]] = None
    """Session attributes."""


@dataclass
class BedrockGuardrailResponse:
    """Bedrock guardrail response — the output expected by Bedrock Agents runtime."""

    action: Literal["ALLOW", "DENY"] = "ALLOW"
    """Action to take."""

    message: Optional[str] = None
    """Message to return when denied."""

    reason_codes: Optional[List[str]] = None
    """Reason codes for the decision."""

    risk_score: Optional[int] = None
    """Risk score (0-100)."""

    metadata: Optional[Dict[str, Any]] = None
    """Additional metadata."""


@dataclass
class BedrockAdapterConfig:
    """Configuration for the Bedrock guardrail adapter."""

    default_action_class: str = "TOOL_INVOKE"
    """Default action class for Bedrock events."""

    environment: str = "production"
    """Environment identifier."""

    agent_id: Optional[str] = None
    """Agent ID to use for NHI identity."""


# ── Bedrock Guardrail Adapter ─────────────────────────────────────

class BedrockGuardrailAdapter(BaseGovernanceAdapter):
    """BedrockGuardrailAdapter — Translates Bedrock Guardrails API events
    into TealTiger governance evaluations.

    Usage:
        ```python
        adapter = BedrockGuardrailAdapter()
        await adapter.initialize(engine)

        # In Lambda handler:
        response = await adapter.evaluate_guardrail(event)
        return response
        ```
    """

    def __init__(self, config: Optional[BedrockAdapterConfig] = None) -> None:
        self._adapter_config = config or BedrockAdapterConfig()

    @property
    def platform(self) -> PlatformType:
        return "bedrock"

    async def evaluate(self, platform_request: Any) -> PlatformDecision:
        """Evaluate a platform-generic request (implements GovernanceAdapter)."""
        if isinstance(platform_request, BedrockGuardrailEvent):
            event = platform_request
        elif isinstance(platform_request, dict):
            event = BedrockGuardrailEvent(**platform_request)
        else:
            event = platform_request

        response = await self.evaluate_guardrail(event)
        return PlatformDecision(
            allowed=response.action == "ALLOW",
            reason_codes=response.reason_codes or [],
            metadata=response.metadata or {},
        )

    async def evaluate_guardrail(
        self, event: BedrockGuardrailEvent
    ) -> BedrockGuardrailResponse:
        """Evaluate a Bedrock guardrail event through TealTiger's governance pipeline.

        Translates the Bedrock event into a GovernanceRequest, evaluates it,
        and returns the result in Bedrock's expected response format.
        """
        governance_request = self._translate_to_governance_request(event)
        decision = await self._evaluate_via_engine(governance_request)
        return self._translate_to_bedrock_response(decision)

    def _translate_to_governance_request(
        self, event: BedrockGuardrailEvent
    ) -> GovernanceRequest:
        """Translate a Bedrock guardrail event into a TealTiger GovernanceRequest."""
        action_class = self._resolve_action_class(event)
        content = event.input_text or event.output_text or ""

        action_attributes: Dict[str, Any] = {
            "source": event.source,
            "message_version": event.message_version,
        }

        tool: Optional[str] = None

        # Add action group details if present (tool invocation)
        if event.action_group:
            action_attributes["tool"] = event.action_group.get("name", "")
            action_attributes["api_path"] = event.action_group.get("apiPath", "")
            action_attributes["http_method"] = event.action_group.get("httpMethod", "")
            action_attributes["parameters"] = event.action_group.get("parameters")
            tool = event.action_group.get("name")

        # Add knowledge base details if present
        if event.knowledge_base:
            action_attributes["knowledge_base_id"] = event.knowledge_base.get("id", "")
            action_attributes["query"] = event.knowledge_base.get("query", "")

        # Add agent identity
        if event.agent:
            action_attributes["agent_id"] = event.agent.get("id", "")
            action_attributes["agent_name"] = event.agent.get("name", "")
            action_attributes["agent_version"] = event.agent.get("version", "")

        model = (event.agent or {}).get("name", "bedrock-agent")

        return GovernanceRequest(
            correlation_id=self._generate_correlation_id(),
            content=content,
            model=model,
            tool=tool,
            action_class=action_class,
            action_attributes=action_attributes,
        )

    def _resolve_action_class(self, event: BedrockGuardrailEvent) -> str:
        """Resolve the action class from a Bedrock event."""
        if event.source == "ORCHESTRATION":
            return "TOOL_INVOKE" if event.action_group else "REASONING"
        elif event.source == "KNOWLEDGE_BASE_RESPONSE_GENERATION":
            return "READ"
        elif event.source in ("PRE_PROCESSING", "POST_PROCESSING"):
            return "REASONING"
        return self._adapter_config.default_action_class

    def _translate_to_bedrock_response(
        self, decision: DecisionV13
    ) -> BedrockGuardrailResponse:
        """Translate a TealTiger Decision into a Bedrock guardrail response."""
        action: Literal["ALLOW", "DENY"] = (
            "ALLOW" if decision.action == "ALLOW" else "DENY"
        )

        response = BedrockGuardrailResponse(
            action=action,
            reason_codes=decision.reason_codes if decision.reason_codes else None,
            risk_score=decision.risk_score,
            metadata={
                "policy_version": decision.policy_version,
                "evaluated_by": "tealtiger",
            },
        )

        if action == "DENY":
            codes = ", ".join(decision.reason_codes) if decision.reason_codes else ""
            response.message = f"Action denied by TealTiger governance: {codes}"

        return response
