"""Tests for TealEngine with Decision contract.

TealTiger SDK v1.1.x - Enterprise Adoption Features
Phase 2: Decision Contract
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


def test_teal_engine_monitor_mode():
    """Test TealEngine in MONITOR mode always allows but logs violations."""
    engine = TealEngine(
        policies={},
        mode=ModeConfig(default=PolicyMode.MONITOR),
    )
    
    context = ContextManager.create_context()
    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"},
        context,
    )
    
    assert isinstance(decision, Decision)
    assert decision.action == DecisionAction.ALLOW
    assert decision.mode == PolicyMode.MONITOR
    assert decision.correlation_id == context.correlation_id
    assert decision.metadata["evaluation_performed"] is True


def test_teal_engine_enforce_mode():
    """Test TealEngine in ENFORCE mode blocks violations."""
    engine = TealEngine(
        policies={},
        mode=ModeConfig(default=PolicyMode.ENFORCE),
    )
    
    context = ContextManager.create_context()
    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"},
        context,
    )
    
    assert isinstance(decision, Decision)
    assert decision.mode == PolicyMode.ENFORCE
    assert decision.correlation_id == context.correlation_id
    assert decision.metadata["evaluation_performed"] is True


def test_teal_engine_decision_structure():
    """Test that Decision object has all required fields."""
    engine = TealEngine(
        policies={},
        mode=ModeConfig(default=PolicyMode.ENFORCE),
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


def test_teal_engine_hierarchical_mode_resolution():
    """Test hierarchical mode resolution (policy > environment > global)."""
    engine = TealEngine(
        policies={},
        mode=ModeConfig(
            default=PolicyMode.ENFORCE,
            environment={"staging": PolicyMode.MONITOR},
            policy={"tools.file_delete": PolicyMode.REPORT_ONLY},
        ),
    )
    
    # Test policy-specific override (highest priority)
    context = ContextManager.create_context()
    decision = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"},
        context,
    )
    assert decision.mode == PolicyMode.REPORT_ONLY
    
    # Test environment-specific override
    context_staging = ContextManager.create_context()
    context_staging.environment = "staging"
    decision_staging = engine.evaluate_with_mode(
        {"agentId": "agent-001", "action": "tool.execute", "tool": "other_tool"},
        context_staging,
    )
    assert decision_staging.mode == PolicyMode.MONITOR


def test_teal_engine_component_versions():
    """Test that component versions are included in Decision."""
    engine = TealEngine(
        policies={},
        mode=ModeConfig(default=PolicyMode.ENFORCE),
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
        mode=ModeConfig(default=PolicyMode.ENFORCE),
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
        mode=ModeConfig(default=PolicyMode.ENFORCE),
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
