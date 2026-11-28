"""Dry-run a policy against requests, using the engine that will enforce it.

**The whole design constraint is in that last clause.** A dry run is only worth having if
it predicts what will actually happen, which means it must use the same evaluator that
will produce the real decisions — not a second one written to resemble it.

That is not a hypothetical concern. The TypeScript SDK publishes a `PolicySimulator` built
on a `PolicyTester` with its own `evaluateCondition`, operating on a policy type its own
engine never sees. It offers "dry-run a policy against scenarios before enforcing" while
predicting from an evaluator that will not be the one deciding: not a stub that allows
everything, but a second opinion presented as a preview. This module exists instead of a
port of that one.

So :func:`simulate_policy` constructs a real :class:`~tealtiger.core.engine.TealEngine`
and calls the same ``evaluate_with_mode`` a caller would, and the report says so in
``evaluated_by``. If the simulation and production ever disagree, it is a bug in one
engine rather than a difference between two.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from .policy_validation import PolicyValidationResult, validate_policy
from .teal_engine import TealEngine
from .types import ModeConfig, PolicyMode


@dataclass(frozen=True)
class SimulatedDecision:
    """What the engine decided for one request, and which clause decided it."""

    request: Mapping[str, Any]
    action: str
    reason_codes: Tuple[str, ...]
    triggering_clause: str
    reason: str

    @property
    def allowed(self) -> bool:
        return self.action == "ALLOW"


@dataclass(frozen=True)
class SimulationReport:
    """The outcome of a dry run, with the evidence needed to trust it."""

    evaluated_by: str
    """Which engine produced these decisions, and its version.

    Present so a reader can tell that the preview came from the production evaluator
    rather than a lookalike. A simulation report that does not say what evaluated it
    cannot be distinguished from a guess.
    """

    mode: str
    decisions: Tuple[SimulatedDecision, ...]
    validation: PolicyValidationResult
    by_clause: Mapping[str, int] = field(default_factory=dict)
    """How many decisions each clause produced.

    The useful summary when tuning a policy: it answers "which rule is doing the work",
    and exposes a clause that fires for everything or for nothing.
    """

    @property
    def allowed(self) -> int:
        return sum(1 for d in self.decisions if d.allowed)

    @property
    def denied(self) -> int:
        return sum(1 for d in self.decisions if not d.allowed)


def simulate_policy(
    policies: Optional[Mapping[str, Any]],
    requests: Iterable[Mapping[str, Any]],
    mode: PolicyMode = PolicyMode.ENFORCE,
) -> SimulationReport:
    """Evaluate ``requests`` against ``policies`` without enforcing anything.

    Args:
        policies: The policy document, in the shape ``TealEngine`` evaluates.
        requests: Request contexts, each with at least ``agentId`` and ``action``.
        mode: The mode to simulate. ``ENFORCE`` shows the decisions that would be
            returned; ``MONITOR`` shows what a monitor-mode rollout would record.

    Raises:
        ValueError: if the policy is not well formed, or configures a rule type this
            SDK cannot enforce.

    **Why it raises instead of returning an empty report.** A simulation that could not
    run must not be mistakable for one that ran and found nothing to deny. Returning zero
    decisions would be exactly that, and "no denials" is the single most dangerous thing
    this package can say incorrectly. Call :func:`validate_policy` first if you want the
    findings without the exception.
    """
    validation = validate_policy(policies)

    if not validation:
        detail = "; ".join(
            f"[{f.code}] {f.path or '<document>'}: {f.message}" for f in validation.errors
        )
        raise ValueError(
            "Cannot simulate this policy, so no decisions are reported — an empty "
            "simulation would read as 'nothing would be denied', which is not what "
            f"happened. Problems: {detail}"
        )

    engine = TealEngine(policies=dict(policies or {}), mode=ModeConfig(default=mode))

    decisions = []
    clause_counts: Counter = Counter()

    for request in requests:
        decision = engine.evaluate_with_mode(dict(request))
        clause_counts[decision.triggering_clause] += 1
        decisions.append(
            SimulatedDecision(
                request=dict(request),
                action=decision.action.value,
                reason_codes=tuple(code.value for code in decision.reason_codes),
                triggering_clause=decision.triggering_clause,
                reason=decision.reason,
            )
        )

    versions: Dict[str, str] = engine.component_versions

    return SimulationReport(
        evaluated_by=f"TealEngine {versions.get('engine', 'unknown')}",
        mode=mode.value,
        decisions=tuple(decisions),
        validation=validation,
        by_clause=dict(clause_counts),
    )
