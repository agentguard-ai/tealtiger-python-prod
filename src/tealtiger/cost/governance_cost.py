"""Governance-Owned Cost Limits & Anomaly Detection — TealMonitor v2 (Python SDK).

Port of the TypeScript governance cost modules to Python with identical semantics:
- GovernanceCostEnforcer: Enforces governance-owned budget limits
- CostAnomalyDetector: Detects cost anomalies using rolling baselines

Module: cost/governance_cost
Requirements: 17.1–17.13
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ══════════════════════════════════════════════════════════════════
# GovernanceCostEnforcer — Budget Enforcement
# ══════════════════════════════════════════════════════════════════


@dataclass
class GovernanceCostLimits:
    """Governance-owned cost limits (from bundle, overrides app config)."""

    per_request_max: float = 0.0
    per_session_max: float = 0.0
    per_daily_max: float = 0.0
    per_agent_max: float = 0.0
    reasoning_token_budget: Optional[int] = None


@dataclass
class CostGovernanceConfig:
    """Configuration for governance cost enforcement."""

    governance_limits: Optional[GovernanceCostLimits] = None


@dataclass
class _CostAccumulator:
    """Internal tracking record for cumulative costs."""

    total: float = 0.0
    last_reset: float = 0.0


class GovernanceCostEnforcer:
    """GovernanceCostEnforcer — Enforces governance-owned cost limits.

    Governance limits are defined in policy bundles and take absolute precedence
    over any application-configured limits. The enforcer tracks cumulative costs
    per agent, per session, and per day, and denies requests that would exceed
    governance ceilings.

    Evaluates limits in order:
    1. Per-request max
    2. Reasoning token budget
    3. Per-session max
    4. Per-daily max
    5. Per-agent max
    """

    def __init__(self, config: CostGovernanceConfig) -> None:
        self.config = config
        self._agent_costs: Dict[str, _CostAccumulator] = {}
        self._session_costs: Dict[str, _CostAccumulator] = {}
        self._daily_costs: Dict[str, _CostAccumulator] = {}
        self._reasoning_tokens: Dict[str, int] = {}

    def check_budget(
        self,
        agent_id: str,
        estimated_cost: float,
        session_id: Optional[str] = None,
        reasoning_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Check whether a request is within governance budget limits.

        Returns dict with 'allowed', optional 'reason_code', and 'remaining_budget'.
        """
        limits = self.config.governance_limits

        # If no governance limits configured, allow everything
        if limits is None:
            return {"allowed": True, "remaining_budget": float("inf")}

        # 1. Per-request max
        if estimated_cost > limits.per_request_max:
            return {
                "allowed": False,
                "reason_code": "COST_BUDGET_EXCEEDED",
                "remaining_budget": limits.per_request_max,
            }

        # 2. Reasoning token budget
        if (
            limits.reasoning_token_budget is not None
            and reasoning_tokens is not None
        ):
            key = session_id or agent_id
            consumed = self._reasoning_tokens.get(key, 0)
            if consumed + reasoning_tokens > limits.reasoning_token_budget:
                return {
                    "allowed": False,
                    "reason_code": "REASONING_TOKEN_BUDGET_EXCEEDED",
                    "remaining_budget": max(
                        0, limits.reasoning_token_budget - consumed
                    ),
                }

        # 3. Per-session max
        if session_id:
            session_accum = self._session_costs.get(session_id)
            session_total = session_accum.total if session_accum else 0.0
            if session_total + estimated_cost > limits.per_session_max:
                return {
                    "allowed": False,
                    "reason_code": "COST_BUDGET_EXCEEDED",
                    "remaining_budget": max(
                        0.0, limits.per_session_max - session_total
                    ),
                }

        # 4. Per-daily max
        today = self._get_today_key()
        daily_accum = self._daily_costs.get(today)
        daily_total = daily_accum.total if daily_accum else 0.0
        if daily_total + estimated_cost > limits.per_daily_max:
            return {
                "allowed": False,
                "reason_code": "COST_BUDGET_EXCEEDED",
                "remaining_budget": max(0.0, limits.per_daily_max - daily_total),
            }

        # 5. Per-agent max
        agent_accum = self._agent_costs.get(agent_id)
        agent_total = agent_accum.total if agent_accum else 0.0
        if agent_total + estimated_cost > limits.per_agent_max:
            return {
                "allowed": False,
                "reason_code": "COST_BUDGET_EXCEEDED",
                "remaining_budget": max(0.0, limits.per_agent_max - agent_total),
            }

        # Calculate the most restrictive remaining budget
        remaining_budgets = [
            limits.per_request_max - estimated_cost,
            limits.per_daily_max - daily_total - estimated_cost,
            limits.per_agent_max - agent_total - estimated_cost,
        ]

        if session_id:
            session_accum = self._session_costs.get(session_id)
            session_total = session_accum.total if session_accum else 0.0
            remaining_budgets.append(
                limits.per_session_max - session_total - estimated_cost
            )

        remaining_budget = max(0.0, min(remaining_budgets))

        return {"allowed": True, "remaining_budget": remaining_budget}

    def record_cost(
        self,
        agent_id: str,
        cost: float,
        session_id: Optional[str] = None,
        reasoning_tokens: Optional[int] = None,
    ) -> None:
        """Record a cost after a request has been allowed and executed."""
        now = time.time()

        # Update agent cost
        if agent_id not in self._agent_costs:
            self._agent_costs[agent_id] = _CostAccumulator(last_reset=now)
        self._agent_costs[agent_id].total += cost

        # Update session cost
        if session_id:
            if session_id not in self._session_costs:
                self._session_costs[session_id] = _CostAccumulator(last_reset=now)
            self._session_costs[session_id].total += cost

        # Update daily cost
        today = self._get_today_key()
        if today not in self._daily_costs:
            self._daily_costs[today] = _CostAccumulator(last_reset=now)
        self._daily_costs[today].total += cost

        # Update reasoning tokens
        if reasoning_tokens is not None:
            key = session_id or agent_id
            self._reasoning_tokens[key] = (
                self._reasoning_tokens.get(key, 0) + reasoning_tokens
            )

    def get_agent_cost(self, agent_id: str) -> float:
        """Get the current cumulative cost for an agent."""
        accum = self._agent_costs.get(agent_id)
        return accum.total if accum else 0.0

    def get_session_cost(self, session_id: str) -> float:
        """Get the current cumulative cost for a session."""
        accum = self._session_costs.get(session_id)
        return accum.total if accum else 0.0

    def get_daily_cost(self) -> float:
        """Get the current daily cumulative cost."""
        today = self._get_today_key()
        accum = self._daily_costs.get(today)
        return accum.total if accum else 0.0

    def reset(self) -> None:
        """Reset all tracked costs."""
        self._agent_costs.clear()
        self._session_costs.clear()
        self._daily_costs.clear()
        self._reasoning_tokens.clear()

    def _get_today_key(self) -> str:
        now = datetime.now(tz=timezone.utc)
        return f"{now.year}-{now.month:02d}-{now.day:02d}"


