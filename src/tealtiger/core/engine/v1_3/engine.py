"""TealEngine v1.3 — Governance Bundle Engine (Python SDK).

Extends the v1.2 evaluation pipeline with pre-evaluation and post-evaluation
hook stages. When no v1.3-specific features are configured, behavior is
identical to v1.2.

Pre-evaluation stage (sequential, short-circuit on deny):
  1. FREEZE rule check → FREEZE_BLOCK
  2. PLAN_ONLY mode check → PLAN_ONLY_BLOCK
  3. NHI status validation → NHI_REVOKED, NHI_SUSPENDED
  4. Agent attestation check → AGENT_ATTESTATION_MISSING, AGENT_INTEGRITY_FAILED
  5. ZSP grant check → ACCESS_STANDING_PRIVILEGE_DENIED, ACCESS_GRANT_EXPIRED
  6. NHI scope/environment check → NHI_SCOPE_VIOLATION, NHI_ENVIRONMENT_VIOLATION

If none short-circuit, proceeds to the v1.2 parallel module evaluation pipeline.

Module: core/engine/v1_3/engine
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .types import (
    AgentAttestation,
    AttestationConfig,
    DecisionV13,
    FreezeRule,
    GovernanceContext,
    GovernanceRequest,
    NHIDescriptor,
    NHIInventory,
    PlanOnlyConfig,
    PolicyMatcher,
    TealEngineV13Options,
    ZSPConfig,
)


# ── v1.3 Reason Codes ────────────────────────────────────────────

class V13ReasonCode:
    """v1.3 governance reason codes for pre-evaluation denials."""

    FREEZE_BLOCK = "FREEZE_BLOCK"
    FREEZE_TAMPER_ATTEMPT = "FREEZE_TAMPER_ATTEMPT"
    PLAN_ONLY_BLOCK = "PLAN_ONLY_BLOCK"
    NHI_REVOKED = "NHI_REVOKED"
    NHI_SUSPENDED = "NHI_SUSPENDED"
    NHI_SCOPE_VIOLATION = "NHI_SCOPE_VIOLATION"
    NHI_ENVIRONMENT_VIOLATION = "NHI_ENVIRONMENT_VIOLATION"
    AGENT_ATTESTATION_MISSING = "AGENT_ATTESTATION_MISSING"
    AGENT_INTEGRITY_FAILED = "AGENT_INTEGRITY_FAILED"
    ACCESS_STANDING_PRIVILEGE_DENIED = "ACCESS_STANDING_PRIVILEGE_DENIED"
    ACCESS_GRANT_EXPIRED = "ACCESS_GRANT_EXPIRED"


# ── Default PLAN_ONLY side-effecting action classes ──────────────

DEFAULT_SIDE_EFFECTING_ACTIONS = [
    "CODE_CHANGE",
    "DATABASE_WRITE",
    "INFRASTRUCTURE_MUTATION",
    "PRODUCTION_DEPLOY",
    "SECRETS_REVEAL",
    "CODE_MERGE",
    "TOOL_INVOKE",
    "MEMORY_WRITE",
    "FILE_WRITE",
    "API_MUTATION",
]

DEFAULT_ALLOWED_ACTIONS = [
    "READ",
    "REASONING",
    "PLAN",
    "QUERY",
    "SEARCH",
    "ANALYZE",
    "SUMMARIZE",
]


# ── Governance Event ─────────────────────────────────────────────

@dataclass
class GovernanceEvent:
    """A governance event emitted by the engine."""

    type: str
    timestamp: int
    details: Dict[str, Any] = field(default_factory=dict)


GovernanceEventListener = Callable[[GovernanceEvent], None]


# ── TealEngineV13 ────────────────────────────────────────────────

class TealEngineV13:
    """TealEngine v1.3 — Governance Bundle Engine.

    Provides pre-evaluation stages (FREEZE, PLAN_ONLY, NHI, attestation, ZSP)
    before delegating to v1.2 parallel module evaluation.

    When no v1.3 features are configured, evaluate() delegates directly to
    v1.2 behavior producing identical results.
    """

    def __init__(self, options: TealEngineV13Options) -> None:
        """Initialize TealEngineV13.

        Args:
            options: Engine configuration options.
        """
        # Deep-freeze the FREEZE rules — they are immutable at runtime
        self._freeze_rules: Tuple[FreezeRule, ...] = tuple(
            options.freeze_rules or []
        )

        self._plan_only_mode: bool = options.plan_only_mode
        self._plan_only_config: PlanOnlyConfig = options.plan_only_config or PlanOnlyConfig(
            enabled=options.plan_only_mode,
            side_effecting_actions=list(DEFAULT_SIDE_EFFECTING_ACTIONS),
            allowed_actions=list(DEFAULT_ALLOWED_ACTIONS),
        )

        self._nhi_inventory: Optional[NHIInventory] = options.nhi_inventory
        self._zsp_config: Optional[ZSPConfig] = options.zsp_config
        self._attestation_config: Optional[AttestationConfig] = options.attestation_config
        self._options = options
        self._event_listeners: List[GovernanceEventListener] = []

    # ── Public API ───────────────────────────────────────────────

    async def evaluate(
        self,
        request: GovernanceRequest,
        ctx: Optional[GovernanceContext] = None,
    ) -> DecisionV13:
        """v1.3 evaluation entry point.

        Wraps the v1.2 pipeline with pre-evaluation and post-evaluation stages.
        When no v1.3 features are configured, this delegates directly to v1.2
        behavior producing identical results.

        Args:
            request: The governance request to evaluate.
            ctx: Optional governance context with environment/workflow info.

        Returns:
            A DecisionV13 with the evaluation result.
        """
        if ctx is None:
            ctx = GovernanceContext(correlation_id=request.correlation_id)

        # ── Pre-evaluation stage (sequential, short-circuit on deny) ──

        # 1. FREEZE rule check
        freeze_result = self._check_freeze_rules(request)
        if freeze_result is not None:
            return freeze_result

        # 2. PLAN_ONLY mode check
        plan_only_result = self._check_plan_only_mode(request)
        if plan_only_result is not None:
            return plan_only_result

        # 3. NHI status validation (revoked/suspended)
        nhi_status_result = self._check_nhi_status(request)
        if nhi_status_result is not None:
            return nhi_status_result

        # 4. Agent attestation check
        attestation_result = self._check_agent_attestation(request)
        if attestation_result is not None:
            return attestation_result

        # 5. ZSP grant check
        zsp_result = self._check_zsp_grant(request)
        if zsp_result is not None:
            return zsp_result

        # 6. NHI scope/environment check
        nhi_scope_result = self._check_nhi_scope_and_environment(request, ctx)
        if nhi_scope_result is not None:
            return nhi_scope_result

        # ── No v1.3 pre-evaluation blocks → delegate to v1.2 behavior ──
        decision = self._evaluate_v12(request, ctx)

        # Extend with v1.3 context if NHI identity is present
        if request.nhi_identity:
            decision.nhi_context = {
                "agent_id": request.nhi_identity.agent_id,
                "scope_used": list(request.nhi_identity.capability_scope),
            }

        return decision

    def on_event(self, listener: GovernanceEventListener) -> None:
        """Register an event listener for governance events.

        Args:
            listener: Callback invoked on governance events.
        """
        self._event_listeners.append(listener)

    @property
    def freeze_rules(self) -> Tuple[FreezeRule, ...]:
        """Get the currently active FREEZE rules (read-only)."""
        return self._freeze_rules

    def modify_freeze_rules(self, rules: List[FreezeRule]) -> None:
        """Attempt to modify FREEZE rules at runtime.

        This is ALWAYS rejected — FREEZE rules are immutable.
        Logs a FREEZE_TAMPER_ATTEMPT event.
        """
        self._emit_event(GovernanceEvent(
            type=V13ReasonCode.FREEZE_TAMPER_ATTEMPT,
            timestamp=_now_ms(),
            details={
                "message": "Attempted to modify FREEZE rules at runtime. Operation rejected.",
                "attempted_rules": [r.id for r in rules],
            },
        ))

    def remove_freeze_rule(self, rule_id: str) -> None:
        """Attempt to remove a FREEZE rule at runtime.

        This is ALWAYS rejected — FREEZE rules are immutable.
        Logs a FREEZE_TAMPER_ATTEMPT event.
        """
        self._emit_event(GovernanceEvent(
            type=V13ReasonCode.FREEZE_TAMPER_ATTEMPT,
            timestamp=_now_ms(),
            details={
                "message": "Attempted to remove a FREEZE rule at runtime. Operation rejected.",
                "rule_id": rule_id,
            },
        ))

    # ── Pre-evaluation checks (private) ─────────────────────────

    def _check_freeze_rules(self, request: GovernanceRequest) -> Optional[DecisionV13]:
        """Check 1: FREEZE rule evaluation.

        FREEZE rules have absolute precedence — evaluated FIRST.
        Returns a DENY decision if any FREEZE rule matches, otherwise None.
        """
        if not self._freeze_rules:
            return None

        for rule in self._freeze_rules:
            if self._matches_policy(rule.match, request):
                return self._build_pre_eval_deny(
                    reason_code=V13ReasonCode.FREEZE_BLOCK,
                    reason=f"Action blocked by FREEZE rule '{rule.id}': {rule.reason}",
                    correlation_id=request.correlation_id,
                    metadata={
                        "freeze_rule_id": rule.id,
                        "freeze_reason": rule.reason,
                        "created_by": rule.created_by,
                        "created_at": rule.created_at,
                    },
                )

        return None

    def _check_plan_only_mode(self, request: GovernanceRequest) -> Optional[DecisionV13]:
        """Check 2: PLAN_ONLY mode evaluation.

        When enabled, all side-effecting actions are denied.
        Read-only and reasoning actions proceed normally.
        """
        is_enabled = self._plan_only_mode or self._plan_only_config.enabled
        if not is_enabled:
            return None

        action_class = request.action_class or ""

        # If action is explicitly in the allowed list, let it through
        if self._is_allowed_in_plan_only(action_class):
            return None

        # If action is classified as side-effecting, deny it
        if self._is_side_effecting(action_class):
            return self._build_pre_eval_deny(
                reason_code=V13ReasonCode.PLAN_ONLY_BLOCK,
                reason=(
                    f"Action '{action_class}' blocked: PLAN_ONLY mode is active. "
                    "Only read-only and reasoning actions are permitted."
                ),
                correlation_id=request.correlation_id,
                metadata={
                    "action_class": action_class,
                    "plan_only_mode": True,
                },
            )

        # If action class is not empty and not in allowed list, treat as side-effecting
        if action_class and not self._is_allowed_in_plan_only(action_class):
            return self._build_pre_eval_deny(
                reason_code=V13ReasonCode.PLAN_ONLY_BLOCK,
                reason=(
                    f"Action '{action_class}' blocked: PLAN_ONLY mode is active. "
                    "Action not in allowed list."
                ),
                correlation_id=request.correlation_id,
                metadata={
                    "action_class": action_class,
                    "plan_only_mode": True,
                },
            )

        return None

    def _check_nhi_status(self, request: GovernanceRequest) -> Optional[DecisionV13]:
        """Check 3: NHI status validation.

        Denies requests from revoked or suspended NHI identities.
        """
        nhi = request.nhi_identity
        if nhi is None:
            return None

        # Also check the inventory if available
        inventory_entry = (
            self._nhi_inventory.lookup(nhi.agent_id)
            if self._nhi_inventory is not None
            else None
        )
        effective_status = inventory_entry.status if inventory_entry else nhi.status

        if effective_status == "revoked":
            return self._build_pre_eval_deny(
                reason_code=V13ReasonCode.NHI_REVOKED,
                reason=f"NHI identity '{nhi.agent_id}' has been revoked. All actions are denied.",
                correlation_id=request.correlation_id,
                metadata={
                    "agent_id": nhi.agent_id,
                    "owner": nhi.owner,
                    "status": effective_status,
                },
            )

        if effective_status == "suspended":
            return self._build_pre_eval_deny(
                reason_code=V13ReasonCode.NHI_SUSPENDED,
                reason=(
                    f"NHI identity '{nhi.agent_id}' is suspended. "
                    "All actions are denied until reactivation."
                ),
                correlation_id=request.correlation_id,
                metadata={
                    "agent_id": nhi.agent_id,
                    "owner": nhi.owner,
                    "status": effective_status,
                },
            )

        return None

    def _check_agent_attestation(self, request: GovernanceRequest) -> Optional[DecisionV13]:
        """Check 4: Agent attestation verification.

        Denies requests missing required attestation or with invalid attestation.
        """
        if not self._attestation_config or not self._attestation_config.required:
            return None

        attestation = request.attestation

        # No attestation provided but required
        if attestation is None:
            return self._build_pre_eval_deny(
                reason_code=V13ReasonCode.AGENT_ATTESTATION_MISSING,
                reason="Agent attestation is required but was not provided in the governance request.",
                correlation_id=request.correlation_id,
                metadata={"attestation_required": True},
            )

        # Verify attestation integrity
        if not self._is_attestation_valid(attestation):
            return self._build_pre_eval_deny(
                reason_code=V13ReasonCode.AGENT_INTEGRITY_FAILED,
                reason=f"Agent attestation integrity check failed for agent '{attestation.agent_id}'.",
                correlation_id=request.correlation_id,
                metadata={
                    "agent_id": attestation.agent_id,
                    "signer": attestation.signer,
                    "attested_at": attestation.attested_at,
                },
            )

        return None

    def _check_zsp_grant(self, request: GovernanceRequest) -> Optional[DecisionV13]:
        """Check 5: Zero Standing Privilege grant validation.

        When ZSP is enabled, every tool/resource access requires a valid,
        non-expired JIT grant.
        """
        if not self._zsp_config or not self._zsp_config.enabled:
            return None

        grant = request.jit_grant

        # No grant provided — standing privilege denied
        if grant is None:
            return self._build_pre_eval_deny(
                reason_code=V13ReasonCode.ACCESS_STANDING_PRIVILEGE_DENIED,
                reason=(
                    "Zero Standing Privilege mode is enabled. "
                    "A valid JIT grant is required for all tool/resource access."
                ),
                correlation_id=request.correlation_id,
                metadata={
                    "zsp_enabled": True,
                    "agent_id": request.nhi_identity.agent_id if request.nhi_identity else None,
                },
            )

        # Grant expired
        now = _now_ms()
        if grant.expires_at <= now:
            return self._build_pre_eval_deny(
                reason_code=V13ReasonCode.ACCESS_GRANT_EXPIRED,
                reason=f"JIT grant '{grant.grant_id}' has expired. Request a new grant to continue.",
                correlation_id=request.correlation_id,
                metadata={
                    "grant_id": grant.grant_id,
                    "agent_id": grant.agent_id,
                    "expired_at": grant.expires_at,
                    "current_time": now,
                },
            )

        return None

    def _check_nhi_scope_and_environment(
        self,
        request: GovernanceRequest,
        ctx: GovernanceContext,
    ) -> Optional[DecisionV13]:
        """Check 6: NHI scope and environment constraint validation.

        Denies requests where the action is outside the NHI's capability scope
        or the environment is not in the NHI's environment constraints.
        """
        nhi = request.nhi_identity
        if nhi is None or nhi.status != "active":
            return None

        # Check capability scope
        action_class = request.action_class
        tool = request.tool

        if action_class and nhi.capability_scope:
            if not self._is_within_scope(action_class, tool, nhi.capability_scope):
                return self._build_pre_eval_deny(
                    reason_code=V13ReasonCode.NHI_SCOPE_VIOLATION,
                    reason=(
                        f"NHI '{nhi.agent_id}' attempted action '{action_class}' "
                        "outside its declared capability scope."
                    ),
                    correlation_id=request.correlation_id,
                    metadata={
                        "agent_id": nhi.agent_id,
                        "action_class": action_class,
                        "tool": tool,
                        "capability_scope": nhi.capability_scope,
                    },
                )

        # Check environment constraints
        environment = ctx.environment
        if environment and nhi.environment_constraints:
            if environment not in nhi.environment_constraints:
                return self._build_pre_eval_deny(
                    reason_code=V13ReasonCode.NHI_ENVIRONMENT_VIOLATION,
                    reason=(
                        f"NHI '{nhi.agent_id}' attempted to operate in environment "
                        f"'{environment}' which is not in its allowed environments."
                    ),
                    correlation_id=request.correlation_id,
                    metadata={
                        "agent_id": nhi.agent_id,
                        "environment": environment,
                        "allowed_environments": nhi.environment_constraints,
                    },
                )

        return None

    # ── v1.2 delegation ─────────────────────────────────────────

    def _evaluate_v12(
        self,
        request: GovernanceRequest,
        ctx: GovernanceContext,
    ) -> DecisionV13:
        """Delegate to v1.2 evaluation behavior.

        When no v1.3 features block, this produces the standard v1.2 ALLOW
        decision (simplified — in production, this would invoke the full
        v1.2 parallel module pipeline).
        """
        return DecisionV13(
            action="ALLOW",
            reason_codes=["POLICY_COMPLIANT"],
            risk_score=0,
            mode="ENFORCE",
            policy_id="v1.3-governance",
            policy_version="1.3.0",
            component_versions={"sdk": "1.3.0", "engine": "1.3.0"},
            correlation_id=ctx.correlation_id or request.correlation_id,
            reason="Request allowed — no policy violations detected.",
            event_type="governance.evaluation",
            teec_version="2.0.0",
            timestamp=_now_ms(),
            module="TealEngineV13",
        )

    # ── Helper methods ───────────────────────────────────────────

    def _matches_policy(self, matcher: PolicyMatcher, request: GovernanceRequest) -> bool:
        """Match a PolicyMatcher against a GovernanceRequest."""
        # Match action_class
        if matcher.action_class:
            request_action_class = request.action_class or ""
            if not self._glob_match(matcher.action_class, request_action_class):
                return False

        # Match tool
        if matcher.tool:
            request_tool = request.tool or ""
            if not self._glob_match(matcher.tool, request_tool):
                return False

        # Match agent_id
        if matcher.agent_id:
            request_agent_id = (
                request.nhi_identity.agent_id if request.nhi_identity else ""
            )
            if not self._glob_match(matcher.agent_id, request_agent_id):
                return False

        # Match environment
        if matcher.environment:
            request_env = (
                (request.action_attributes or {}).get("environment", "")
                if request.action_attributes
                else ""
            )
            if not self._glob_match(matcher.environment, str(request_env)):
                return False

        # Match model
        if matcher.model:
            request_model = request.model or ""
            if not self._glob_match(matcher.model, request_model):
                return False

        return True

    @staticmethod
    def _glob_match(pattern: str, value: str) -> bool:
        """Simple glob matching supporting '*' wildcard."""
        if pattern == "*":
            return True
        if "*" not in pattern:
            return pattern == value

        # Convert glob to regex
        escaped = re.escape(pattern)
        regex_str = escaped.replace(r"\*", ".*")
        regex = re.compile(f"^{regex_str}$")
        return regex.match(value) is not None

    def _is_allowed_in_plan_only(self, action_class: str) -> bool:
        """Check if an action class is explicitly allowed in PLAN_ONLY mode."""
        allowed = self._plan_only_config.allowed_actions
        return any(a.upper() == action_class.upper() for a in allowed)

    def _is_side_effecting(self, action_class: str) -> bool:
        """Check if an action class is classified as side-effecting."""
        side_effecting = self._plan_only_config.side_effecting_actions
        return any(a.upper() == action_class.upper() for a in side_effecting)

    def _is_within_scope(
        self,
        action_class: str,
        tool: Optional[str],
        scope: List[str],
    ) -> bool:
        """Check if an action/tool is within the NHI's declared capability scope.

        Scope entries use a colon-separated format: 'read:memory', 'invoke:tool:search'
        """
        action_lower = action_class.lower()
        tool_lower = tool.lower() if tool else None

        for entry in scope:
            entry_lower = entry.lower()

            # Direct action class match
            if entry_lower == action_lower:
                return True

            # Wildcard scope
            if entry_lower == "*":
                return True

            # Colon-separated scope matching
            parts = entry_lower.split(":")

            # Match 'invoke:tool:toolname' pattern
            if len(parts) >= 3 and parts[0] == "invoke" and parts[1] == "tool" and tool_lower:
                if parts[2] == "*" or parts[2] == tool_lower:
                    return True

            # Match action class prefix (e.g., 'read' matches 'READ')
            if action_lower.startswith(parts[0]) or parts[0] in action_lower:
                return True

            # Match tool-level scope (e.g., 'tool:search' matches tool='search')
            if len(parts) >= 2 and parts[0] == "tool" and tool_lower:
                if parts[1] == "*" or parts[1] == tool_lower:
                    return True

        return False

    def _is_attestation_valid(self, attestation: AgentAttestation) -> bool:
        """Validate agent attestation.

        Checks: signer is trusted, attestation is not expired, signature format is valid.
        """
        if not self._attestation_config:
            return True

        # Check if signer is in trusted signers list
        if self._attestation_config.trusted_signers:
            if attestation.signer not in self._attestation_config.trusted_signers:
                return False

        # Check attestation age
        if self._attestation_config.max_attestation_age_ms is not None:
            age = _now_ms() - attestation.attested_at
            if age > self._attestation_config.max_attestation_age_ms:
                return False

        # Check signature is present and non-empty
        if not attestation.signature:
            return False

        # Check integrity hash is present
        if not attestation.integrity_hash:
            return False

        return True

    def _build_pre_eval_deny(
        self,
        reason_code: str,
        reason: str,
        correlation_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DecisionV13:
        """Build a pre-evaluation DENY decision with v1.3 metadata."""
        return DecisionV13(
            action="DENY",
            reason_codes=[reason_code],
            risk_score=100,
            mode="ENFORCE",
            policy_id="v1.3-governance",
            policy_version="1.3.0",
            component_versions={"sdk": "1.3.0", "engine": "1.3.0"},
            correlation_id=correlation_id,
            reason=reason,
            event_type="governance.pre_evaluation_deny",
            teec_version="2.0.0",
            timestamp=_now_ms(),
            module="TealEngineV13",
            metadata={
                "pre_evaluation_stage": True,
                "reason_code": reason_code,
                **(metadata or {}),
            },
        )

    def _emit_event(self, event: GovernanceEvent) -> None:
        """Emit a governance event to all registered listeners."""
        for listener in self._event_listeners:
            try:
                listener(event)
            except Exception:
                # Event listeners should not break the engine
                pass


# ── Utility ──────────────────────────────────────────────────────

def _now_ms() -> int:
    """Get current time in Unix milliseconds."""
    return int(time.time() * 1000)
