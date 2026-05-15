"""TealEngine v1.3 — Core Types (Python SDK).

Extends the v1.2 type surface with governance bundle types: automation levels,
NHI governance, FREEZE rules, PLAN_ONLY mode, Zero Standing Privilege,
agent attestation, policy bundles, and governance provider interfaces.

All v1.2 types are preserved; nothing is removed or renamed.
When no v1.3-specific features are configured, behavior is identical to v1.2.

Module: core/engine/v1_3/types
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Protocol, runtime_checkable

# Re-export v1.2 types for convenience
from ..types import Decision, DecisionAction, PolicyMode, ReasonCode

__all__ = [
    # Re-exports
    "Decision",
    "DecisionAction",
    "PolicyMode",
    "ReasonCode",
    # Automation Levels
    "AutomationLevel",
    "PolicyMatcher",
    "AutomationLevelRule",
    "AutomationLevelConfig",
    "PendingDecision",
    # NHI Governance
    "NHIDescriptor",
    "NHIInventory",
    # FREEZE Rules and PLAN_ONLY Mode
    "FreezeRule",
    "PlanOnlyConfig",
    # Secure Change Governance
    "CodeChangeAttributes",
    "CodeChangePolicy",
    # Zero Standing Privilege
    "ZSPConfig",
    "JITGrant",
    # Agent Attestation
    "AttestationConfig",
    "AgentAttestation",
    # Governance Request and Context
    "GovernanceRequest",
    "GovernanceContext",
    # v1.3 Decision
    "DecisionV13",
    "CostEvidence",
    "GovernanceReceipt",
    # Policy Bundle
    "PolicyBundle",
    "GovernanceCostLimits",
    "PolicyRule",
    # Governance Provider Interface
    "GovernanceProvider",
    "EvaluationContext",
    "CapabilityManifest",
    # Engine Options
    "TealEngineV13Options",
]


# ── Automation Levels (Requirement 1) ────────────────────────────

AutomationLevel = Literal[
    "auto_deny",
    "auto_sanitize",
    "auto_allow",
    "approval_required",
]
"""Automation level metadata field on policy rules.

Determines the degree of autonomy for an action category.
"""


@dataclass
class PolicyMatcher:
    """Policy matcher for rule conditions.

    Matches against action class, tool name, agent identity, etc.
    """

    action_class: Optional[str] = None
    """Action class to match (e.g., 'CODE_CHANGE', 'TOOL_INVOKE')."""

    tool: Optional[str] = None
    """Tool name pattern (glob or exact)."""

    agent_id: Optional[str] = None
    """Agent ID pattern."""

    environment: Optional[str] = None
    """Environment pattern."""

    model: Optional[str] = None
    """Model pattern."""

    risk_score_above: Optional[float] = None
    """Risk score threshold (match if risk_score >= threshold)."""

    attributes: Optional[Dict[str, Any]] = None
    """Custom attribute matchers."""


@dataclass
class AutomationLevelRule:
    """Rule mapping a policy matcher to an automation level."""

    match: PolicyMatcher
    """Condition to match against the governance request."""

    automation_level: AutomationLevel
    """Automation level to apply when matched."""


@dataclass
class AutomationLevelConfig:
    """Configuration for automation level rules."""

    rules: List[AutomationLevelRule] = field(default_factory=list)
    """Ordered list of automation level rules (first match wins)."""

    default_level: Optional[AutomationLevel] = None
    """Default automation level when no rule matches."""


@dataclass
class PendingDecision:
    """Decision extension for approval_required automation level.

    Returned when an action requires external approval before proceeding.
    """

    action: Literal["PENDING"] = "PENDING"
    """PENDING action — blocks execution until external approval."""

    requires_approval: Literal[True] = True
    """Indicates this decision requires external approval."""

    approval_token: str = ""
    """Opaque token used to approve or reject the pending action."""

    expires_at: int = 0
    """Unix ms timestamp after which the approval expires."""

    reason_codes: List[str] = field(default_factory=list)
    """Reason codes for the pending decision."""

    risk_score: int = 0
    """Risk score (0-100)."""

    correlation_id: str = ""
    """Correlation ID for tracing."""

    reason: str = ""
    """Human-readable reason."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional metadata."""


