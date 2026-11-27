"""Tests for TealEngine with Decision contract.

TealTiger SDK v1.1.x - Enterprise Adoption Features
Phase 2: Decision Contract

Scope note
----------
``TealEngine`` enforces **tool allowlist** and nothing else. Every other rule type is
UNSPECIFIED in conformance specification v0.1 §7, so a policy that configures one is
refused with ``UnsupportedPolicySectionError`` rather than partially honoured.

That boundary is what these tests mostly exist to hold. The history is short and worth
keeping in view:

- before 1.6.0 — every request was ALLOWed without the policy being read at all, while
  the decision reported ``POLICY_COMPLIANT`` and a risk score of 0
- 1.6.0 — that silent allow was replaced with a loud ``NotImplementedError``
- now — a real decision for the one rule type the specification defines, and a loud
  refusal for the ones it does not

So the regression guard has moved rather than disappeared. It is no longer "ENFORCE must
raise"; it is **"a configured deny must come back DENY, and a section we cannot enforce
must never contribute an ALLOW"**. A test that accepted an ALLOW for a tool configured
``{"allowed": False}`` would be a check that cannot fail, which is what the original
seven tests here were.

Per-requirement coverage of TA-1 … TA-8 lives in
``tests/core/engine/test_policy_evaluator.py``, against the published corpus. This module
tests the engine's part: mode behaviour (§5.4), the support boundary (§9.1, §9.2), and
the Decision contract.
"""

import pytest

from tealtiger.core.context import ContextManager
from tealtiger.core.engine import (
    Decision,
    DecisionAction,
    ModeConfig,
    PolicyMode,
    ReasonCode,
    TealEngine,
)
from tealtiger.core.engine.policy_evaluator import (
    SUPPORTED_RULE_TYPES,
    UnsupportedPolicySectionError,
)
from tealtiger.core.engine.teal_engine import resolve_policy_mode


def test_teal_engine_initialization():
    """Test TealEngine initialization with mode configuration."""
    engine = TealEngine(
        policies={},
        mode=ModeConfig(default=PolicyMode.ENFORCE),
    )

    assert engine is not None
    assert engine.mode_config.default == PolicyMode.ENFORCE


def test_teal_engine_report_only_mode():
    """Test TealEngine in REPORT_ONLY mode always allows requests."""
    engine = TealEngine(
        policies={},
        mode=ModeConfig(default=PolicyMode.REPORT_ONLY),
    )

    context = ContextManager.create_context()
    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"},
        context,
    )

    assert isinstance(decision, Decision)
    assert decision.action == DecisionAction.ALLOW
    assert ReasonCode.REPORT_ONLY_MODE in decision.reason_codes
    assert decision.risk_score == 0
    assert decision.mode == PolicyMode.REPORT_ONLY
    assert decision.correlation_id == context.correlation_id


def test_teal_engine_report_only_declares_evaluation_skipped():
    """REPORT_ONLY must not claim an evaluation it did not perform."""
    engine = TealEngine(
        policies={},
        mode=ModeConfig(default=PolicyMode.REPORT_ONLY),
    )

    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"},
    )

    # The honest signal: this mode skipped evaluation and says so.
    assert decision.metadata["evaluation_performed"] is False
    assert decision.metadata["triggered_policies"] == []
    # It must not report policy compliance, which would imply policy was checked.
    assert ReasonCode.POLICY_COMPLIANT not in decision.reason_codes


def test_teal_engine_monitor_mode_evaluates_then_allows():
    """§5.4: MONITOR evaluates fully, returns ALLOW, and preserves the would-be denial.

    The point of the mode is a rollout where you learn what *would* be blocked without
    blocking it. That only works if the decision still carries the reason codes and the
    clause, so this asserts the recording rather than just the ALLOW.
    """
    engine = TealEngine(
        policies={"tools": {"file_delete": {"allowed": False}}},
        mode=ModeConfig(default=PolicyMode.MONITOR),
    )

    context = ContextManager.create_context()
    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"},
        context,
    )

    assert decision.action == DecisionAction.ALLOW
    assert decision.mode == PolicyMode.MONITOR
    assert decision.metadata["evaluation_performed"] is True

    # The would-be denial, preserved.
    assert ReasonCode.MONITOR_MODE_VIOLATION in decision.reason_codes
    assert ReasonCode.TOOL_NOT_ALLOWED in decision.reason_codes
    assert decision.triggering_clause == "tools.file_delete.allowed"
    assert decision.metadata["triggered_policies"] == ["tools.file_delete.allowed"]