# ══════════════════════════════════════════════════════════════════
# CostAnomalyDetector — Anomaly Detection
# ══════════════════════════════════════════════════════════════════


@dataclass
class AnomalyDetectorConfig:
    """Configuration for the anomaly detector."""

    baseline_window: int = 100
    """Number of requests in the rolling baseline window."""

    spike_multiplier: float = 10.0
    """Multiplier above baseline that triggers anomaly."""

    growth_rate_threshold: float = 0.5
    """Session cost growth rate threshold (fraction, e.g. 0.5 = 50% growth)."""


@dataclass
class _RollingWindow:
    """Internal rolling window for tracking cost history."""

    values: List[float] = field(default_factory=list)
    total: float = 0.0


class CostAnomalyDetector:
    """CostAnomalyDetector — Detects cost anomalies using rolling baselines.

    Maintains a per-agent/provider rolling window of request costs and flags
    requests that significantly exceed the established baseline.

    Emits:
    - COST_ANOMALY_DETECTED: single request cost exceeds spike_multiplier × baseline
    - COST_SPIKE_DETECTED: session cost growth rate exceeds threshold
    """

    def __init__(self, config: AnomalyDetectorConfig) -> None:
        self.config = config
        self._baselines: Dict[str, _RollingWindow] = {}
        self._previous_session_costs: Dict[str, float] = {}

    def check_anomaly(
        self,
        agent_id: str,
        provider: str,
        cost: float,
        session_cost_total: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Check whether a request cost is anomalous relative to the rolling baseline.

        Detection logic:
        1. If rolling baseline has data and cost > spike_multiplier × mean → COST_ANOMALY_DETECTED
        2. If session_cost_total growth rate > threshold → COST_SPIKE_DETECTED

        Returns dict with 'anomaly', optional 'alert_type' and 'reason_code'.
        """
        key = f"{agent_id}:{provider}"
        window = self._get_or_create_window(key)

        # Check for single-request anomaly against baseline
        if window.values:
            baseline_mean = window.total / len(window.values)
            if (
                baseline_mean > 0
                and cost > baseline_mean * self.config.spike_multiplier
            ):
                self._add_to_window(key, cost)
                self._update_session_cost(key, session_cost_total)
                return {
                    "anomaly": True,
                    "alert_type": "single_request_anomaly",
                    "reason_code": "COST_ANOMALY_DETECTED",
                }

        # Check for session cost spike (growth rate)
        if session_cost_total is not None:
            previous_total = self._previous_session_costs.get(key)
            if previous_total is not None and previous_total > 0:
                growth_rate = (session_cost_total - previous_total) / previous_total
                if growth_rate > self.config.growth_rate_threshold:
                    self._add_to_window(key, cost)
                    self._update_session_cost(key, session_cost_total)
                    return {
                        "anomaly": True,
                        "alert_type": "session_cost_spike",
                        "reason_code": "COST_SPIKE_DETECTED",
                    }
            self._update_session_cost(key, session_cost_total)

        # No anomaly — add cost to baseline window
        self._add_to_window(key, cost)

        return {"anomaly": False}

    def get_baseline_mean(self, agent_id: str, provider: str) -> Optional[float]:
        """Get the current baseline mean for an agent/provider combination."""
        key = f"{agent_id}:{provider}"
        window = self._baselines.get(key)
        if not window or not window.values:
            return None
        return window.total / len(window.values)

    def get_baseline_size(self, agent_id: str, provider: str) -> int:
        """Get the number of samples in the baseline for an agent/provider."""
        key = f"{agent_id}:{provider}"
        window = self._baselines.get(key)
        return len(window.values) if window else 0

    def reset(self) -> None:
        """Reset all baselines and session tracking."""
        self._baselines.clear()
        self._previous_session_costs.clear()

    def _get_or_create_window(self, key: str) -> _RollingWindow:
        if key not in self._baselines:
            self._baselines[key] = _RollingWindow()
        return self._baselines[key]

    def _add_to_window(self, key: str, cost: float) -> None:
        window = self._get_or_create_window(key)
        window.values.append(cost)
        window.total += cost

        # Evict oldest entries if window exceeds configured size
        while len(window.values) > self.config.baseline_window:
            evicted = window.values.pop(0)
            window.total -= evicted

    def _update_session_cost(
        self, key: str, session_cost_total: Optional[float]
    ) -> None:
        if session_cost_total is not None:
            self._previous_session_costs[key] = session_cost_total