# ── NHI Governance (Requirement 2) ───────────────────────────────

@dataclass
class NHIDescriptor:
    """Non-Human Identity descriptor.

    Represents an AI agent or automated system as a principal with
    identity, ownership, scope, and revocation lifecycle.
    """

    agent_id: str
    """Unique agent identifier."""

    owner: str
    """Owner of the agent (team, user, or org)."""

    created_at: int
    """Unix ms timestamp of agent creation."""

    capability_scope: List[str] = field(default_factory=list)
    """Scoped capabilities (e.g., ['read:memory', 'invoke:tool:search'])."""

    environment_constraints: List[str] = field(default_factory=list)
    """Environments the agent may operate in (e.g., ['production', 'staging'])."""

    status: Literal["active", "suspended", "revoked"] = "active"
    """Current lifecycle status."""


@runtime_checkable
class NHIInventory(Protocol):
    """NHI Inventory — registry of all agent identities."""

    def lookup(self, agent_id: str) -> Optional[NHIDescriptor]:
        """Look up an agent by ID."""
        ...

    def update_status(
        self, agent_id: str, status: Literal["active", "suspended", "revoked"]
    ) -> None:
        """Update the status of an agent."""
        ...


# ── FREEZE Rules and PLAN_ONLY Mode (Requirement 4) ─────────────

@dataclass
class FreezeRule:
    """Immutable governance control that blocks specified actions.

    Cannot be modified at runtime regardless of agent output or policy evaluation.
    """

    id: str
    """Unique identifier for this FREEZE rule."""

    match: PolicyMatcher
    """Condition to match (action class, tool name, etc.)."""

    reason: str
    """Human-readable reason for the freeze."""

    created_at: int
    """Unix ms timestamp of rule creation."""

    created_by: str
    """Identity that created the rule."""

    immutable: Literal[True] = True
    """FREEZE rules are always immutable at runtime."""


@dataclass
class PlanOnlyConfig:
    """Configuration for PLAN_ONLY mode.

    When enabled, all side-effecting actions are denied.
    """

    enabled: bool = False
    """Whether PLAN_ONLY mode is active."""

    side_effecting_actions: List[str] = field(default_factory=list)
    """Action classes treated as side-effecting (denied in PLAN_ONLY)."""

    allowed_actions: List[str] = field(default_factory=list)
    """Action classes treated as read-only/reasoning (allowed in PLAN_ONLY)."""


# ── Secure Change Governance (Requirement 3) ─────────────────────

@dataclass
class CodeChangeAttributes:
    """Attributes for a CODE_CHANGE action."""

    target_paths: List[str] = field(default_factory=list)
    """Target file paths being changed."""

    target_branch: str = ""
    """Target branch for the change."""

    change_type: Literal["create", "modify", "delete"] = "modify"
    """Type of change."""

    diff_hash: str = ""
    """SHA-256 hash of the diff content."""


@dataclass
class CodeChangePolicy:
    """Policy configuration for CODE_CHANGE governance."""

    path_allowlist: List[str] = field(default_factory=list)
    """Glob patterns for allowed file paths."""

    branch_allowlist: List[str] = field(default_factory=list)
    """Allowed target branches."""

    two_person_rule: bool = False
    """Whether two-person approval is required."""

    require_diff_hash: bool = False
    """Whether a diff hash must be provided."""


# ── Zero Standing Privilege (Requirement 19) ─────────────────────

@dataclass
class ZSPConfig:
    """Configuration for Zero Standing Privilege mode.

    When enabled, every tool/resource access requires a valid JIT grant.
    """

    enabled: bool = False
    """Whether ZSP is enabled."""

    max_grant_ttl_ms: int = 3_600_000
    """Maximum duration for a JIT grant in milliseconds (default: 1 hour)."""


