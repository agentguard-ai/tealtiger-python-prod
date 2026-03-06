"""TealCircuit - Circuit Breaker with Decision Contract.

TealTiger SDK v1.1.x - Enterprise Adoption Features
Phase 2: Decision Contract

This module implements TealCircuit that returns Decision objects for consistency
with TealEngine and TealGuard.
"""

import time
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional, TypeVar

from ..context.context_manager import ContextManager
from ..context.execution_context import ExecutionContext
from ..engine.types import Decision, DecisionAction, PolicyMode, ReasonCode


T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""
    
    CLOSED = "closed"
    """Normal operation, requests pass through"""
    
    OPEN = "open"
    """Circuit is tripped, requests fail immediately"""
    
    HALF_OPEN = "half-open"
    """Testing if the service has recovered"""


def get_component_versions_with_circuit() -> Dict[str, str]:
    """Get component versions including circuit.
    
    Returns:
        Dict with component versions
    """
    import importlib.metadata
    
    try:
        version = importlib.metadata.version("tealtiger")
    except importlib.metadata.PackageNotFoundError:
        version = "1.1.0"
    
    return {
        "sdk": version,
        "circuit": version,
    }


class CircuitOpenError(Exception):
    """Error thrown when circuit is open."""
    
    def __init__(self, message: str = "Circuit breaker is open"):
        super().__init__(message)
        self.message = message


