"""TealTiger v1.3 — Azure AI Agent Service Middleware (Python SDK).

Integrates into the Azure AI Agent Service tool-call pipeline.
Supports deployment as Azure Functions-based middleware or as an
in-process SDK integration.

Module: adapters/azure
Requirements: 14.9, 14.10, 14.11, 14.12
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from .base import BaseGovernanceAdapter, PlatformDecision, PlatformType
from ..core.engine.v1_3 import DecisionV13, GovernanceRequest

__all__ = [
    "AzureToolCall",
    "AzureAgentContext",
    "AzureMiddlewareResult",
    "AzureAdapterConfig",
    "AzureAgentMiddleware",
]


# ── Azure-Specific Types ──────────────────────────────────────────

@dataclass
class AzureToolCall:
    """Azure tool call — represents a tool invocation in Azure AI Agent Service."""

    id: str
    """Unique tool call identifier."""

    function_name: str
    """Tool function name."""

    function_arguments: str
    """Tool function arguments (JSON string)."""

    type: str = "function"
    """Tool type (always 'function' for now)."""


@dataclass
class AzureAgentContext:
    """Azure agent context — metadata about the agent and session."""

    deployment_name: str = ""
    """Agent deployment name."""

    resource_group: Optional[str] = None
    """Azure resource group."""

    subscription_id: Optional[str] = None
    """Azure subscription ID."""

    thread_id: Optional[str] = None
    """Session/thread ID."""

    run_id: Optional[str] = None
    """Run ID."""

    user_identity: Optional[str] = None
    """User identity (from Azure AD)."""

    content: Optional[str] = None
    """Content being processed."""

    model: Optional[str] = None
    """Model being used."""


@dataclass
class AzureMiddlewareResult:
    """Azure middleware result — the response format for the tool-call pipeline."""

    allowed: bool = True
    """Whether the tool call is allowed."""

    action: Literal["allow", "deny", "modify"] = "allow"
    """Action: allow, deny, or modify."""

    reason: Optional[str] = None
    """Reason for the decision."""

    reason_codes: Optional[List[str]] = None
    """Reason codes from governance evaluation."""

    modified_arguments: Optional[str] = None
    """Modified arguments (when action is 'modify')."""

    risk_score: Optional[int] = None
    """Risk score (0-100)."""

    correlation_id: Optional[str] = None
    """Correlation ID for Application Insights."""

    telemetry: Optional[Dict[str, Any]] = None
    """Telemetry data for Azure Monitor."""


@dataclass
class AzureAdapterConfig:
    """Configuration for the Azure AI Agent Service middleware."""

    environment: str = "production"
    """Environment identifier."""

    enable_telemetry: bool = True
    """Whether to emit telemetry to Application Insights."""

    instrumentation_key: Optional[str] = None
    """Application Insights instrumentation key."""

    deployment_name: Optional[str] = None
    """Default deployment name."""


# ── Azure Agent Middleware ─────────────────────────────────────────

class AzureAgentMiddleware(BaseGovernanceAdapter):
    """AzureAgentMiddleware — Governance middleware for Azure AI Agent Service.

    Integrates into the tool-call pipeline and evaluates tool invocations
    and content generation through TealTiger's governance pipeline.

    Usage:
        ```python
        middleware = AzureAgentMiddleware()
        await middleware.initialize(engine)

        result = await middleware.evaluate_tool_call(tool_call, context)
        if not result.allowed:
            # Block the tool call
            pass
        ```
    """

    def __init__(self, config: Optional[AzureAdapterConfig] = None) -> None:
        self._adapter_config = config or AzureAdapterConfig()

    @property
    def platform(self) -> PlatformType:
        return "azure"

    async def evaluate(self, platform_request: Any) -> PlatformDecision:
        """Evaluate a platform-generic request (implements GovernanceAdapter)."""
        if isinstance(platform_request, dict):
            tool_call = platform_request.get("tool_call")
            context = platform_request.get("context")
            if isinstance(tool_call, dict):
                tool_call = AzureToolCall(**tool_call)
            if isinstance(context, dict):
                context = AzureAgentContext(**context)
        else:
            tool_call = getattr(platform_request, "tool_call", platform_request)
            context = getattr(platform_request, "context", None)

        result = await self.evaluate_tool_call(tool_call, context)
        return PlatformDecision(
            allowed=result.allowed,
            reason_codes=result.reason_codes or [],
            metadata=result.telemetry or {},
        )

    async def evaluate_tool_call(
        self,
        tool_call: AzureToolCall,
        context: Optional[AzureAgentContext] = None,
    ) -> AzureMiddlewareResult:
        """Evaluate a single tool call through the governance pipeline.

        This is the primary in-process integration point.
        """
        start_time = time.time()
        correlation_id = self._generate_correlation_id()

        # Translate to GovernanceRequest
        governance_request = self._translate_tool_call_to_governance_request(
            tool_call, context
        )

        # Evaluate via TealEngine
        decision = await self._evaluate_via_engine(governance_request)

        duration_ms = int((time.time() - start_time) * 1000)

        # Build telemetry data
        telemetry = self._build_telemetry(
            tool_call, decision, correlation_id, duration_ms
        )

        # Translate to Azure middleware result
        return self._translate_to_middleware_result(
            decision, correlation_id, telemetry
        )

    def _translate_tool_call_to_governance_request(
        self,
        tool_call: AzureToolCall,
        context: Optional[AzureAgentContext] = None,
    ) -> GovernanceRequest:
        """Translate a tool call into a GovernanceRequest."""
        try:
            parsed_arguments = json.loads(tool_call.function_arguments)
        except (json.JSONDecodeError, TypeError):
            parsed_arguments = {"raw": tool_call.function_arguments}

        model = ""
        if context:
            model = context.model or context.deployment_name or "azure-agent"
        else:
            model = "azure-agent"

        action_attributes: Dict[str, Any] = {
            "tool_call_id": tool_call.id,
            "tool_name": tool_call.function_name,
            "tool_arguments": parsed_arguments,
        }

        if context:
            action_attributes["deployment_name"] = context.deployment_name
            action_attributes["resource_group"] = context.resource_group
            action_attributes["subscription_id"] = context.subscription_id
            action_attributes["thread_id"] = context.thread_id
            action_attributes["run_id"] = context.run_id
            action_attributes["user_identity"] = context.user_identity

        return GovernanceRequest(
            correlation_id=self._generate_correlation_id(),
            content=tool_call.function_arguments,
            model=model,
            tool=tool_call.function_name,
            action_class="TOOL_INVOKE",
            action_attributes=action_attributes,
        )

    def _build_telemetry(
        self,
        tool_call: AzureToolCall,
        decision: DecisionV13,
        correlation_id: str,
        duration_ms: int,
    ) -> Dict[str, Any]:
        """Build telemetry data for Azure Monitor / Application Insights."""
        return {
            "custom_dimensions": {
                "tealtiger.decision.action": decision.action,
                "tealtiger.policy.version": decision.policy_version,
                "tealtiger.reason_codes": ",".join(decision.reason_codes),
                "tealtiger.correlation_id": correlation_id,
                "tealtiger.tool.name": tool_call.function_name,
            },
            "custom_metrics": {
                "tealtiger.risk_score": decision.risk_score,
                "tealtiger.duration_ms": duration_ms,
            },
            "operation_name": "TealTiger.Governance.EvaluateToolCall",
            "duration_ms": duration_ms,
        }

    def _translate_to_middleware_result(
        self,
        decision: DecisionV13,
        correlation_id: str,
        telemetry: Dict[str, Any],
    ) -> AzureMiddlewareResult:
        """Translate a TealTiger Decision into an Azure middleware result."""
        if decision.action == "ALLOW":
            action: Literal["allow", "deny", "modify"] = "allow"
        elif decision.action == "MODIFY":
            action = "modify"
        else:
            action = "deny"

        result = AzureMiddlewareResult(
            allowed=decision.action in ("ALLOW", "MODIFY"),
            action=action,
            correlation_id=correlation_id,
            reason_codes=decision.reason_codes if decision.reason_codes else None,
            risk_score=decision.risk_score,
        )

        if decision.reason_codes:
            result.reason = ", ".join(decision.reason_codes)

        if self._adapter_config.enable_telemetry:
            result.telemetry = telemetry

        return result
