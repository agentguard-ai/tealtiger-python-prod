"""TealTiger v1.3 — Platform Adapters (Python SDK).

Platform adapters translate between platform-specific contracts and
TealTiger's GovernanceRequest, using the same TealEngineV13 evaluation
logic internally.

Cross-platform guarantee: identical inputs → identical Decisions
regardless of which platform adapter is used.

Supported platforms:
- AWS Bedrock Agents (BedrockGuardrailAdapter)
- AWS AgentCore (AgentCorePlugin)
- Azure AI Agent Service (AzureAgentMiddleware)

Module: adapters
Requirements: 14.13, 14.14, 14.16
"""

from .base import GovernanceAdapter, BaseGovernanceAdapter, PlatformDecision, PlatformType
from .bedrock import BedrockGuardrailAdapter
from .agentcore import AgentCorePlugin
from .azure import AzureAgentMiddleware

__all__ = [
    # Base
    "GovernanceAdapter",
    "BaseGovernanceAdapter",
    "PlatformDecision",
    "PlatformType",
    # Adapters
    "BedrockGuardrailAdapter",
    "AgentCorePlugin",
    "AzureAgentMiddleware",
]
