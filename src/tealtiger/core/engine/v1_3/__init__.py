"""TealEngine v1.3 — Governance Bundle Engine (Python SDK).

This package provides the v1.3 governance engine with pre-evaluation stages,
FREEZE rules, PLAN_ONLY mode, NHI governance, Zero Standing Privilege,
agent attestation, and policy bundles.

When no v1.3-specific features are configured, behavior is identical to v1.2.
"""

from .engine import TealEngineV13, V13ReasonCode
from .policy_hotswap import (
    SDK_CAPABILITIES,
    BundleValidationResult,
    HotSwapEventType,
    LoadPolicyResult,
    PolicyHotSwapManager,
)
from .types import (
    AgentAttestation,
    AttestationConfig,
    AutomationLevel,
    AutomationLevelConfig,
    AutomationLevelRule,
    CapabilityManifest,
    CodeChangeAttributes,
    CodeChangePolicy,
    CostEvidence,
    DecisionV13,
    EvaluationContext,
    FreezeRule,
    GovernanceContext,
    GovernanceCostLimits,
    GovernanceProvider,
    GovernanceReceipt,
    GovernanceRequest,
    JITGrant,
    NHIDescriptor,
    NHIInventory,
    PendingDecision,
    PlanOnlyConfig,
    PolicyBundle,
    PolicyMatcher,
    PolicyRule,
    TealEngineV13Options,
    ZSPConfig,
)

__all__ = [
    # Types
    "AutomationLevel",
    "PolicyMatcher",
    "AutomationLevelRule",
    "AutomationLevelConfig",
    "PendingDecision",
    "NHIDescriptor",
    "NHIInventory",
    "FreezeRule",
    "PlanOnlyConfig",
    "CodeChangeAttributes",
    "CodeChangePolicy",
    "ZSPConfig",
    "JITGrant",
    "AttestationConfig",
    "AgentAttestation",
    "GovernanceRequest",
    "GovernanceContext",
    "DecisionV13",
    "CostEvidence",
    "GovernanceReceipt",
    "PolicyBundle",
    "GovernanceCostLimits",
    "PolicyRule",
    "GovernanceProvider",
    "EvaluationContext",
    "CapabilityManifest",
    "TealEngineV13Options",
    # Engine
    "TealEngineV13",
    "V13ReasonCode",
    # Policy bundle hot-swap
    "PolicyHotSwapManager",
    "BundleValidationResult",
    "LoadPolicyResult",
    "HotSwapEventType",
    "SDK_CAPABILITIES",
]
