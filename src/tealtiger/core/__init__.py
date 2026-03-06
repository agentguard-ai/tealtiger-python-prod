"""Core components for TealTiger SDK v1.1.x Enterprise Adoption Features."""

from tealtiger.core.audit import (
    AUDIT_SCHEMA_VERSION,
    AuditConfig,
    AuditEvent,
    AuditEventType,
    AuditOutput,
    ConsoleOutput,
    CustomOutput,
    RedactionLevel,
    TealAudit,
    TealAuditConfig,
)
from tealtiger.core.circuit import CircuitOpenError, CircuitState, TealCircuit
from tealtiger.core.context.context_manager import ContextManager
from tealtiger.core.context.execution_context import ExecutionContext
from tealtiger.core.engine.teal_engine import TealEngine
from tealtiger.core.engine.types import (
    Decision,
    DecisionAction,
    ModeConfig,
    PolicyMode,
    ReasonCode,
)
from tealtiger.core.guard import GuardrailResult, TealGuard

__all__ = [
    # Engine
    "TealEngine",
    "PolicyMode",
    "ModeConfig",
    "DecisionAction",
    "ReasonCode",
    "Decision",
    # Context
    "ExecutionContext",
    "ContextManager",
    # Guard
    "TealGuard",
    "GuardrailResult",
    # Circuit
    "TealCircuit",
    "CircuitState",
    "CircuitOpenError",
    # Audit
    "TealAudit",
    "TealAuditConfig",
    "AuditConfig",
    "AuditEvent",
    "AuditEventType",
    "AuditOutput",
    "ConsoleOutput",
    "CustomOutput",
    "RedactionLevel",
    "AUDIT_SCHEMA_VERSION",
]