def test_teal_engine_monitor_mode_allows_a_permitted_tool_without_a_clause():
    """Nothing would have been blocked, so there is nothing to record."""
    engine = TealEngine(
        policies={"tools": {"search": {"allowed": True}}},
        mode=ModeConfig(default=PolicyMode.MONITOR),
    )

    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "search"}
    )

    assert decision.action == DecisionAction.ALLOW
    assert decision.reason_codes == [ReasonCode.POLICY_COMPLIANT]
    assert decision.triggering_clause == "none"
    assert ReasonCode.MONITOR_MODE_VIOLATION not in decision.reason_codes


def test_teal_engine_enforce_allows_under_an_empty_policy():
    """§5.3: an empty or absent policy allows, with POLICY_COMPLIANT and `none`.

    This is the case that used to raise. It is specified behaviour, not a gap: a policy
    that configures nothing has nothing to enforce.
    """
    engine = TealEngine(
        policies={},
        mode=ModeConfig(default=PolicyMode.ENFORCE),
    )

    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"},
        ContextManager.create_context(),
    )

    assert decision.action == DecisionAction.ALLOW
    assert decision.reason_codes == [ReasonCode.POLICY_COMPLIANT]
    assert decision.triggering_clause == "none"


def test_teal_engine_enforce_does_not_allow_denied_tool():
    """Regression guard for the silent-allow defect.

    A tool explicitly configured ``{"allowed": False}`` must never come back ALLOW.
    Written when evaluation did not exist, to accept ``NotImplementedError`` then and
    require ``DENY`` once it did. This is that second branch, now live.
    """
    engine = TealEngine(
        policies={"tools": {"file_delete": {"allowed": False}}},
        mode=ModeConfig(default=PolicyMode.ENFORCE),
    )

    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"},
    )

    assert decision.action == DecisionAction.DENY, (
        "TealEngine returned a non-DENY decision for a tool configured allowed=False. "
        "This is the silent-allow defect."
    )
    assert decision.reason_codes == [
        ReasonCode.POLICY_VIOLATION,
        ReasonCode.TOOL_NOT_ALLOWED,
    ]
    assert decision.triggering_clause == "tools.file_delete.allowed"


def test_teal_engine_enforce_default_denies_an_unconfigured_tool():
    """TA-4 through the engine: an unknown tool is not an allowed tool."""
    engine = TealEngine(
        policies={"tools": {"search": {"allowed": True}}},
        mode=ModeConfig(default=PolicyMode.ENFORCE),
    )

    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "unregistered"}
    )

    assert decision.action == DecisionAction.DENY
    assert decision.triggering_clause == "tools.unregistered.absent"


