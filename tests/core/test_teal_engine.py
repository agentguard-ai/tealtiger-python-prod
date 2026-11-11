"""Tests for TealEngine with Decision contract.

TealTiger SDK v1.1.x - Enterprise Adoption Features
Phase 2: Decision Contract

Scope note
----------
``TealEngine`` does not evaluate policy in the Python SDK. Under ``ENFORCE`` and
``MONITOR`` it raises :class:`NotImplementedError` rather than returning a decision.
Until this release it returned ALLOW for every request regardless of the configured
policy, reporting ``POLICY_COMPLIANT`` with a risk score of 0 -- a tool configured
``{"allowed": False}`` was permitted, as were prompt injection, PII, unsafe code and
any cost above any limit.

These tests therefore assert two things and nothing more:

1. ``ENFORCE`` and ``MONITOR`` fail loudly. This is the regression guard against the
   silent-allow defect returning: a test that accepted an ALLOW from those modes would
   be a check that cannot fail.
2. ``REPORT_ONLY`` still works and still honours the Decision contract. That mode's
   contract is that evaluation is *skipped*, which this engine can satisfy honestly, so
   it remains the correct surface for exercising Decision construction, mode resolution,
   component versions and context propagation.

Mode *resolution* is independent of mode *execution*, so it is tested directly against
``resolve_policy_mode`` where the engine would otherwise refuse to run.
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


def test_teal_engine_monitor_mode_raises_not_implemented():
    """MONITOR mode must fail loudly rather than report a policy it never evaluated."""
    engine = TealEngine(
        policies={},
        mode=ModeConfig(default=PolicyMode.MONITOR),
    )

    context = ContextManager.create_context()
    with pytest.raises(NotImplementedError) as excinfo:
        engine.evaluate_with_mode(
            {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"},
            context,
        )

    # The error must point the caller at surfaces that do work.
    assert "does not evaluate policy" in str(excinfo.value)
    assert "REPORT_ONLY" in str(excinfo.value)


def test_teal_engine_enforce_mode_raises_not_implemented():
    """ENFORCE mode must fail loudly rather than permit every request."""
    engine = TealEngine(
        policies={},
        mode=ModeConfig(default=PolicyMode.ENFORCE),
    )

    context = ContextManager.create_context()
    with pytest.raises(NotImplementedError):
        engine.evaluate_with_mode(
            {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"},
            context,
        )


def test_teal_engine_enforce_does_not_allow_denied_tool():
    """Regression guard for the silent-allow defect.

    A tool explicitly configured ``{"allowed": False}`` must never come back ALLOW.
    While evaluation is unimplemented the required outcome is NotImplementedError; if
    evaluation is implemented later the required outcome is DENY. Anything else -- in
    particular an ALLOW -- is the original defect.
    """
    engine = TealEngine(
        policies={"tools": {"file_delete": {"allowed": False}}},
        mode=ModeConfig(default=PolicyMode.ENFORCE),
    )

    try:
        decision = engine.evaluate_with_mode(
            {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"},
        )
    except NotImplementedError:
        return  # Current, documented behaviour.

    assert decision.action == DecisionAction.DENY, (
        "TealEngine returned a non-DENY decision for a tool configured allowed=False. "
        "This is the silent-allow defect; see TealEngine._evaluate_policies."
    )


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

    # Policy-specific override (highest priority) resolves to REPORT_ONLY, which the
    # engine can serve, so the resolved mode is observable on the Decision.
    context = ContextManager.create_context()
    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"},
        context,
    )
    assert decision.mode == PolicyMode.REPORT_ONLY

    # Environment override resolves to MONITOR, which raises. The raise is itself the
    # evidence that resolution did not fall through to REPORT_ONLY.
    context_staging = ContextManager.create_context()
    context_staging.environment = "staging"
    with pytest.raises(NotImplementedError):
        engine.evaluate_with_mode(
            {"agentId": "agent-001", "action": "tool.execute", "tool": "other_tool"},
            context_staging,
        )


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
