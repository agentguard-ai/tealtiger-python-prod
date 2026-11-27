"""TealEngine - Core Policy Evaluation Engine for Python SDK.

TealTiger SDK v1.1.x - Enterprise Adoption Features
Phase 2: Decision Contract

This module implements the TealEngine with mode-specific behavior and Decision contract.
"""

import importlib.metadata
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..context.context_manager import ContextManager
from ..context.execution_context import ExecutionContext
from .policy_evaluator import (
    RULE_TYPE_SUPPORT,
    ClauseOutcome,
    UnsupportedPolicySectionError,
    evaluate_policies,
    unsupported_sections,
)
from .types import (
    CLAUSE_NONE,
    Decision,
    DecisionAction,
    ModeConfig,
    PolicyMode,
    ReasonCode,
)


def get_package_version() -> str:
    """Get the TealTiger package version.

    Returns:
        Package version string
    """
    try:
        return importlib.metadata.version("tealtiger")
    except importlib.metadata.PackageNotFoundError:
        return "1.1.0"  # Fallback version


def get_component_versions() -> Dict[str, str]:
    """Get component versions for Decision objects.

    Returns:
        Dict with component versions
    """
    version = get_package_version()
    return {
        "sdk": version,
        "engine": version,
    }


def resolve_policy_mode(
    policy_id: str,
    mode_config: ModeConfig,
    environment: Optional[str] = None,
) -> PolicyMode:
    """Resolve the effective policy mode using hierarchical resolution.

    Priority: policy-specific > environment-specific > global default

    Args:
        policy_id: Policy identifier
        mode_config: Mode configuration
        environment: Optional environment name

    Returns:
        Resolved PolicyMode
    """
    # Check policy-specific override (highest priority)
    if policy_id in mode_config.policy:
        return mode_config.policy[policy_id]

    # Check environment-specific override
    if environment and environment in mode_config.environment:
        return mode_config.environment[environment]

    # Fall back to global default
    return mode_config.default


def calculate_risk_score(allowed: bool, triggered_policies: List[str]) -> int:
    """Calculate risk score based on policy evaluation result.

    Args:
        allowed: Whether the request was allowed
        triggered_policies: List of triggered policy IDs

    Returns:
        Risk score (0-100)
    """
    if allowed:
        return 0  # No risk if allowed

    # Base risk score for violations
    risk_score = 50

    # Increase risk based on number of triggered policies
    triggered_count = len(triggered_policies)
    risk_score += min(triggered_count * 10, 40)

    # Check for high-risk policy violations
    high_risk_patterns = [
        "tools.file_delete",
        "tools.database_delete",
        "identity.forbidden",
        "codeExecution.blockedFunctions",
        "codeExecution.blockedPatterns",
    ]

    for policy in triggered_policies:
        if any(pattern in policy for pattern in high_risk_patterns):
            risk_score = min(risk_score + 20, 100)

    return min(max(risk_score, 0), 100)


# `determine_reason_codes` was removed here.
#
# It inferred reason codes by substring-matching clause paths and the human-readable
# reason text — `if "tools" in policy`, `if "blocked" in reason` — which produced
# `UNSAFE_CODE_DETECTED` for any clause containing "codeExecution" whether or not any
# code was inspected. That is the shape of defect the conformance specification exists
# to prevent, and §3.6 now makes the code order part of the contract anyway.
#
# The evaluator returns the codes directly, in the order TA-2 fixes, from the branch
# that actually decided. Nothing needs to guess.


def get_policy_id_from_context(context: Dict[str, Any]) -> str:
    """Extract policy ID from request context.

    Args:
        context: Request context dict

    Returns:
        Policy ID string
    """
    # Generate policy ID based on context
    if "tool" in context:
        return f"tools.{context['tool']}"
    elif "code" in context:
        return "codeExecution"
    elif "action" in context:
        return f"action.{context['action']}"
    else:
        return "general"