class TestTheSupportBoundary:
    """§9.1 and §9.2: what this engine claims, and what it refuses.

    The refusal is the part that matters. Evaluating the sections the engine understands
    while ignoring the rest would return an ALLOW the policy did not earn — the 1.6.0
    defect in a smaller box.
    """

    UNIMPLEMENTED = {"content": {"pii": {"action": "deny"}}}

    def test_an_unimplemented_section_is_refused_not_ignored(self):
        engine = TealEngine(
            policies=self.UNIMPLEMENTED,
            mode=ModeConfig(default=PolicyMode.ENFORCE),
        )

        with pytest.raises(UnsupportedPolicySectionError) as excinfo:
            engine.evaluate_with_mode({"agentId": "a", "action": "chat.create"})

        assert excinfo.value.sections == ("content",)

    def test_the_refusal_names_the_section_and_the_alternatives(self):
        engine = TealEngine(policies=self.UNIMPLEMENTED)

        with pytest.raises(UnsupportedPolicySectionError) as excinfo:
            engine.evaluate_with_mode({"agentId": "a", "action": "chat.create"})

        message = str(excinfo.value)
        assert "content" in message
        assert "REPORT_ONLY" in message
        assert "Guardrail" in message or "guardrail" in message

    def test_the_refusal_is_still_a_not_implemented_error(self):
        """1.6.0 told callers to expect NotImplementedError. That stays true."""
        engine = TealEngine(policies=self.UNIMPLEMENTED)

        with pytest.raises(NotImplementedError):
            engine.evaluate_with_mode({"agentId": "a", "action": "chat.create"})

    def test_a_mixed_policy_is_refused_whole(self):
        """Not "enforce the half we understand". The policy asked for more than that."""
        engine = TealEngine(
            policies={
                "tools": {"file_delete": {"allowed": False}},
                "content": {"pii": {"action": "deny"}},
            },
            mode=ModeConfig(default=PolicyMode.ENFORCE),
        )

        with pytest.raises(UnsupportedPolicySectionError):
            engine.evaluate_with_mode(
                {"agentId": "a", "action": "tool.execute", "tool": "file_delete"}
            )

    def test_report_only_honours_any_policy(self):
        """That mode promises no evaluation, so it can keep the promise regardless."""
        engine = TealEngine(
            policies=self.UNIMPLEMENTED,
            mode=ModeConfig(default=PolicyMode.REPORT_ONLY),
        )

        decision = engine.evaluate_with_mode({"agentId": "a", "action": "chat.create"})

        assert decision.action == DecisionAction.ALLOW
        assert decision.reason_codes == [ReasonCode.REPORT_ONLY_MODE]
        assert decision.metadata["evaluation_performed"] is False

    def test_unenforceable_sections_can_be_checked_before_any_request(self):
        """So a caller finds out at startup, not on the first denial that mattered."""
        assert TealEngine(policies=self.UNIMPLEMENTED).unenforceable_sections() == (
            "content",
        )
        assert TealEngine(policies={"tools": {}}).unenforceable_sections() == ()
        assert TealEngine(policies={}).unenforceable_sections() == ()

    def test_the_published_support_claim_matches_what_is_enforced(self):
        """§9.1. A claim that only exists in a README is one nobody can check."""
        support = TealEngine.rule_type_support()

        assert support["tools"] == "enforced"
        enforced = {name for name, state in support.items() if state == "enforced"}
        assert enforced == set(SUPPORTED_RULE_TYPES)


def test_teal_engine_decision_structure():
    """Test that Decision object has all required fields.

    Exercised through REPORT_ONLY, the one mode this engine can serve.
    """
    engine = TealEngine(
        policies={},
        mode=ModeConfig(default=PolicyMode.REPORT_ONLY),
    )

    context = ContextManager.create_context()
    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"},
        context,
    )

    # Required fields
    assert hasattr(decision, "action")
    assert hasattr(decision, "reason_codes")
    assert hasattr(decision, "risk_score")
    assert hasattr(decision, "mode")
    assert hasattr(decision, "policy_id")
    assert hasattr(decision, "policy_version")
    assert hasattr(decision, "component_versions")
    assert hasattr(decision, "correlation_id")
    assert hasattr(decision, "reason")
    assert hasattr(decision, "metadata")

    # Validate types
    assert isinstance(decision.action, DecisionAction)
    assert isinstance(decision.reason_codes, list)
    assert isinstance(decision.risk_score, int)
    assert isinstance(decision.mode, PolicyMode)
    assert isinstance(decision.policy_id, str)
    assert isinstance(decision.policy_version, str)
    assert isinstance(decision.component_versions, dict)
    assert isinstance(decision.correlation_id, str)
    assert isinstance(decision.reason, str)
    assert isinstance(decision.metadata, dict)

    # Validate risk score bounds
    assert 0 <= decision.risk_score <= 100


