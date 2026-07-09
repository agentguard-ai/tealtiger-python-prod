"""
CostAccumulator — tracks per-request, per-session, and per-agent cost.

Python port of the TypeScript cost-accumulator.ts.
Maintains in-memory running totals that are monotonically non-decreasing.
Thread-safety is NOT required (single-threaded per proxy).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .types import CostBreakdownSummary, ObserveCostSummary, RequestCostResult


# ---------------------------------------------------------------------------
# Pricing table — per-1K-token rates (USD)
# ---------------------------------------------------------------------------

DEFAULT_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "claude-3-opus": {"input": 0.015, "output": 0.075},
    "claude-3-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
    "gemini-2.0-flash": {"input": 0.0001, "output": 0.0004},
    "gemini-2.5-pro": {"input": 0.00125, "output": 0.01},
    "mistral-large": {"input": 0.002, "output": 0.006},
    "command-r-plus": {"input": 0.003, "output": 0.015},
}


def _get_model_pricing(model: str) -> Tuple[float, float]:
    """
    Look up per-1K-token pricing for a model.

    Resolution order:
      1. Exact match in DEFAULT_PRICING
      2. Prefix match (model starts with a known key)
      3. Default fallback (0.001 input, 0.002 output)

    Args:
        model: The model identifier string.

    Returns:
        Tuple of (input_rate, output_rate) per 1K tokens.
    """
    # Exact match
    if model in DEFAULT_PRICING:
        entry = DEFAULT_PRICING[model]
        return entry["input"], entry["output"]

    # Prefix match
    for key, entry in DEFAULT_PRICING.items():
        if model.startswith(key):
            return entry["input"], entry["output"]

    # Default fallback
    return 0.001, 0.002


class CostAccumulator:
    """
    Tracks per-request, per-session, and per-agent cost.

    Wraps a simplified pricing engine and maintains in-memory running totals
    that are monotonically non-decreasing.
    """

    def __init__(self) -> None:
        """Initialize empty cost tracking dictionaries."""
        self._session_costs: Dict[str, ObserveCostSummary] = {}
        self._agent_costs: Dict[str, ObserveCostSummary] = {}

    def record_cost(
        self,
        agent_id: str,
        session_id: str,
        request_id: str,
        model: str,
        provider: str,
        usage: Optional[Any],
    ) -> RequestCostResult:
        """
        Record cost for a completed request.

        Args:
            agent_id: The agent identifier.
            session_id: The session identifier.
            request_id: Unique identifier for this request.
            model: Model name used for pricing lookup.
            provider: Provider name (unused for pricing, retained for API parity).
            usage: Object with ``input_tokens`` and ``output_tokens`` attributes,
                   or None if usage data is unavailable.

        Returns:
            RequestCostResult with the computed cost breakdown for this request.
        """
        if usage is None:
            # No usage data — record zero cost with pricing_unavailable flag
            self._increment_totals(
                agent_id, session_id, input_cost=0.0, output_cost=0.0, pricing_unavailable=True
            )
            return RequestCostResult(
                request_id=request_id,
                cost=0.0,
                pricing_unavailable=True,
                breakdown=CostBreakdownSummary(input_cost=0.0, output_cost=0.0),
            )

        # Extract token counts via duck-typing (getattr)
        input_tokens: int = getattr(usage, "input_tokens", 0)
        output_tokens: int = getattr(usage, "output_tokens", 0)

        # Look up pricing
        input_rate, output_rate = _get_model_pricing(model)

        # Compute costs
        input_cost = (input_tokens / 1000) * input_rate
        output_cost = (output_tokens / 1000) * output_rate
        total_cost = input_cost + output_cost

        self._increment_totals(
            agent_id, session_id, input_cost=input_cost, output_cost=output_cost, pricing_unavailable=False
        )

        return RequestCostResult(
            request_id=request_id,
            cost=total_cost,
            pricing_unavailable=False,
            breakdown=CostBreakdownSummary(input_cost=input_cost, output_cost=output_cost),
        )

    def get_session_cost(self, session_id: str) -> ObserveCostSummary:
        """
        Get cumulative cost for a session (monotonically non-decreasing).

        Args:
            session_id: The session identifier to look up.

        Returns:
            ObserveCostSummary with accumulated totals, or a zeroed summary
            if no requests have been recorded for this session.
        """
        return self._session_costs.get(session_id, self._empty_summary())

    def get_agent_cost(self, agent_id: str) -> ObserveCostSummary:
        """
        Get cumulative cost for an agent (persists across sessions).

        Args:
            agent_id: The agent identifier to look up.

        Returns:
            ObserveCostSummary with accumulated totals, or a zeroed summary
            if no requests have been recorded for this agent.
        """
        return self._agent_costs.get(agent_id, self._empty_summary())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _increment_totals(
        self,
        agent_id: str,
        session_id: str,
        input_cost: float,
        output_cost: float,
        pricing_unavailable: bool,
    ) -> None:
        """Increment both session and agent running totals."""
        total_cost = input_cost + output_cost

        # Update session total
        if session_id not in self._session_costs:
            self._session_costs[session_id] = self._empty_summary()
        session = self._session_costs[session_id]
        session.total_cost += total_cost
        session.request_count += 1
        if pricing_unavailable:
            session.has_pricing_gaps = True
        session.breakdown.input_cost += input_cost
        session.breakdown.output_cost += output_cost

        # Update agent total
        if agent_id not in self._agent_costs:
            self._agent_costs[agent_id] = self._empty_summary()
        agent = self._agent_costs[agent_id]
        agent.total_cost += total_cost
        agent.request_count += 1
        if pricing_unavailable:
            agent.has_pricing_gaps = True
        agent.breakdown.input_cost += input_cost
        agent.breakdown.output_cost += output_cost

    @staticmethod
    def _empty_summary() -> ObserveCostSummary:
        """Create a zeroed ObserveCostSummary."""
        return ObserveCostSummary(
            total_cost=0.0,
            request_count=0,
            has_pricing_gaps=False,
            breakdown=CostBreakdownSummary(),
        )