class TealCircuit:
    """TealCircuit - Circuit breaker for preventing cascading failures.
    
    Implements the circuit breaker pattern with three states:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Circuit is tripped, requests fail immediately
    - HALF-OPEN: Testing if the service has recovered
    
    Returns Decision objects for consistency with TealEngine and TealGuard.
    
    Example:
        >>> from tealtiger.core.circuit import TealCircuit
        >>> from tealtiger.core.context import ContextManager
        >>> 
        >>> circuit = TealCircuit(
        ...     failure_threshold=5,
        ...     timeout=60000,
        ...     half_open_requests=3
        ... )
        >>> 
        >>> context = ContextManager.create_context()
        >>> decision = circuit.evaluate(context)
        >>> 
        >>> if decision.action == DecisionAction.DENY:
        ...     print("Circuit is open, service unavailable")
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 60000,
        half_open_requests: int = 3,
        on_state_change: Optional[Callable[[CircuitState, CircuitState], None]] = None,
    ):
        """Initialize TealCircuit.
        
        Args:
            failure_threshold: Number of consecutive failures before opening circuit
            timeout: Time in milliseconds to wait before attempting to close circuit
            half_open_requests: Number of successful requests in half-open state before closing
            on_state_change: Optional callback invoked when circuit state changes
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.half_open_requests = half_open_requests
        self.on_state_change = on_state_change or (lambda new, old: None)
        
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_attempts = 0
        self.component_versions = get_component_versions_with_circuit()
    
    async def execute(self, fn: Callable[[], T]) -> T:
        """Execute a function with circuit breaker protection.
        
        Args:
            fn: Async function to execute
            
        Returns:
            Result of the function
            
        Raises:
            CircuitOpenError: If circuit is open
        """
        # Check circuit state
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to(CircuitState.HALF_OPEN)
            else:
                raise CircuitOpenError("Circuit breaker is open")
        
        try:
            result = await fn()
            self._on_success()
            return result
        except Exception as error:
            self._on_failure()
            raise error
    
    def evaluate(self, context: Optional[ExecutionContext] = None) -> Decision:
        """Evaluate circuit state and return a Decision object.
        
        This method checks the circuit state and returns a Decision object
        indicating whether the operation should be allowed or denied.
        
        Part of TealTiger v1.1.x - Enterprise Adoption Features (P0.2)
        Returns Decision object with same structure as TealEngine and TealGuard.
        
        Args:
            context: Optional ExecutionContext for tracing
            
        Returns:
            Decision object with action, reason_codes, risk_score, and metadata
        """
        start_time = time.time()
        
        # Ensure we have an ExecutionContext
        execution_context = context or ContextManager.create_context()
        
        # Check if circuit should attempt reset
        if self.state == CircuitState.OPEN and self._should_attempt_reset():
            self._transition_to(CircuitState.HALF_OPEN)
        
        # Determine action based on circuit state
        if self.state == CircuitState.OPEN:
            action = DecisionAction.DENY
            reason_codes = [ReasonCode.CIRCUIT_OPEN]
            risk_score = 100  # Maximum risk when circuit is open
            reason = "Circuit breaker is open - service unavailable"
        elif self.state == CircuitState.HALF_OPEN:
            action = DecisionAction.ALLOW
            reason_codes = [ReasonCode.CIRCUIT_HALF_OPEN]
            risk_score = 50  # Medium risk in half-open state
            reason = "Circuit breaker is half-open - testing service recovery"
        else:
            action = DecisionAction.ALLOW
            reason_codes = [ReasonCode.POLICY_COMPLIANT]
            risk_score = 0  # No risk when circuit is closed
            reason = "Circuit breaker is closed - normal operation"
        
        # Build metadata
        metadata: Dict[str, Any] = {
            "evaluation_time_ms": int((time.time() - start_time) * 1000),
            "circuit_state": self.state.value,
            "failures": self.failures,
            "last_failure_time": (
                self.last_failure_time.isoformat() if self.last_failure_time else None
            ),
            "half_open_attempts": self.half_open_attempts,
        }
        
        if execution_context.tenant_id:
            metadata["tenant_id"] = execution_context.tenant_id
        if execution_context.application:
            metadata["application"] = execution_context.application
        if execution_context.environment:
            metadata["environment"] = execution_context.environment
        if execution_context.agent_purpose:
            metadata["agent_purpose"] = execution_context.agent_purpose
        
        # Build Decision object
        decision = Decision(
            action=action,
            reason_codes=reason_codes,
            risk_score=risk_score,
            mode=PolicyMode.ENFORCE,  # Circuit breaker always enforces
            policy_id="circuit.breaker",
            policy_version=self.component_versions.get("circuit", "1.1.0"),
            component_versions=self.component_versions,
            correlation_id=execution_context.correlation_id,
            reason=reason,
            metadata=metadata,
        )
        
        # Add optional fields only if defined
        if execution_context.trace_id:
            decision.trace_id = execution_context.trace_id
        if execution_context.workflow_id:
            decision.workflow_id = execution_context.workflow_id
        if execution_context.run_id:
            decision.run_id = execution_context.run_id
        if execution_context.span_id:
            decision.span_id = execution_context.span_id
        if execution_context.parent_span_id:
            decision.parent_span_id = execution_context.parent_span_id
        
        return decision
    
    def get_state(self) -> CircuitState:
        """Get current circuit state.
        
        Returns:
            Current CircuitState
        """
        return self.state
    
    def reset(self) -> None:
        """Reset the circuit to closed state."""
        self._transition_to(CircuitState.CLOSED)
        self.failures = 0
        self.last_failure_time = None
        self.half_open_attempts = 0
    
    def force_open(self) -> None:
        """Force the circuit to open state."""
        self._transition_to(CircuitState.OPEN)
    
    def force_close(self) -> None:
        """Force the circuit to closed state."""
        self._transition_to(CircuitState.CLOSED)
        self.failures = 0
        self.last_failure_time = None
        self.half_open_attempts = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit statistics.
        
        Returns:
            Dict with circuit stats
        """
        return {
            "state": self.state.value,
            "failures": self.failures,
            "last_failure_time": self.last_failure_time,
            "half_open_attempts": self.half_open_attempts,
        }
    
    def _on_success(self) -> None:
        """Handle successful execution."""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_attempts += 1
            
            if self.half_open_attempts >= self.half_open_requests:
                self._transition_to(CircuitState.CLOSED)
                self.failures = 0
                self.last_failure_time = None
                self.half_open_attempts = 0
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failures = 0
    
    def _on_failure(self) -> None:
        """Handle failed execution."""
        self.failures += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open state opens the circuit
            self.half_open_attempts = 0  # Reset half-open attempts
            self._transition_to(CircuitState.OPEN)
        elif self.state == CircuitState.CLOSED and self.failures >= self.failure_threshold:
            # Threshold reached, open the circuit
            self._transition_to(CircuitState.OPEN)
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset.
        
        Returns:
            True if should attempt reset, False otherwise
        """
        if not self.last_failure_time:
            return False
        
        elapsed_ms = (datetime.utcnow() - self.last_failure_time).total_seconds() * 1000
        return elapsed_ms >= self.timeout
    
    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state.
        
        Args:
            new_state: New CircuitState
        """
        old_state = self.state
        
        if old_state == new_state:
            return  # No transition needed
        
        self.state = new_state
        
        if new_state == CircuitState.HALF_OPEN:
            self.half_open_attempts = 0
        
        # Invoke callback
        self.on_state_change(new_state, old_state)