@dataclass
class JITGrant:
    """Just-In-Time grant for temporary access."""

    grant_id: str
    """Unique grant identifier."""

    agent_id: str
    """Agent receiving the grant."""

    scope: List[str] = field(default_factory=list)
    """Tools/resources granted (e.g., ['tool:database', 'resource:secrets'])."""

    issued_at: int = 0
    """Unix ms timestamp when grant was issued."""

    expires_at: int = 0
    """Unix ms timestamp when grant expires."""

    issued_by: str = ""
    """Identity that issued the grant."""


# ── Agent Attestation ────────────────────────────────────────────

@dataclass
class AttestationConfig:
    """Configuration for agent attestation verification."""

    required: bool = False
    """Whether attestation is required."""

    trusted_signers: List[str] = field(default_factory=list)
    """Trusted signers (public keys or key IDs)."""

    max_attestation_age_ms: Optional[int] = None
    """Maximum age of attestation in milliseconds."""


@dataclass
class AgentAttestation:
    """Agent attestation payload submitted with governance requests."""

    agent_id: str
    """Agent identifier."""

    signature: str
    """Attestation signature (Ed25519 or similar)."""

    signer: str
    """Signer identity (public key or key ID)."""

    attested_at: int
    """Unix ms timestamp of attestation."""

    integrity_hash: str
    """SHA-256 hash of agent code/config for integrity verification."""


# ── Governance Request and Context ───────────────────────────────

@dataclass
class GovernanceRequest:
    """v1.3 Governance request.

    Extends the evaluation request with action classification,
    NHI identity, attestation, and JIT grants.
    """

    correlation_id: str = ""
    """Correlation ID for request tracing."""

    action_class: Optional[str] = None
    """Action class (e.g., 'CODE_CHANGE', 'TOOL_INVOKE', 'MEMORY_WRITE')."""

    action_attributes: Optional[Dict[str, Any]] = None
    """Action-specific attributes."""

    nhi_identity: Optional[NHIDescriptor] = None
    """NHI identity of the requesting agent."""

    attestation: Optional[AgentAttestation] = None
    """Agent attestation for integrity verification."""

    jit_grant: Optional[JITGrant] = None
    """JIT grant for ZSP access."""

    tool: Optional[str] = None
    """Tool being invoked."""

    model: Optional[str] = None
    """Model being used."""

    content: Optional[str] = None
    """Content being evaluated."""

    metadata: Optional[Dict[str, Any]] = None
    """Additional request metadata."""


@dataclass
class GovernanceContext:
    """v1.3 Governance context.

    Extends the module context with automation level, NHI identity,
    environment, and workflow tracking.
    """

    correlation_id: str = ""
    """Correlation ID for request tracing."""

    automation_level: Optional[AutomationLevel] = None
    """Resolved automation level for this evaluation."""

    nhi_identity: Optional[NHIDescriptor] = None
    """NHI identity from the request."""

    environment: Optional[str] = None
    """Current environment (e.g., 'production', 'staging', 'development')."""

    workflow_id: Optional[str] = None
    """Workflow ID if triggered by TealFlow."""


# ── v1.3 Decision (extends v1.2 Decision) ────────────────────────

@dataclass
class CostEvidence:
    """Cost evidence attached to a decision."""

    estimated_cost: float = 0.0
    """Estimated cost for this request."""

    budget_limit: float = 0.0
    """Budget limit that applies."""

    remaining_budget: float = 0.0
    """Remaining budget after this request."""

    reasoning_tokens: Optional[int] = None
    """Reasoning tokens used (if applicable)."""


