"""Multi-Stage Defense Pipeline — Policy Evaluation Module (Python SDK).

Evaluates requests against a configurable policy (blocked models, blocked topics,
token limits) and returns DENY with reason code POLICY_VIOLATION when any policy
rule is violated.

Module: pipeline/modules/pre/policy_evaluation
Requirements: 6.1, 6.6, 6.7
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class PolicyRules:
    """Policy rules that govern what requests are permitted."""

    blocked_models: List[str] = field(default_factory=list)
    """Model identifiers that are not allowed. Matched case-insensitively."""

    blocked_topics: List[str] = field(default_factory=list)
    """Topic keywords that are not allowed in request content. Matched case-insensitively."""

    max_tokens: Optional[int] = None
    """Maximum token count allowed in a request."""


@dataclass
class PolicyEvaluationConfig:
    """Configuration object for PolicyEvaluationModule."""

    policy: PolicyRules


# ---------------------------------------------------------------------------
# Module Implementation
# ---------------------------------------------------------------------------


class PolicyEvaluationModule:
    """Evaluates a request against a TealEngine policy configuration.

    Returns DENY with reason code POLICY_VIOLATION when any policy rule is violated.
    Returns ALLOW when all rules pass.

    Supported policy rules:
    - ``blocked_models``: Denies requests targeting a blocked model.
    - ``blocked_topics``: Denies requests containing blocked topic keywords in content.
    - ``max_tokens``: Denies requests exceeding the configured token limit.
    """

    name: str = "PolicyEvaluationModule"
    version: str = "1.0.0"

    def __init__(self, config: PolicyEvaluationConfig) -> None:
        self._policy = config.policy

    async def evaluate(
        self, request: Any, ctx: Any, policy: Any
    ) -> Dict[str, Any]:
        """Evaluate the request against configured policy rules.

        Args:
            request: The module evaluation request (dict-like).
            ctx: The module context.
            policy: The policy configuration (unused, rules are in config).

        Returns:
            A ModuleResult dict with action, reason_codes, event_type, metadata.
        """
        violations: List[str] = []

        # Check blocked models
        if self._policy.blocked_models:
            request_model = (request.get("model") or "").lower() if isinstance(request, dict) else ""
            if request_model:
                for blocked in self._policy.blocked_models:
                    if blocked.lower() == request_model:
                        violations.append(f"Blocked model: {blocked}")
                        break

        # Check blocked topics
        if self._policy.blocked_topics:
            content = (request.get("content") or "").lower() if isinstance(request, dict) else ""
            if content:
                for topic in self._policy.blocked_topics:
                    if topic.lower() in content:
                        violations.append(f"Blocked topic: {topic}")

        # Check max tokens
        if self._policy.max_tokens is not None:
            token_count = self._estimate_token_count(request)
            if token_count > self._policy.max_tokens:
                violations.append(
                    f"Token limit exceeded: {token_count} > {self._policy.max_tokens}"
                )

        # Return result based on violations
        if violations:
            return {
                "action": "DENY",
                "reason_codes": ["POLICY_VIOLATION"],
                "event_type": "pipeline.policy_evaluation",
                "metadata": {
                    "violations": violations,
                    "module": self.name,
                },
            }

        return {
            "action": "ALLOW",
            "reason_codes": [],
            "event_type": "pipeline.policy_evaluation",
            "metadata": {
                "module": self.name,
            },
        }

    def _estimate_token_count(self, request: Any) -> int:
        """Estimate the token count from a request.

        Uses the ``max_tokens`` field from the payload if present,
        otherwise estimates based on content length (~4 chars per token).
        """
        if isinstance(request, dict):
            max_tokens = request.get("max_tokens") or request.get("maxTokens")
            if isinstance(max_tokens, (int, float)):
                return int(max_tokens)

            content = request.get("content") or ""
            return math.ceil(len(content) / 4)

        return 0