def test_resolve_policy_mode_hierarchy():
    """Mode resolution precedence: policy > environment > global default.

    Tested directly, because resolution is independent of whether the resolved mode
    can then be executed.
    """
    mode_config = ModeConfig(
        default=PolicyMode.ENFORCE,
        environment={"staging": PolicyMode.MONITOR},
        policy={"tools.file_delete": PolicyMode.REPORT_ONLY},
    )

    # Policy-specific override wins, even against a matching environment override.
    assert (
        resolve_policy_mode("tools.file_delete", mode_config, environment="staging")
        == PolicyMode.REPORT_ONLY
    )

    # Environment override applies when no policy-specific entry matches.
    assert (
        resolve_policy_mode("tools.other_tool", mode_config, environment="staging")
        == PolicyMode.MONITOR
    )

    # Global default applies when neither matches.
    assert (
        resolve_policy_mode("tools.other_tool", mode_config, environment="prod")
        == PolicyMode.ENFORCE
    )
    assert resolve_policy_mode("tools.other_tool", mode_config) == PolicyMode.ENFORCE


def test_teal_engine_hierarchical_mode_resolution():
    """Test hierarchical mode resolution as observed through the engine."""
    engine = TealEngine(
        policies={},
        mode=ModeConfig(
            default=PolicyMode.ENFORCE,
            environment={"staging": PolicyMode.MONITOR},
            policy={"tools.file_delete": PolicyMode.REPORT_ONLY},
        ),
    )

    # Policy-specific override (highest priority).
    context = ContextManager.create_context()
    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"},
        context,
    )
    assert decision.mode == PolicyMode.REPORT_ONLY

    # Environment override applies where no policy-specific entry matches. Now that
    # MONITOR executes, the resolved mode is observable on the Decision itself rather
    # than inferred from which exception came back.
    context_staging = ContextManager.create_context()
    context_staging.environment = "staging"
    decision_staging = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "other_tool"},
        context_staging,
    )
    assert decision_staging.mode == PolicyMode.MONITOR

    # Global default applies where neither override matches.
    context_prod = ContextManager.create_context()
    context_prod.environment = "prod"
    decision_prod = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "other_tool"},
        context_prod,
    )
    assert decision_prod.mode == PolicyMode.ENFORCE


def test_teal_engine_component_versions():
    """Test that component versions are included in Decision."""
    engine = TealEngine(
        policies={},
        mode=ModeConfig(default=PolicyMode.REPORT_ONLY),
    )

    context = ContextManager.create_context()
    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute"},
        context,
    )

    assert "sdk" in decision.component_versions
    assert "engine" in decision.component_versions
    assert decision.component_versions["sdk"] is not None
    assert decision.component_versions["engine"] is not None


def test_teal_engine_execution_context_propagation():
    """Test that ExecutionContext fields are propagated to Decision."""
    context = ContextManager.create_context()
    context.trace_id = "trace-123"
    context.workflow_id = "workflow-456"
    context.run_id = "run-789"
    context.span_id = "span-abc"
    context.tenant_id = "tenant-xyz"

    engine = TealEngine(
        policies={},
        mode=ModeConfig(default=PolicyMode.REPORT_ONLY),
    )

    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute"},
        context,
    )

    assert decision.correlation_id == context.correlation_id
    assert decision.trace_id == "trace-123"
    assert decision.workflow_id == "workflow-456"
    assert decision.run_id == "run-789"
    assert decision.span_id == "span-abc"
    assert decision.metadata["tenant_id"] == "tenant-xyz"


def test_teal_engine_auto_generates_context():
    """Test that TealEngine auto-generates ExecutionContext if not provided."""
    engine = TealEngine(
        policies={},
        mode=ModeConfig(default=PolicyMode.REPORT_ONLY),
    )

    # Call without ExecutionContext
    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute"},
    )

    # Should have auto-generated correlation_id
    assert decision.correlation_id is not None
    assert len(decision.correlation_id) > 0


def test_teal_engine_invalid_mode_config():
    """Test that invalid mode configuration raises error."""
    with pytest.raises(ValueError):
        TealEngine(
            policies={},
            mode=ModeConfig(
                default="INVALID_MODE",  # type: ignore
            ),
        )
