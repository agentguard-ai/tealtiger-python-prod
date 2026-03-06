"""TealCircuit module for circuit breaker with Decision contract.

TealTiger SDK v1.1.x - Enterprise Adoption Features
"""

from .teal_circuit import CircuitOpenError, CircuitState, TealCircuit

__all__ = [
    "TealCircuit",
    "CircuitState",
    "CircuitOpenError",
]