class TealEngine:
    """Policy evaluation. **Tool allowlist is enforced; nothing else is implemented.**

    What that means precisely, because the distinction is the whole point:

    - ``tools`` — **enforced.** Specified in conformance specification §6, implemented
      here, and verified 16/16 against the published conformance corpus.
    - every other rule type — **unspecified.** §7 of that specification defines none of
      them in v0.1, so none is implemented. A policy that configures one is **refused**
      with :class:`UnsupportedPolicySectionError` rather than partially honoured.

    The refusal is deliberate. Evaluating the sections this engine understands while
    ignoring the rest would return an ``ALLOW`` the policy did not earn, which is the
    defect fixed in 1.6.0 wearing a smaller disguise. §9.2 forbids presenting a rule type
    as enforced when its clause is a no-op, and the only way to keep that promise with a
    partial implementation is to decline the whole policy.

    :data:`~tealtiger.core.engine.policy_evaluator.RULE_TYPE_SUPPORT` is the
    machine-readable version of this claim, as §9.1 requires.

    History: until 1.6.0 this class returned ``ALLOW`` for every request without reading
    the policy at all, reporting ``POLICY_COMPLIANT`` with a risk score of 0. 1.6.0
    replaced that with a loud failure; this release replaces the failure with a real
    decision for the one rule type that is specified.

    Example:
        >>> from tealtiger.core.engine import TealEngine, ModeConfig, PolicyMode
        >>>
        >>> engine = TealEngine(
        ...     policies={"tools": {"search": {"allowed": True},
        ...                         "file_delete": {"allowed": False}}},
        ...     mode=ModeConfig(default=PolicyMode.ENFORCE),
        ... )
        >>> decision = engine.evaluate_with_mode(
        ...     {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"}
        ... )
        >>> decision.action.value
        'DENY'
        >>> [c.value for c in decision.reason_codes]
        ['POLICY_VIOLATION', 'TOOL_NOT_ALLOWED']
        >>> decision.triggering_clause
        'tools.file_delete.allowed'
        >>>
        >>> # Default-deny: a tool nobody configured is not an allowed tool (TA-4).
        >>> engine.evaluate_with_mode(
        ...     {"agentId": "a", "action": "tool.execute", "tool": "unknown"}
        ... ).triggering_clause
        'tools.unknown.absent'
        >>>
        >>> # A rule type this SDK does not implement is refused, not ignored.
        >>> partial = TealEngine(policies={"content": {"pii": "deny"}})
        >>> partial.evaluate_with_mode({"agentId": "a", "action": "chat.create"})
        Traceback (most recent call last):
        UnsupportedPolicySectionError: This policy configures rule types...
    """

    def __init__(
        self,
        policies: Dict[str, Any],
        mode: Optional[ModeConfig] = None,
        cache_ttl: Optional[int] = None,
        cache_enabled: bool = True,
        cache_max_size: int = 1000,
    ):
        """Initialize TealEngine.

        Args:
            policies: Policy configuration dict
            mode: Optional mode configuration (defaults to ENFORCE)
            cache_ttl: Optional cache TTL in milliseconds
            cache_enabled: Whether to enable caching
            cache_max_size: Maximum cache size
        """
        self.policies = policies
        self.mode_config = mode or ModeConfig(default=PolicyMode.ENFORCE)
        self.cache_ttl = cache_ttl
        self.cache_enabled = cache_enabled
        self.cache_max_size = cache_max_size
        self.component_versions = get_component_versions()

        # Validate mode configuration
        self._validate_mode_config()

    def _validate_mode_config(self) -> None:
        """Validate mode configuration.

        Raises:
            ValueError: If mode configuration is invalid
        """
        # Validate default mode
        if not isinstance(self.mode_config.default, PolicyMode):
            raise ValueError(f"Invalid default mode: {self.mode_config.default}")

        # Validate environment modes
        for env, mode in self.mode_config.environment.items():
            if not isinstance(mode, PolicyMode):
                raise ValueError(f"Invalid mode for environment '{env}': {mode}")

        # Validate policy modes
        for policy_id, mode in self.mode_config.policy.items():
            if not isinstance(mode, PolicyMode):
                raise ValueError(f"Invalid mode for policy '{policy_id}': {mode}")

    def evaluate_with_mode(
        self,
        context: Dict[str, Any],
        execution_context: Optional[ExecutionContext] = None,
    ) -> Decision:
        """Evaluate a request with mode-specific behavior and return a Decision object.

        Args:
            context: Request context dict with keys like agentId, action, tool, etc.
            execution_context: Optional ExecutionContext for tracing

        Returns:
            Decision object with action, reason_codes, risk_score, and metadata
        """
        start_time = time.time()

        # Ensure we have an execution context with correlation_id
        exec_context = execution_context or ContextManager.create_context()

        # Resolve the effective mode for this policy
        policy_id = get_policy_id_from_context(context)
        environment = exec_context.environment if exec_context else None

        effective_mode = resolve_policy_mode(
            policy_id=policy_id,
            mode_config=self.mode_config,
            environment=environment,
        )

        # REPORT_ONLY mode: Always allow without evaluating policies
        if effective_mode == PolicyMode.REPORT_ONLY:
            metadata: Dict[str, Any] = {
                "evaluation_time_ms": int((time.time() - start_time) * 1000),
                "cache_hit": False,
                "triggered_policies": [],
                "evaluation_performed": False,
            }

            # Add optional context fields
            if exec_context.tenant_id:
                metadata["tenant_id"] = exec_context.tenant_id
            if exec_context.application:
                metadata["application"] = exec_context.application
            if exec_context.environment:
                metadata["environment"] = exec_context.environment
            if exec_context.agent_purpose:
                metadata["agent_purpose"] = exec_context.agent_purpose

            decision = Decision(
                action=DecisionAction.ALLOW,
                reason_codes=[ReasonCode.REPORT_ONLY_MODE],
                risk_score=0,
                mode=PolicyMode.REPORT_ONLY,
                policy_id=policy_id,
                policy_version=self.component_versions["engine"],
                component_versions=self.component_versions,
                correlation_id=exec_context.correlation_id,
                reason="Request allowed in REPORT_ONLY mode (policy evaluation skipped)",
                # No clause decided, because no clause was consulted. §5.4 makes that
                # this mode's whole contract, so `none` is the honest value here
                # rather than a placeholder.
                triggering_clause=CLAUSE_NONE,
                metadata=metadata,
            )

            # Add optional fields
            if exec_context.trace_id:
                decision.trace_id = exec_context.trace_id
            if exec_context.workflow_id:
                decision.workflow_id = exec_context.workflow_id
            if exec_context.run_id:
                decision.run_id = exec_context.run_id
            if exec_context.span_id:
                decision.span_id = exec_context.span_id
            if exec_context.parent_span_id:
                decision.parent_span_id = exec_context.parent_span_id
            if context.get("metadata", {}).get("provider"):
                decision.provider = context["metadata"]["provider"]

            return decision

        # Evaluate the policy. Raises for any rule type this engine does not implement,
        # rather than evaluating the part it understands and implying the rest passed.
        outcome = self._evaluate_policies(context)

        # The clause that decided is the only triggered policy there is. A list is kept
        # because `metadata.triggered_policies` is part of the existing decision shape,
        # and because §5.2 permits short-circuiting — so one entry is the honest count,
        # not a simplification.
        triggered_policies = [] if outcome.allowed else [outcome.triggering_clause]

        # risk_score remains UNSPECIFIED (§3.4): there is no severity model behind it in
        # either SDK, the corpus deliberately asserts nothing about it, and decision D2
        # has not been taken. It is computed here only to keep the field populated, and
        # should not be routed on.
        risk_score = calculate_risk_score(outcome.allowed, triggered_policies)

        # Reason codes come from the evaluator, in the order the specification fixes
        # (TA-2: POLICY_VIOLATION first, then the specific code). §3.6 makes that order
        # part of the contract, so it is not re-derived here from a bag of strings.
        reason_codes = list(outcome.reason_codes)

        # MONITOR mode: Always allow but log violations
        if effective_mode == PolicyMode.MONITOR:
            metadata = {
                "evaluation_time_ms": int((time.time() - start_time) * 1000),
                "cache_hit": False,
                "triggered_policies": triggered_policies,
                "evaluation_performed": True,
            }

            # Add optional context fields
            if exec_context.tenant_id:
                metadata["tenant_id"] = exec_context.tenant_id
            if exec_context.application:
                metadata["application"] = exec_context.application
            if exec_context.environment:
                metadata["environment"] = exec_context.environment
            if exec_context.agent_purpose:
                metadata["agent_purpose"] = exec_context.agent_purpose

            # §5.4: MONITOR evaluates fully, then returns ALLOW while PRESERVING the
            # computed reason codes and triggering clause, so the would-be denial is
            # recorded rather than erased.
            #
            # An ALLOW carrying a clause looks contradictory and is exactly right here:
            # it says "nothing was blocked, and this is the clause that would have
            # blocked it". The §3.5 validator permits it deliberately — it only forbids
            # the reverse, a non-ALLOW that names nothing.
            decision = Decision(
                action=DecisionAction.ALLOW,
                reason_codes=(
                    [ReasonCode.POLICY_COMPLIANT]
                    if outcome.allowed
                    else [ReasonCode.MONITOR_MODE_VIOLATION] + reason_codes
                ),
                risk_score=risk_score,
                mode=PolicyMode.MONITOR,
                policy_id=policy_id,
                policy_version=self.component_versions["engine"],
                component_versions=self.component_versions,
                correlation_id=exec_context.correlation_id,
                reason=(
                    outcome.reason
                    if outcome.allowed
                    else f"Request allowed in MONITOR mode but would violate policy: {outcome.reason}"
                ),
                triggering_clause=outcome.triggering_clause,
                metadata=metadata,
            )

            # Add optional fields
            if exec_context.trace_id:
                decision.trace_id = exec_context.trace_id
            if exec_context.workflow_id:
                decision.workflow_id = exec_context.workflow_id
            if exec_context.run_id:
                decision.run_id = exec_context.run_id
            if exec_context.span_id:
                decision.span_id = exec_context.span_id
            if exec_context.parent_span_id:
                decision.parent_span_id = exec_context.parent_span_id
            if context.get("metadata", {}).get("provider"):
                decision.provider = context["metadata"]["provider"]

            return decision

        # ENFORCE mode: Block violations, allow compliant requests
        #
        # §5.4: return the computed decision unmodified. This is the only mode that does.
        if effective_mode == PolicyMode.ENFORCE:
            metadata = {
                "evaluation_time_ms": int((time.time() - start_time) * 1000),
                "cache_hit": False,
                "triggered_policies": triggered_policies,
                "evaluation_performed": True,
            }

            # Add optional context fields
            if exec_context.tenant_id:
                metadata["tenant_id"] = exec_context.tenant_id
            if exec_context.application:
                metadata["application"] = exec_context.application
            if exec_context.environment:
                metadata["environment"] = exec_context.environment
            if exec_context.agent_purpose:
                metadata["agent_purpose"] = exec_context.agent_purpose

            decision = Decision(
                action=DecisionAction.ALLOW if outcome.allowed else DecisionAction.DENY,
                reason_codes=reason_codes,
                risk_score=risk_score,
                mode=PolicyMode.ENFORCE,
                policy_id=policy_id,
                policy_version=self.component_versions["engine"],
                component_versions=self.component_versions,
                correlation_id=exec_context.correlation_id,
                reason=outcome.reason,
                triggering_clause=outcome.triggering_clause,
                metadata=metadata,
            )

            # Add optional fields
            if exec_context.trace_id:
                decision.trace_id = exec_context.trace_id
            if exec_context.workflow_id:
                decision.workflow_id = exec_context.workflow_id
            if exec_context.run_id:
                decision.run_id = exec_context.run_id
            if exec_context.span_id:
                decision.span_id = exec_context.span_id
            if exec_context.parent_span_id:
                decision.parent_span_id = exec_context.parent_span_id
            if context.get("metadata", {}).get("provider"):
                decision.provider = context["metadata"]["provider"]

            return decision

        # Fallback (should never reach here due to mode validation)
        raise ValueError(f"Invalid policy mode: {effective_mode}")

    def _evaluate_policies(self, context: Dict[str, Any]) -> ClauseOutcome:
        """Evaluate the policy, or refuse if it asks for a rule type we do not implement.

        **Tool allowlist is enforced.** Every other rule type is UNSPECIFIED in the
        conformance specification v0.1 (§7) and is not implemented here, so a policy
        that configures one is refused rather than partially honoured.

        That refusal is the load-bearing part. Until 1.6.0 this method returned
        ``{"allowed": True}`` unconditionally without reading ``self.policies``: a tool
        configured ``{"allowed": False}``, prompt injection, PII, ``os.system('rm -rf /')``
        and any cost above any limit were all permitted, while the decision reported
        ``POLICY_COMPLIANT`` and a risk score of 0. §9.2 names that failure directly — an
        implementation MUST NOT present a rule type as enforced when its clause is a no-op.

        Evaluating the sections we understand and ignoring the rest would be the same
        defect in a smaller box: a caller who configures content governance and receives
        ``ALLOW`` has been told their policy was applied. So the choice is deliberately
        binary. Either the whole policy is within what this engine implements, or no
        decision is offered for it.

        Raises:
            UnsupportedPolicySectionError: if the policy configures any rule type other
                than ``tools``. Subclasses :class:`NotImplementedError`, so callers that
                adapted to 1.6.0's behaviour keep working.

        Note:
            ``PolicyMode.REPORT_ONLY`` never reaches this method. That mode's contract is
            that evaluation is skipped, so it can be honoured honestly whatever the
            policy contains.
        """
        outcome, unsupported = evaluate_policies(context, self.policies)

        if unsupported:
            raise UnsupportedPolicySectionError(unsupported)

        return outcome

    @staticmethod
    def rule_type_support() -> Mapping[str, str]:
        """What this engine claims to enforce, per rule type. §9.1.

        ``enforced`` means specified, implemented and verified against the conformance
        corpus. ``unspecified`` means v0.1 of the specification defines no behaviour, so
        none is claimed and none is implemented.

        Exposed as an API rather than left in prose because a published support claim
        that only exists in a README is a claim nobody can check at runtime — and an
        unverifiable coverage claim is exactly what the 1.6.0 corrections were about.
        """
        return dict(RULE_TYPE_SUPPORT)

    def unenforceable_sections(self) -> Tuple[str, ...]:
        """Sections of *this engine's* policy that it cannot enforce.

        Empty means ``evaluate_with_mode`` can offer a decision under ENFORCE and
        MONITOR. Non-empty means it will raise, and these are the section names it will
        name. Available before any request, so a caller can find out at startup rather
        than on the first denial that matters.
        """
        return unsupported_sections(self.policies)

    def get_mode_config(self) -> ModeConfig:
        """Get the current mode configuration.

        Returns:
            Current ModeConfig
        """
        return self.mode_config
