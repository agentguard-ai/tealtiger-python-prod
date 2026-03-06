"""TealGuard module for enhanced guardrails with Decision contract.

TealTiger SDK v1.1.x - Enterprise Adoption Features
"""

from .teal_guard import TealGuard
from .types import GuardrailResult

__all__ = [
    "TealGuard",
    "GuardrailResult",
]
