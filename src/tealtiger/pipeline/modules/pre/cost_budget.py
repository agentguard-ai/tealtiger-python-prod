"""Multi-Stage Defense Pipeline — Cost Budget Module (Python SDK).

Checks the estimated cost of a request against session, agent, and daily budgets.
Returns DENY with reason code BUDGET_EXCEEDED when any budget would be exceeded.
Tracks accumulated costs internally and exposes ``add_cost()`` for external integration.

Module: pipeline/modules/pre/cost_budget
Requirements: 6.4, 6.6, 6.7
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class CostBudgetConfig:
    """Configuration object for CostBudgetModule."""

    session_budget: Optional[float] = None
    """Maximum USD spend allowed per session."""

    daily_budget: Optional[float] = None
    """Maximum USD spend allowed per day."""

    agent_budget: Optional[float] = None
    """Maximum USD spend allowed per agent."""

    cost_per_token: float = 0.00003
    """Estimated cost per token in USD."""


# ---------------------------------------------------------------------------
# Module Implementation
# ---------------------------------------------------------------------------


class CostBudgetModule:
    """Checks the estimated cost of a request against configured budgets.

    Returns DENY with reason code BUDGET_EXCEEDED when any budget would be
    exceeded. Returns ALLOW when within all budgets.

    Cost estimation uses a configurable cost_per_token rate applied to the
    token count derived from request content length (~4 chars per token
    heuristic) or explicit token fields in the request.

    Tracks accumulated session and daily costs internally. Call ``add_cost()``
    after a successful LLM response to keep the internal state accurate for
    subsequent budget checks.
    """

    name: str = "CostBudgetModule"
    version: str = "1.0.0"

    def __init__(self, config: CostBudgetConfig) -> None:
        self._config = config
        self._cost_per_token = config.cost_per_token

        self._session_spent: float = 0.0
        self._daily_spent: float = 0.0
        self._agent_spent: float = 0.0
        self._daily_reset_timestamp: float = self._get_day_start(time.time() * 1000)

    async def evaluate(
        self, request: Any, ctx: Any, policy: Any
    ) -> Dict[str, Any]:
        """Evaluate the request cost against configured budgets.

        Args:
            request: The module evaluation request (dict-like).
            ctx: The module context.
            policy: The policy configuration (unused).

        Returns:
            A ModuleResult dict with action, reason_codes, event_type, metadata.
        """
        # Reset daily budget if we've crossed into a new day
        self._check_daily_reset()

        estimated_cost = self._estimate_cost(request)
        exceeded_budgets: list[str] = []

        # Check session budget
        if (
            self._config.session_budget is not None
            and self._session_spent + estimated_cost > self._config.session_budget
        ):
            exceeded_budgets.append(
                f"session: ${self._session_spent + estimated_cost:.6f} "
                f"> ${self._config.session_budget:.6f}"
            )

        # Check daily budget
        if (
            self._config.daily_budget is not None
            and self._daily_spent + estimated_cost > self._config.daily_budget
        ):
            exceeded_budgets.append(
                f"daily: ${self._daily_spent + estimated_cost:.6f} "
                f"> ${self._config.daily_budget:.6f}"
            )

        # Check agent budget
        if (
            self._config.agent_budget is not None
            and self._agent_spent + estimated_cost > self._config.agent_budget
        ):
            exceeded_budgets.append(
                f"agent: ${self._agent_spent + estimated_cost:.6f} "
                f"> ${self._config.agent_budget:.6f}"
            )

        if exceeded_budgets:
            return {
                "action": "DENY",
                "reason_codes": ["BUDGET_EXCEEDED"],
                "event_type": "pipeline.cost_budget",
                "metadata": {
                    "module": self.name,
                    "estimated_cost": estimated_cost,
                    "session_spent": self._session_spent,
                    "daily_spent": self._daily_spent,
                    "agent_spent": self._agent_spent,
                    "exceeded_budgets": exceeded_budgets,
                },
            }

        return {
            "action": "ALLOW",
            "reason_codes": [],
            "event_type": "pipeline.cost_budget",
            "metadata": {
                "module": self.name,
                "estimated_cost": estimated_cost,
                "session_spent": self._session_spent,
                "daily_spent": self._daily_spent,
                "agent_spent": self._agent_spent,
            },
        }

    def add_cost(self, amount: float) -> None:
        """Add an actual cost amount to the internal tracking.

        Call this after a successful LLM response to keep budget state accurate.

        Args:
            amount: Cost in USD to add to all budget trackers.
        """
        self._check_daily_reset()
        self._session_spent += amount
        self._daily_spent += amount
        self._agent_spent += amount

    def get_spent(self) -> Dict[str, float]:
        """Get current accumulated costs for inspection/testing."""
        return {
            "session": self._session_spent,
            "daily": self._daily_spent,
            "agent": self._agent_spent,
        }

    def reset_session(self) -> None:
        """Reset accumulated session costs."""
        self._session_spent = 0.0

    def _estimate_cost(self, request: Any) -> float:
        """Estimate cost from the request's token count."""
        token_count = self._estimate_token_count(request)
        return token_count * self._cost_per_token

    def _estimate_token_count(self, request: Any) -> int:
        """Estimate token count from request.

        Priority: explicit max_tokens field → content length heuristic (~4 chars/token).
        """
        if isinstance(request, dict):
            max_tokens = request.get("max_tokens") or request.get("maxTokens")
            if isinstance(max_tokens, (int, float)) and max_tokens > 0:
                return int(max_tokens)

            content = request.get("content") or ""
            return math.ceil(len(content) / 4)

        return 0

    def _check_daily_reset(self) -> None:
        """Check if a new day has started and reset daily budget if so."""
        current_day_start = self._get_day_start(time.time() * 1000)
        if current_day_start > self._daily_reset_timestamp:
            self._daily_spent = 0.0
            self._daily_reset_timestamp = current_day_start

    @staticmethod
    def _get_day_start(timestamp_ms: float) -> float:
        """Get the Unix timestamp (ms) for midnight UTC of the day containing timestamp."""
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight.timestamp() * 1000
