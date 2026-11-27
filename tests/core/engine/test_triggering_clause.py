"""Tests for `Decision.triggering_clause` and the anti-vacuity invariant.

Conformance specification §3.5 requires a decision to identify the clause that
produced it. The reason it exists is worth restating, because it is what these
tests are protecting: in the cross-run that produced that specification, all 13
unsafe-code cases returned the expected ``DENY`` with the expected
``UNSAFE_CODE_DETECTED``, and all 13 were produced by a language precondition
rather than by inspecting any code. Every one of them looked like a pass.

So the field is not decoration, and the invariant below is the whole point: a
decision that refuses a request must record what refused it. A ``DENY``
attributed to ``none`` asserts that something was blocked while recording nothing
about what blocked it, which is unauditable and indistinguishable from a bug.
"""

import pytest
from pydantic import ValidationError

from tealtiger.core.circuit import CircuitState, TealCircuit
from tealtiger.core.context import ContextManager
from tealtiger.core.engine import (
    CLAUSE_NONE,
    CLAUSE_UNKNOWN,
    Decision,
    DecisionAction,
    ModeConfig,
    PolicyMode,
    ReasonCode,
    TealEngine,
)
from tealtiger.core.guard import TealGuard
from tealtiger.core.guard.types import GuardrailResult


def _decision(**overrides):
    """A minimal valid Decision, so each test states only what it is about."""
    kwargs = {
        "action": DecisionAction.ALLOW,
        "reason_codes": [ReasonCode.POLICY_COMPLIANT],
        "risk_score": 0,
        "mode": PolicyMode.ENFORCE,
        "policy_id": "test.policy",
        "policy_version": "1.0.0",
        "component_versions": {"engine": "1.1.0"},
        "correlation_id": "test-correlation-id",
        "reason": "test",
    }
    kwargs.update(overrides)
    return Decision(**kwargs)


class TestTriggeringClauseField:
    """The field itself: default, and what it accepts."""

    def test_defaults_to_none_so_existing_callers_keep_working(self):
        """Defaulted rather than required, which is why adding it broke no caller."""
        assert _decision().triggering_clause == CLAUSE_NONE

    def test_allow_may_report_no_clause(self):
        """§5.3: an empty or absent policy allows with a clause of `none`."""
        decision = _decision(action=DecisionAction.ALLOW, triggering_clause=CLAUSE_NONE)

        assert decision.action == DecisionAction.ALLOW
        assert decision.triggering_clause == CLAUSE_NONE

    def test_clause_is_preserved_verbatim(self):
        """Dotted clause paths are data, not parsed or normalised."""
        for clause in (
            "tools.file_delete.allowed",
            "tools.unregistered_tool.absent",
            "tools.*.allowed",
            "request.tool.missing",
            "guardrail.PIIDetectionGuardrail",
            "circuit.open",
        ):
            assert _decision(
                action=DecisionAction.DENY, triggering_clause=clause
            ).triggering_clause == clause


class TestNonAllowMustNameItsClause:
    """The invariant, enforced on construction rather than trusted to callers."""

    def test_deny_without_a_clause_is_rejected(self):
        with pytest.raises(ValidationError) as excinfo:
            _decision(action=DecisionAction.DENY)

        message = str(excinfo.value)
        assert "triggering_clause" in message
        assert "DENY" in message

    def test_the_error_says_what_to_do_about_it(self):
        """A validator that only says 'invalid' makes the next person guess."""
        with pytest.raises(ValidationError) as excinfo:
            _decision(action=DecisionAction.DENY)

        message = str(excinfo.value)
        assert "§3.5" in message or "3.5" in message
        assert "guardrail." in message
        assert "circuit.open" in message

    def test_deny_with_a_clause_is_accepted(self):
        decision = _decision(
            action=DecisionAction.DENY,
            reason_codes=[ReasonCode.POLICY_VIOLATION, ReasonCode.TOOL_NOT_ALLOWED],
            triggering_clause="tools.file_delete.allowed",
        )

        assert decision.action == DecisionAction.DENY
        assert decision.triggering_clause == "tools.file_delete.allowed"

    @pytest.mark.parametrize(
        "action",
        [
            DecisionAction.DENY,
            DecisionAction.REDACT,
            DecisionAction.TRANSFORM,
            DecisionAction.REQUIRE_APPROVAL,
            DecisionAction.DEGRADE,
        ],
    )
    def test_the_invariant_covers_every_non_allow_action(self, action):
        """Not just DENY.

        REDACT, TRANSFORM, REQUIRE_APPROVAL and DEGRADE all change what happens to
        the request, so each needs to say what decided that. Scoping the rule to
        DENY alone would leave four ways to produce an unattributed intervention.
        """
        with pytest.raises(ValidationError):
            _decision(action=action)

        assert _decision(action=action, triggering_clause="tools.x.allowed")

    def test_unknown_is_permitted_as_an_honest_last_resort(self):
        """`unknown` says "something decided and I cannot tell you what".

        Worse than a clause path and better than `none`: it does not claim that
        nothing decided, and it does not invent a clause no policy contains.
        """
        decision = _decision(
            action=DecisionAction.DENY, triggering_clause=CLAUSE_UNKNOWN
        )

        assert decision.triggering_clause == CLAUSE_UNKNOWN