@dataclass
class GovernanceReceipt:
    """Governance receipt — cryptographic proof of a policy decision."""

    leaf_index: int = 0
    """Position in the Merkle tree."""

    decision_hash: str = ""
    """SHA-256 hash of decision + context + timestamp + policy_version + prev_hash."""

    previous_hash: str = ""
    """Hash of the previous decision in the chain."""

    timestamp: int = 0
    """Unix ms timestamp of the decision."""

    policy_version: str = ""
    """Policy version used for evaluation."""

    correlation_id: str = ""
    """Correlation ID linking to the originating request."""

    merkle_proof: List[str] = field(default_factory=list)
    """Sibling hashes for Merkle proof verification."""


@dataclass
class DecisionV13:
    """v1.3 Decision — extends v1.2 Decision with governance bundle fields.

    All new fields are optional; absence preserves v1.2 behavior.
    """

    # Core decision fields (from v1.2)
    action: str = "ALLOW"
    """Decision action (ALLOW, DENY, MODIFY, PENDING)."""

    reason_codes: List[str] = field(default_factory=list)
    """Reason codes explaining the decision."""

    risk_score: int = 0
    """Risk score (0-100)."""

    mode: str = "ENFORCE"
    """Policy mode that produced this decision."""

    policy_id: str = ""
    """ID of the policy that made the decision."""

    policy_version: str = ""
    """Version of the policy."""

    component_versions: Dict[str, str] = field(default_factory=dict)
    """Versions of TealTiger components."""

    correlation_id: str = ""
    """Correlation ID for tracing."""

    reason: str = ""
    """Human-readable reason for the decision."""

    event_type: str = ""
    """Event type for audit/logging."""

    teec_version: str = "2.0.0"
    """TEEC schema version."""

    timestamp: int = 0
    """Unix ms timestamp of the decision."""

    module: str = ""
    """Module that produced the decision."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional metadata about the decision."""

    # v1.3 extensions
    automation_level: Optional[AutomationLevel] = None
    """Automation level that produced this decision."""

    pending: Optional[Dict[str, Any]] = None
    """Pending approval details (when automation_level = 'approval_required')."""

    proof_receipt: Optional[GovernanceReceipt] = None
    """Cryptographic governance receipt."""

    cost_evidence: Optional[CostEvidence] = None
    """Cost evidence for this decision."""

    nhi_context: Optional[Dict[str, Any]] = None
    """NHI context used in evaluation."""

    control_id: Optional[str] = None
    """Control ID in DIM.CATEGORY.SUBCATEGORY.CONTROL format."""

    owasp_category: Optional[str] = None
    """OWASP category identifier (e.g., 'LLM06')."""


# ── Policy Bundle ────────────────────────────────────────────────

@dataclass
class GovernanceCostLimits:
    """Governance-owned cost limits (from bundle, overrides app config)."""

    per_request_max: float = 0.0
    per_session_max: float = 0.0
    per_daily_max: float = 0.0
    per_agent_max: float = 0.0
    reasoning_token_budget: Optional[int] = None


@dataclass
class PolicyRule:
    """A single policy rule within a bundle.

    Control IDs follow the format: DIM.CATEGORY.SUBCATEGORY.CONTROL
    """

    id: str
    """Unique rule identifier."""

    control_id: str
    """Control ID in hierarchical format."""

    match: PolicyMatcher
    """Condition to match against the governance request."""

    action: str
    """Action to take when matched (e.g., 'DENY', 'ALLOW', 'MODIFY')."""

    automation_level: Optional[AutomationLevel] = None
    """Automation level for this rule."""

    metadata: Optional[Dict[str, Any]] = None
    """Additional rule metadata."""


