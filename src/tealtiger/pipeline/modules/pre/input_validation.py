"""Multi-Stage Defense Pipeline — Input Validation Module (Python SDK).

Validates request structure against configurable rules: required fields,
type checks, and maximum token length. Returns DENY with reason code
INPUT_INVALID when any validation fails.

Module: pipeline/modules/pre/input_validation
Requirements: 6.2, 6.6, 6.7
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class InputValidationConfig:
    """Configuration object for InputValidationModule."""

    required_fields: List[str] = field(default_factory=list)
    """Fields that must be present (and non-None) in the request."""

    max_tokens: Optional[int] = None
    """Maximum token estimate. Checks content length using ~4 chars per token heuristic."""

    type_checks: Optional[Dict[str, str]] = None
    """Field name → expected Python type name (e.g., {'model': 'str', 'max_tokens': 'int'})."""


# ---------------------------------------------------------------------------
# Module Implementation
# ---------------------------------------------------------------------------


class InputValidationModule:
    """Validates request structure (required fields, type checks, max token length).

    Returns DENY with reason code INPUT_INVALID when any validation check fails.
    Returns ALLOW when all configured checks pass.

    Validation rules are composable — only configured checks are enforced:
    - ``required_fields``: Ensures specified fields exist and are not None.
    - ``type_checks``: Ensures specified fields match the expected Python type.
    - ``max_tokens``: Ensures the estimated token count does not exceed the limit.
    """

    name: str = "InputValidationModule"
    version: str = "1.0.0"

    def __init__(self, config: InputValidationConfig) -> None:
        self._config = config

    async def evaluate(
        self, request: Any, ctx: Any, policy: Any
    ) -> Dict[str, Any]:
        """Evaluate the request against configured validation rules.

        Args:
            request: The module evaluation request (dict-like).
            ctx: The module context.
            policy: The policy configuration (unused).

        Returns:
            A ModuleResult dict with action, reason_codes, event_type, metadata.
        """
        failures: List[str] = []

        if not isinstance(request, dict):
            failures.append("Request is not a dictionary")
            return self._deny_result(failures)

        # Check required fields
        if self._config.required_fields:
            for fld in self._config.required_fields:
                if request.get(fld) is None:
                    failures.append(f"Missing required field: {fld}")

        # Check type constraints
        if self._config.type_checks:
            type_map = {
                "str": str,
                "string": str,
                "int": int,
                "number": (int, float),
                "float": float,
                "bool": bool,
                "boolean": bool,
                "list": list,
                "dict": dict,
                "object": dict,
            }
            for fld, expected_type_name in self._config.type_checks.items():
                value = request.get(fld)
                if value is not None:
                    expected_type = type_map.get(expected_type_name.lower())
                    if expected_type and not isinstance(value, expected_type):
                        actual_type = type(value).__name__
                        failures.append(
                            f"Type mismatch for field '{fld}': "
                            f"expected {expected_type_name}, got {actual_type}"
                        )

        # Check max token length
        if self._config.max_tokens is not None:
            token_count = self._estimate_token_count(request)
            if token_count > self._config.max_tokens:
                failures.append(
                    f"Token limit exceeded: estimated {token_count} tokens "
                    f"> max {self._config.max_tokens}"
                )

        # Return result based on failures
        if failures:
            return self._deny_result(failures)

        return {
            "action": "ALLOW",
            "reason_codes": [],
            "event_type": "pipeline.input_validation",
            "metadata": {
                "module": self.name,
            },
        }

    def _deny_result(self, failures: List[str]) -> Dict[str, Any]:
        """Build a DENY result with validation failures."""
        return {
            "action": "DENY",
            "reason_codes": ["INPUT_INVALID"],
            "event_type": "pipeline.input_validation",
            "metadata": {
                "failures": failures,
                "failure_count": len(failures),
                "module": self.name,
            },
        }

    def _estimate_token_count(self, request: Dict[str, Any]) -> int:
        """Estimate token count from request.

        Priority: explicit max_tokens field → content length heuristic (~4 chars/token).
        """
        explicit_tokens = request.get("max_tokens") or request.get("maxTokens")
        if isinstance(explicit_tokens, (int, float)) and explicit_tokens > 0:
            return int(explicit_tokens)

        content = request.get("content") or ""
        return math.ceil(len(content) / 4)