class TestEngineReportsNoClauseWhenItEvaluatesNothing:
    """REPORT_ONLY is the one mode this engine can still serve."""

    def test_report_only_reports_no_clause(self):
        """§5.4: REPORT_ONLY skips evaluation, so no clause decided.

        This is the honest pairing the mode exists for, and it is asserted here so
        that a future change cannot start reporting a clause the engine never
        consulted.
        """
        engine = TealEngine(
            policies={"tools": {"file_delete": {"allowed": False}}},
            mode=ModeConfig(default=PolicyMode.REPORT_ONLY),
        )

        decision = engine.evaluate_with_mode(
            {"agentId": "a", "action": "tool.execute", "tool": "file_delete"}
        )

        assert decision.action == DecisionAction.ALLOW
        assert decision.triggering_clause == CLAUSE_NONE
        assert decision.metadata["evaluation_performed"] is False


class TestGuardAttributesItsOwnDenials:
    """`TealGuard` denies on a guardrail, which is identifiable, so it says which one.

    These drive `_build_decision` directly. The public `check()` path needs registered
    guardrails and real failing input to reach a denial; the attribution logic is what
    changed, and calling it with synthetic results isolates exactly that.
    """

    def _build(self, guard, *, passed, results, policy_decision=None):
        return guard._build_decision(
            passed=passed,
            guardrail_results=results,
            policy_decision=policy_decision,
            execution_context=ContextManager.create_context(),
            execution_time=1,
        )

    def test_denial_names_the_guardrail_that_failed(self):
        guard = TealGuard()
        results = [
            GuardrailResult(name="PIIDetectionGuardrail", passed=False, message="pii"),
        ]

        decision = self._build(guard, passed=False, results=results)

        assert decision.action == DecisionAction.DENY
        assert decision.triggering_clause == "guardrail.PIIDetectionGuardrail"

    def test_first_failing_guardrail_wins_when_several_fail(self):
        """Short-circuit attribution, matching §5.2's permission to stop at the first."""
        guard = TealGuard()
        results = [
            GuardrailResult(name="PIIDetectionGuardrail", passed=False),
            GuardrailResult(name="PromptInjectionGuardrail", passed=False),
        ]

        decision = self._build(guard, passed=False, results=results)

        assert decision.triggering_clause == "guardrail.PIIDetectionGuardrail"

    def test_passing_check_reports_no_clause(self):
        guard = TealGuard()
        results = [GuardrailResult(name="PIIDetectionGuardrail", passed=True)]

        decision = self._build(guard, passed=True, results=results)

        assert decision.action == DecisionAction.ALLOW
        assert decision.triggering_clause == CLAUSE_NONE

    def test_an_inherited_policy_denial_keeps_the_policy_clause(self):
        """When the policy supplied the action, the policy's clause is the honest one.

        Overwriting it with a guardrail name would attribute the decision to something
        that did not make it.
        """
        guard = TealGuard()
        policy_decision = _decision(
            action=DecisionAction.DENY,
            reason_codes=[ReasonCode.POLICY_VIOLATION, ReasonCode.TOOL_NOT_ALLOWED],
            triggering_clause="tools.file_delete.allowed",
        )
        results = [GuardrailResult(name="PIIDetectionGuardrail", passed=False)]

        decision = self._build(
            guard, passed=False, results=results, policy_decision=policy_decision
        )

        assert decision.triggering_clause == "tools.file_delete.allowed"

    def test_unattributable_inherited_denial_becomes_unknown(self):
        """A non-ALLOW policy decision carrying `none` is a bug upstream.

        This component cannot say which clause decided, so it says `unknown` rather
        than `none` — which the validator rejects on a denial — and rather than
        blaming a guardrail that did not produce the action.
        """
        guard = TealGuard()
        policy_decision = _decision(action=DecisionAction.ALLOW)
        # Bypass the validator to construct the broken upstream decision this guards
        # against, since the validator is exactly what makes it unconstructable.
        object.__setattr__(policy_decision, "action", DecisionAction.DENY)
        assert policy_decision.triggering_clause == CLAUSE_NONE

        decision = self._build(
            guard,
            passed=True,
            results=[],
            policy_decision=policy_decision,
        )

        assert decision.action == DecisionAction.DENY
        assert decision.triggering_clause == CLAUSE_UNKNOWN


class TestCircuitAttributesItsOwnDenials:
    """The circuit breaker is not policy evaluation, but it still refuses requests."""

    def test_open_circuit_names_the_state_that_refused(self):
        circuit = TealCircuit()
        circuit.force_open()

        decision = circuit.evaluate(ContextManager.create_context())

        assert decision.action == DecisionAction.DENY
        assert decision.triggering_clause == "circuit.open"
        assert decision.metadata["circuit_state"] == CircuitState.OPEN.value

    def test_closed_circuit_reports_no_clause(self):
        decision = TealCircuit().evaluate(ContextManager.create_context())

        assert decision.action == DecisionAction.ALLOW
        assert decision.triggering_clause == CLAUSE_NONE

    def test_half_open_circuit_reports_no_clause(self):
        """HALF_OPEN allows, so nothing refused and nothing to attribute."""
        circuit = TealCircuit()
        circuit.force_open()
        circuit._transition_to(CircuitState.HALF_OPEN)

        decision = circuit.evaluate(ContextManager.create_context())

        assert decision.action == DecisionAction.ALLOW
        assert decision.triggering_clause == CLAUSE_NONE