@dataclass
class PolicyBundle:
    """A complete policy bundle that can be loaded and hot-swapped at runtime."""

    bundle_version: str
    """Bundle version (semver)."""

    requires_sdk: str
    """Required SDK version (semver range, e.g., '^1.3.0')."""

    requires_teec: str
    """Required TEEC version (semver range, e.g., '^2.0.0')."""

    required_capabilities: List[str] = field(default_factory=list)
    """Capabilities required by this bundle."""

    hash: str = ""
    """SHA-256 hash of bundle contents for integrity verification."""

    signature: Optional[str] = None
    """Optional Ed25519 signature for bundle authentication."""

    policies: List[PolicyRule] = field(default_factory=list)
    """Policy rules in this bundle."""

    cost_limits: Optional[GovernanceCostLimits] = None
    """Governance-owned cost limits."""

    freeze_rules: Optional[List[FreezeRule]] = None
    """FREEZE rules (persist across hot-swaps)."""

    fail_behavior: Literal["fail_closed", "fail_open"] = "fail_closed"
    """Behavior when a module fails during evaluation."""


# ── Governance Provider Interface (Requirement 20) ───────────────

@dataclass
class EvaluationContext:
    """Evaluation context for the GovernanceProvider interface.

    Published as open JSON Schema, versioned independently.
    """

    correlation_id: str = ""
    """Correlation ID for request tracing."""

    agent_id: Optional[str] = None
    """Agent identifier."""

    action: str = ""
    """Action being evaluated."""

    action_attributes: Dict[str, Any] = field(default_factory=dict)
    """Action-specific attributes."""

    content: Optional[str] = None
    """Content being evaluated."""

    model: Optional[str] = None
    """Model being used."""

    tool: Optional[str] = None
    """Tool being invoked."""

    environment: Optional[str] = None
    """Current environment."""

    nhi_identity: Optional[NHIDescriptor] = None
    """NHI identity of the requesting agent."""


@dataclass
class CapabilityManifest:
    """Capability manifest describing what a governance provider supports."""

    sdk_version: str = "1.3.0"
    """SDK version."""

    supported_modules: List[str] = field(default_factory=list)
    """List of supported module names."""

    supported_features: List[str] = field(default_factory=list)
    """List of supported feature identifiers."""

    teec_version: str = "2.0.0"
    """TEEC schema version."""


@runtime_checkable
class GovernanceProvider(Protocol):
    """Portable governance provider interface.

    Allows alternative implementations to provide governance decisions
    using the same evaluation context and policy bundle format.
    """

    async def evaluate(self, context: EvaluationContext) -> DecisionV13:
        """Evaluate a governance request and return a decision."""
        ...

    async def load_policies(self, bundle: PolicyBundle) -> None:
        """Load a policy bundle into the provider."""
        ...

    def get_capabilities(self) -> CapabilityManifest:
        """Get the provider's capability manifest."""
        ...


# ── TealEngine v1.3 Options ──────────────────────────────────────

@dataclass
class TealEngineV13Options:
    """TealEngine v1.3 options.

    All new fields are optional; defaults preserve v1.2 behavior.
    """

    # v1.2 base options
    policies: Optional[Dict[str, Any]] = None
    """Policy configuration dict."""

    mode: str = "ENFORCE"
    """Default policy mode."""

    # v1.3 additions (all optional, defaults preserve v1.2 behavior)
    freeze_rules: Optional[List[FreezeRule]] = None
    """Immutable FREEZE rules (evaluated first, cannot be removed)."""

    plan_only_mode: bool = False
    """Enable PLAN_ONLY mode (blocks all side-effecting actions)."""

    plan_only_config: Optional[PlanOnlyConfig] = None
    """PLAN_ONLY configuration with action classification."""

    nhi_inventory: Optional[NHIInventory] = None
    """NHI inventory for agent identity governance."""

    automation_levels: Optional[AutomationLevelConfig] = None
    """Automation level configuration."""

    zsp_config: Optional[ZSPConfig] = None
    """Zero Standing Privilege configuration."""

    attestation_config: Optional[AttestationConfig] = None
    """Agent attestation configuration."""

    code_change_policy: Optional[CodeChangePolicy] = None
    """Code change governance policy."""

    policy_packs: Optional[List[str]] = None
    """Policy packs to load (e.g., ['owasp-agentic-top10'])."""
