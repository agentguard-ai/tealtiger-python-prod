"""Tests for TealGuard with Decision contract.

TealTiger SDK v1.1.x - Enterprise Adoption Features
Phase 2: Decision Contract
"""

import pytest

from tealtiger.core.context import ContextManager
from tealtiger.core.engine import Decision, DecisionAction, PolicyMode
from tealtiger.core.guard import TealGuard


@pytest.mark.asyncio
async def test_teal_guard_initialization():
    """Test TealGuard initialization."""
    guard = TealGuard()
    
    assert guard is not None
    assert guard.policy_driven is False


@pytest.mark.asyncio
async def test_teal_guard_check_returns_decision():
    """Test that TealGuard.check() returns a Decision object."""
    guard = TealGuard()
    context = ContextManager.create_context()
    
    decision = await guard.check("Hello world", context)
    
    assert isinstance(decision, Decision)
    assert decision.action in [DecisionAction.ALLOW, DecisionAction.DENY]
    assert decision.correlation_id == context.correlation_id
    assert decision.policy_id == "guardrail.check"


@pytest.mark.asyncio
async def test_teal_guard_decision_structure():
    """Test that Decision object has all required fields."""
    guard = TealGuard()
    context = ContextManager.create_context()
    
    decision = await guard.check("Test input", context)
    
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
    
    # Validate risk score bounds
    assert 0 <= decision.risk_score <= 100


@pytest.mark.asyncio
async def test_teal_guard_component_versions():
    """Test that component versions include guard."""
    guard = TealGuard()
    context = ContextManager.create_context()
    
    decision = await guard.check("Test input", context)
    
    assert "sdk" in decision.component_versions
    assert "guard" in decision.component_versions


@pytest.mark.asyncio
async def test_teal_guard_execution_context_propagation():
    """Test that ExecutionContext fields are propagated to Decision."""
    guard = TealGuard()
    
    context = ContextManager.create_context()
    context.trace_id = "trace-123"
    context.workflow_id = "workflow-456"
    context.tenant_id = "tenant-xyz"
    
    decision = await guard.check("Test input", context)
    
    assert decision.correlation_id == context.correlation_id
    assert decision.trace_id == "trace-123"
    assert decision.workflow_id == "workflow-456"
    assert decision.metadata["tenant_id"] == "tenant-xyz"


@pytest.mark.asyncio
async def test_teal_guard_auto_generates_context():
    """Test that TealGuard auto-generates ExecutionContext if not provided."""
    guard = TealGuard()
    
    # Call without ExecutionContext
    decision = await guard.check("Test input")
    
    # Should have auto-generated correlation_id
    assert decision.correlation_id is not None
    assert len(decision.correlation_id) > 0


@pytest.mark.asyncio
async def test_teal_guard_metadata_includes_guardrail_results():
    """Test that metadata includes guardrail results."""
    guard = TealGuard()
    context = ContextManager.create_context()
    
    decision = await guard.check("Test input", context)
    
    assert "guardrail_results" in decision.metadata
    assert "passed" in decision.metadata["guardrail_results"]
    assert "total" in decision.metadata["guardrail_results"]
    assert "failed" in decision.metadata["guardrail_results"]
