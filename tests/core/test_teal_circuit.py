"""Tests for TealCircuit with Decision contract.

TealTiger SDK v1.1.x - Enterprise Adoption Features
Phase 2: Decision Contract
"""

import pytest

from tealtiger.core.circuit import CircuitOpenError, CircuitState, TealCircuit
from tealtiger.core.context import ContextManager
from tealtiger.core.engine import Decision, DecisionAction, PolicyMode, ReasonCode


def test_teal_circuit_initialization():
    """Test TealCircuit initialization."""
    circuit = TealCircuit(
        failure_threshold=5,
        timeout=60000,
        half_open_requests=3,
    )
    
    assert circuit is not None
    assert circuit.state == CircuitState.CLOSED
    assert circuit.failures == 0


def test_teal_circuit_evaluate_returns_decision():
    """Test that TealCircuit.evaluate() returns a Decision object."""
    circuit = TealCircuit()
    context = ContextManager.create_context()
    
    decision = circuit.evaluate(context)
    
    assert isinstance(decision, Decision)
    assert decision.action in [DecisionAction.ALLOW, DecisionAction.DENY]
    assert decision.correlation_id == context.correlation_id
    assert decision.policy_id == "circuit.breaker"


def test_teal_circuit_closed_state():
    """Test TealCircuit in CLOSED state allows requests."""
    circuit = TealCircuit()
    context = ContextManager.create_context()
    
    decision = circuit.evaluate(context)
    
    assert decision.action == DecisionAction.ALLOW
    assert ReasonCode.POLICY_COMPLIANT in decision.reason_codes
    assert decision.risk_score == 0
    assert decision.metadata["circuit_state"] == CircuitState.CLOSED.value


def test_teal_circuit_open_state():
    """Test TealCircuit in OPEN state denies requests."""
    circuit = TealCircuit()
    circuit.force_open()
    
    context = ContextManager.create_context()
    decision = circuit.evaluate(context)
    
    assert decision.action == DecisionAction.DENY
    assert ReasonCode.CIRCUIT_OPEN in decision.reason_codes
    assert decision.risk_score == 100
    assert decision.metadata["circuit_state"] == CircuitState.OPEN.value


def test_teal_circuit_half_open_state():
    """Test TealCircuit in HALF_OPEN state allows requests with medium risk."""
    circuit = TealCircuit()
    circuit.force_open()
    
    # Manually transition to half-open
    circuit._transition_to(CircuitState.HALF_OPEN)
    
    context = ContextManager.create_context()
    decision = circuit.evaluate(context)
    
    assert decision.action == DecisionAction.ALLOW
    assert ReasonCode.CIRCUIT_HALF_OPEN in decision.reason_codes
    assert decision.risk_score == 50
    assert decision.metadata["circuit_state"] == CircuitState.HALF_OPEN.value


def test_teal_circuit_decision_structure():
    """Test that Decision object has all required fields."""
    circuit = TealCircuit()
    context = ContextManager.create_context()
    
    decision = circuit.evaluate(context)
    
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
    
    # Circuit breaker always enforces
    assert decision.mode == PolicyMode.ENFORCE
    
    # Validate risk score bounds
    assert 0 <= decision.risk_score <= 100


def test_teal_circuit_component_versions():
    """Test that component versions include circuit."""
    circuit = TealCircuit()
    context = ContextManager.create_context()
    
    decision = circuit.evaluate(context)
    
    assert "sdk" in decision.component_versions
    assert "circuit" in decision.component_versions


def test_teal_circuit_execution_context_propagation():
    """Test that ExecutionContext fields are propagated to Decision."""
    circuit = TealCircuit()
    
    context = ContextManager.create_context()
    context.trace_id = "trace-123"
    context.workflow_id = "workflow-456"
    context.tenant_id = "tenant-xyz"
    
    decision = circuit.evaluate(context)
    
    assert decision.correlation_id == context.correlation_id
    assert decision.trace_id == "trace-123"
    assert decision.workflow_id == "workflow-456"
    assert decision.metadata["tenant_id"] == "tenant-xyz"


def test_teal_circuit_auto_generates_context():
    """Test that TealCircuit auto-generates ExecutionContext if not provided."""
    circuit = TealCircuit()
    
    # Call without ExecutionContext
    decision = circuit.evaluate()
    
    # Should have auto-generated correlation_id
    assert decision.correlation_id is not None
    assert len(decision.correlation_id) > 0


def test_teal_circuit_metadata_includes_stats():
    """Test that metadata includes circuit statistics."""
    circuit = TealCircuit()
    context = ContextManager.create_context()
    
    decision = circuit.evaluate(context)
    
    assert "circuit_state" in decision.metadata
    assert "failures" in decision.metadata
    assert "last_failure_time" in decision.metadata
    assert "half_open_attempts" in decision.metadata


@pytest.mark.asyncio
async def test_teal_circuit_execute_success():
    """Test TealCircuit.execute() with successful function."""
    circuit = TealCircuit()
    
    async def successful_fn():
        return "success"
    
    result = await circuit.execute(successful_fn)
    assert result == "success"
    assert circuit.state == CircuitState.CLOSED
    assert circuit.failures == 0


@pytest.mark.asyncio
async def test_teal_circuit_execute_failure():
    """Test TealCircuit.execute() with failing function."""
    circuit = TealCircuit(failure_threshold=2)
    
    async def failing_fn():
        raise ValueError("Test error")
    
    # First failure
    with pytest.raises(ValueError):
        await circuit.execute(failing_fn)
    
    assert circuit.failures == 1
    assert circuit.state == CircuitState.CLOSED
    
    # Second failure should open circuit
    with pytest.raises(ValueError):
        await circuit.execute(failing_fn)
    
    assert circuit.failures == 2
    assert circuit.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_teal_circuit_execute_open_raises_error():
    """Test that execute() raises CircuitOpenError when circuit is open."""
    circuit = TealCircuit()
    circuit.force_open()
    
    async def test_fn():
        return "test"
    
    with pytest.raises(CircuitOpenError):
        await circuit.execute(test_fn)


def test_teal_circuit_reset():
    """Test TealCircuit.reset() resets state."""
    circuit = TealCircuit()
    circuit.force_open()
    circuit.failures = 5
    
    circuit.reset()
    
    assert circuit.state == CircuitState.CLOSED
    assert circuit.failures == 0
    assert circuit.last_failure_time is None


def test_teal_circuit_get_stats():
    """Test TealCircuit.get_stats() returns statistics."""
    circuit = TealCircuit()
    
    stats = circuit.get_stats()
    
    assert "state" in stats
    assert "failures" in stats
    assert "last_failure_time" in stats
    assert "half_open_attempts" in stats
