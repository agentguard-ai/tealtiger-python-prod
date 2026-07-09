"""TEEC v2.1 Governance Contract — Public API (Python SDK).

This package provides the TEEC v2.1 governance contract types for
cryptographic verifiability and tamper-evidence in TealTiger v1.4.

Usage:
    from tealtiger.core.engine.v2_1 import (
        # Types
        DecisionV21,
        GovernanceSeal,
        GENESIS_RECEIPT_REF,
        ValidationContext,
        ValidationSuccess,
        ValidationFailure,
        ContiguitySuccess,
        ContiguityFailure,
        # Errors
        SealConfigurationError,
        # Services
        CryptoService,
        CounterManager,
        # Engine
        GovernanceEngineV21,
        GovernanceEngineV21Options,
        # Validation functions
        validate_governance_decision,
        verify_contiguity,
    )
"""

from .types import (
    GENESIS_RECEIPT_REF,
    ContiguityFailure,
    ContiguitySuccess,
    DecisionV21,
    GovernanceSeal,
    ValidationContext,
    ValidationFailure,
    ValidationSuccess,
)
from .errors import SealConfigurationError
from .crypto_service import CryptoService
from .counter_manager import CounterManager
from .governance_engine import GovernanceEngineV21, GovernanceEngineV21Options
from .validate_governance_decision import validate_governance_decision
from .verify_contiguity import verify_contiguity

__all__ = [
    # Types
    "DecisionV21",
    "GovernanceSeal",
    # Constants
    "GENESIS_RECEIPT_REF",
    # Validation result types
    "ValidationContext",
    "ValidationSuccess",
    "ValidationFailure",
    "ContiguitySuccess",
    "ContiguityFailure",
    # Errors
    "SealConfigurationError",
    # Services
    "CryptoService",
    "CounterManager",
    # Engine
    "GovernanceEngineV21",
    "GovernanceEngineV21Options",
    # Validation functions
    "validate_governance_decision",
    "verify_contiguity",
]
