"""Tests for TealDrift, TealState, TealTemporal, and Cost Governance modules.

Covers:
- TealDrift: baseline tracking, drift detection, min_samples guard
- TealState: context size enforcement (deny/truncate/alert), mutation governance
- TealTemporal: session TTL, cooldown enforcement, time restrictions
- Cost: per-request/session/daily budget, anomaly detection, spike detection

Requirements: 12.1
"""

import time

import pytest

from tealtiger.modules.governance_modules import (
    TealDriftModule,
    TealStateModule,
    TealTemporalModule,
    DriftConfig,
    DriftObservation,
    StateConfig,
    ContextEntry,
    TemporalConfig,
    CooldownRule,
    TimeRestriction,
)
from tealtiger.cost.governance_cost import (
    GovernanceCostEnforcer,
    CostAnomalyDetector,
    CostGovernanceConfig,
    GovernanceCostLimits,
    AnomalyDetectorConfig,
)


# ══════════════════════════════════════════════════════════════════
# TealDrift Tests
# ══════════════════════════════════════════════════════════════════


class TestTealDriftBaseline:
    """TealDrift baseline tracking with Welford's algorithm."""

    def test_update_baseline_increments_sample_count(self):
        drift = TealDriftModule(DriftConfig(min_samples=5))
        obs = DriftObservation(
            agent_id="a1", provider="openai", model="gpt-4",
            refusal=False, response_length=100, topics=["code"]
        )
        drift.update_baseline(obs)
        baseline = drift.get_baseline("a1", "openai", "gpt-4")
        assert baseline is not None
        assert baseline.sample_count == 1

    def test_update_baseline_tracks_mean(self):
        drift = TealDriftModule(DriftConfig(min_samples=2))
        for length in [100, 200, 300]:
            drift.update_baseline(DriftObservation(
                agent_id="a1", provider="openai", model="gpt-4",
                response_length=length, topics=[]
            ))
        baseline = drift.get_baseline("a1", "openai", "gpt-4")
        assert baseline is not None
        assert abs(baseline.response_length.mean - 200.0) < 0.01

    def test_update_baseline_tracks_topics(self):
        drift = TealDriftModule()
        drift.update_baseline(DriftObservation(
            agent_id="a1", provider="openai", model="gpt-4",
            topics=["code", "math"]
        ))
        drift.update_baseline(DriftObservation(
            agent_id="a1", provider="openai", model="gpt-4",
            topics=["code"]
        ))
        baseline = drift.get_baseline("a1", "openai", "gpt-4")
        assert baseline is not None
        assert baseline.topic_distribution["code"] == 2
        assert baseline.topic_distribution["math"] == 1


class TestTealDriftDetection:
    """TealDrift drift detection logic."""

    def test_no_drift_when_below_min_samples(self):
        drift = TealDriftModule(DriftConfig(min_samples=50, threshold_sigma=3))
        # Add only 10 samples
        for _ in range(10):
            drift.update_baseline(DriftObservation(
                agent_id="a1", provider="openai", model="gpt-4",
                response_length=100, topics=["code"]
            ))
        # Check drift — should return None (insufficient samples)
        result = drift.check_drift(DriftObservation(
            agent_id="a1", provider="openai", model="gpt-4",
            response_length=10000, topics=["code"]
        ))
        assert result is None

    def test_no_drift_when_no_baseline(self):
        drift = TealDriftModule()
        result = drift.check_drift(DriftObservation(
            agent_id="unknown", provider="openai", model="gpt-4",
            response_length=100
        ))
        assert result is None

    def test_detects_response_length_drift(self):
        drift = TealDriftModule(DriftConfig(min_samples=10, threshold_sigma=2))
        # Build baseline with some variance around 100 (need non-zero variance)
        for i in range(20):
            drift.update_baseline(DriftObservation(
                agent_id="a1", provider="openai", model="gpt-4",
                response_length=95 + (i % 10), topics=["code"]
            ))
        # Extreme deviation (far beyond 2 sigma)
        result = drift.check_drift(DriftObservation(
            agent_id="a1", provider="openai", model="gpt-4",
            response_length=100000, topics=["code"]
        ))
        assert result is not None
        assert result["drifted"] is True
        assert result["metric"] == "response_length"

    def test_detects_topic_drift(self):
        drift = TealDriftModule(DriftConfig(min_samples=10, threshold_sigma=2))
        # Build baseline with known topics
        for _ in range(50):
            drift.update_baseline(DriftObservation(
                agent_id="a1", provider="openai", model="gpt-4",
                response_length=100, topics=["code", "math"]
            ))
        # All unseen topics
        result = drift.check_drift(DriftObservation(
            agent_id="a1", provider="openai", model="gpt-4",
            response_length=100, topics=["weapons", "hacking"]
        ))
        assert result is not None
        assert result["drifted"] is True
        assert result["metric"] == "topic_distribution"

    def test_no_drift_within_normal_range(self):
        drift = TealDriftModule(DriftConfig(min_samples=10, threshold_sigma=3))
        # Build baseline with some variance
        for i in range(20):
            drift.update_baseline(DriftObservation(
                agent_id="a1", provider="openai", model="gpt-4",
                response_length=90 + (i % 20), topics=["code"]
            ))
        # Within normal range
        result = drift.check_drift(DriftObservation(
            agent_id="a1", provider="openai", model="gpt-4",
            response_length=105, topics=["code"]
        ))
        assert result is None



# ══════════════════════════════════════════════════════════════════
# TealState Tests
# ══════════════════════════════════════════════════════════════════


class TestTealStateContextEnforcement:
    """TealState context size enforcement."""

    def test_add_context_within_limit(self):
        state = TealStateModule(StateConfig(max_context_size=1000, on_exceed="deny"))
        result = state.add_context("agent-1", ContextEntry(
            content="hello world", source="user"
        ))
        assert result["allowed"] is True
        assert state.get_context_size("agent-1") == len("hello world".encode("utf-8"))

    def test_deny_when_exceeds_limit(self):
        state = TealStateModule(StateConfig(max_context_size=10, on_exceed="deny"))
        result = state.add_context("agent-1", ContextEntry(
            content="this is way too long for the limit", source="user"
        ))
        assert result["allowed"] is False
        assert result["reason_code"] == "CONTEXT_SIZE_EXCEEDED"
        # Context should not have been added
        assert state.get_context_size("agent-1") == 0

    def test_truncate_removes_oldest_entries(self):
        state = TealStateModule(StateConfig(max_context_size=20, on_exceed="truncate"))
        # Add first entry (11 bytes)
        state.add_context("agent-1", ContextEntry(content="hello world", source="s1"))
        # Add second entry that would exceed — should truncate oldest
        result = state.add_context("agent-1", ContextEntry(
            content="second entry", source="s2"
        ))
        assert result["allowed"] is True
        entries = state.get_context("agent-1")
        # Only the second entry should remain (oldest was truncated)
        assert len(entries) == 1
        assert entries[0].content == "second entry"

    def test_alert_allows_but_emits_event(self):
        state = TealStateModule(StateConfig(max_context_size=5, on_exceed="alert"))
        result = state.add_context("agent-1", ContextEntry(
            content="exceeds limit", source="user"
        ))
        assert result["allowed"] is True
        events = state.get_events()
        assert len(events) == 1
        assert events[0]["type"] == "governance.state.context_exceeded"


class TestTealStateMutationGovernance:
    """TealState mutation governance logging."""

    def test_mutation_governance_logs_additions(self):
        state = TealStateModule(StateConfig(
            max_context_size=10000, mutation_governance=True
        ))
        state.add_context("agent-1", ContextEntry(content="data", source="tool"))
        log = state.get_mutation_log("agent-1")
        assert len(log) == 1
        assert log[0]["action"] == "add"
        assert log[0]["source"] == "tool"
        assert log[0]["authorized"] is True

    def test_unauthorized_removal_blocked(self):
        state = TealStateModule(StateConfig(
            max_context_size=10000, mutation_governance=True
        ))
        state.add_context("agent-1", ContextEntry(content="data", source="user"))
        result = state.remove_context("agent-1", 0, source="attacker", authorized=False)
        assert result["allowed"] is False
        assert result["reason_code"] == "UNAUTHORIZED_STATE_MUTATION"
        # Entry should still be there
        assert len(state.get_context("agent-1")) == 1

    def test_authorized_removal_succeeds(self):
        state = TealStateModule(StateConfig(
            max_context_size=10000, mutation_governance=True
        ))
        state.add_context("agent-1", ContextEntry(content="data", source="user"))
        result = state.remove_context("agent-1", 0, source="admin", authorized=True)
        assert result["allowed"] is True
        assert len(state.get_context("agent-1")) == 0



# ══════════════════════════════════════════════════════════════════
# TealTemporal Tests
# ══════════════════════════════════════════════════════════════════


class TestTealTemporalSessionTTL:
    """TealTemporal session TTL enforcement."""

    def test_session_not_expired_within_ttl(self):
        current_time = 1000000.0  # ms
        temporal = TealTemporalModule(
            config=TemporalConfig(session_ttl_ms=60000, age_warning_threshold=80),
            now_fn=lambda: current_time,
        )
        temporal.start_session("agent-1")
        result = temporal.check_session("agent-1")
        assert result["expired"] is False
        assert result["warning"] is False

    def test_session_expired_after_ttl(self):
        times = [1000000.0]  # start time

        def now_fn():
            return times[0]

        temporal = TealTemporalModule(
            config=TemporalConfig(session_ttl_ms=60000),
            now_fn=now_fn,
        )
        temporal.start_session("agent-1")
        # Advance past TTL
        times[0] = 1000000.0 + 60001.0
        result = temporal.check_session("agent-1")
        assert result["expired"] is True
        assert result["reason_code"] == "SESSION_TTL_EXPIRED"

    def test_session_warning_at_threshold(self):
        times = [1000000.0]

        def now_fn():
            return times[0]

        temporal = TealTemporalModule(
            config=TemporalConfig(session_ttl_ms=100000, age_warning_threshold=80),
            now_fn=now_fn,
        )
        temporal.start_session("agent-1")
        # Advance to 85% of TTL
        times[0] = 1000000.0 + 85000.0
        result = temporal.check_session("agent-1")
        assert result["expired"] is False
        assert result["warning"] is True
        assert result["reason_code"] == "SESSION_AGE_WARNING"

    def test_no_session_treated_as_expired(self):
        temporal = TealTemporalModule()
        result = temporal.check_session("nonexistent")
        assert result["expired"] is True
        assert result["reason_code"] == "SESSION_TTL_EXPIRED"


class TestTealTemporalCooldown:
    """TealTemporal cooldown enforcement."""

    def test_no_cooldown_rule_allows_action(self):
        temporal = TealTemporalModule(config=TemporalConfig(cooldown_rules=[]))
        result = temporal.check_cooldown("agent-1", "DEPLOY")
        assert result["blocked"] is False

    def test_cooldown_blocks_within_interval(self):
        times = [1000000.0]

        def now_fn():
            return times[0]

        temporal = TealTemporalModule(
            config=TemporalConfig(
                cooldown_rules=[CooldownRule(action_class="DEPLOY", min_interval_ms=30000)]
            ),
            now_fn=now_fn,
        )
        # Record an action
        temporal.record_action("agent-1", "DEPLOY")
        # Advance only 10 seconds (still within 30s cooldown)
        times[0] = 1000000.0 + 10000.0
        result = temporal.check_cooldown("agent-1", "DEPLOY")
        assert result["blocked"] is True
        assert result["remaining_ms"] == 20000.0
        assert result["reason_code"] == "COOLDOWN_PERIOD_ACTIVE"

    def test_cooldown_allows_after_interval(self):
        times = [1000000.0]

        def now_fn():
            return times[0]

        temporal = TealTemporalModule(
            config=TemporalConfig(
                cooldown_rules=[CooldownRule(action_class="DEPLOY", min_interval_ms=30000)]
            ),
            now_fn=now_fn,
        )
        temporal.record_action("agent-1", "DEPLOY")
        # Advance past cooldown
        times[0] = 1000000.0 + 31000.0
        result = temporal.check_cooldown("agent-1", "DEPLOY")
        assert result["blocked"] is False


class TestTealTemporalTimeRestriction:
    """TealTemporal time-of-day restrictions."""

    def test_allowed_during_business_hours(self):
        from datetime import datetime, timezone
        import calendar

        # Create a time that's a Wednesday at 10:00 UTC
        # Wednesday = weekday 2 in Python, JS day = 3
        # 2025-01-08 is a Wednesday
        wed_10am_utc = datetime(2025, 1, 8, 10, 0, 0, tzinfo=timezone.utc)
        fixed_ms = wed_10am_utc.timestamp() * 1000

        temporal = TealTemporalModule(
            config=TemporalConfig(
                time_restrictions=[
                    TimeRestriction(
                        action_class="DEPLOY",
                        allowed_hours={"start": 9, "end": 17},
                        timezone="UTC",
                        allowed_days=[1, 2, 3, 4, 5],  # Mon-Fri (JS style)
                    )
                ]
            ),
            now_fn=lambda: fixed_ms,
        )
        result = temporal.check_time_restriction("DEPLOY")
        assert result["blocked"] is False

    def test_blocked_outside_business_hours(self):
        from datetime import datetime, timezone

        # Wednesday at 22:00 UTC
        wed_10pm_utc = datetime(2025, 1, 8, 22, 0, 0, tzinfo=timezone.utc)
        fixed_ms = wed_10pm_utc.timestamp() * 1000

        temporal = TealTemporalModule(
            config=TemporalConfig(
                time_restrictions=[
                    TimeRestriction(
                        action_class="DEPLOY",
                        allowed_hours={"start": 9, "end": 17},
                        timezone="UTC",
                        allowed_days=[1, 2, 3, 4, 5],
                    )
                ]
            ),
            now_fn=lambda: fixed_ms,
        )
        result = temporal.check_time_restriction("DEPLOY")
        assert result["blocked"] is True
        assert result["reason_code"] == "TIME_RESTRICTION_VIOLATED"

    def test_blocked_on_weekend(self):
        from datetime import datetime, timezone

        # Saturday at 10:00 UTC (2025-01-11 is a Saturday)
        sat_10am_utc = datetime(2025, 1, 11, 10, 0, 0, tzinfo=timezone.utc)
        fixed_ms = sat_10am_utc.timestamp() * 1000

        temporal = TealTemporalModule(
            config=TemporalConfig(
                time_restrictions=[
                    TimeRestriction(
                        action_class="DEPLOY",
                        allowed_hours={"start": 9, "end": 17},
                        timezone="UTC",
                        allowed_days=[1, 2, 3, 4, 5],  # Mon-Fri only
                    )
                ]
            ),
            now_fn=lambda: fixed_ms,
        )
        result = temporal.check_time_restriction("DEPLOY")
        assert result["blocked"] is True
        assert result["reason_code"] == "TIME_RESTRICTION_VIOLATED"

    def test_no_restriction_allows_action(self):
        temporal = TealTemporalModule(config=TemporalConfig(time_restrictions=[]))
        result = temporal.check_time_restriction("ANY_ACTION")
        assert result["blocked"] is False



# ══════════════════════════════════════════════════════════════════
# Cost Governance Tests
# ══════════════════════════════════════════════════════════════════


class TestGovernanceCostEnforcer:
    """GovernanceCostEnforcer budget enforcement."""

    def _make_enforcer(self, **kwargs) -> GovernanceCostEnforcer:
        limits = GovernanceCostLimits(
            per_request_max=kwargs.get("per_request_max", 1.0),
            per_session_max=kwargs.get("per_session_max", 10.0),
            per_daily_max=kwargs.get("per_daily_max", 100.0),
            per_agent_max=kwargs.get("per_agent_max", 500.0),
            reasoning_token_budget=kwargs.get("reasoning_token_budget", None),
        )
        return GovernanceCostEnforcer(
            CostGovernanceConfig(governance_limits=limits)
        )

    def test_allows_within_per_request_max(self):
        enforcer = self._make_enforcer(per_request_max=1.0)
        result = enforcer.check_budget("agent-1", estimated_cost=0.5)
        assert result["allowed"] is True

    def test_denies_exceeding_per_request_max(self):
        enforcer = self._make_enforcer(per_request_max=1.0)
        result = enforcer.check_budget("agent-1", estimated_cost=1.5)
        assert result["allowed"] is False
        assert result["reason_code"] == "COST_BUDGET_EXCEEDED"

    def test_denies_exceeding_per_session_max(self):
        enforcer = self._make_enforcer(per_session_max=5.0)
        # Record costs to fill session
        enforcer.record_cost("agent-1", cost=4.0, session_id="sess-1")
        # Next request would exceed session limit
        result = enforcer.check_budget("agent-1", estimated_cost=2.0, session_id="sess-1")
        assert result["allowed"] is False
        assert result["reason_code"] == "COST_BUDGET_EXCEEDED"

    def test_denies_exceeding_per_daily_max(self):
        enforcer = self._make_enforcer(per_daily_max=10.0)
        enforcer.record_cost("agent-1", cost=9.0)
        result = enforcer.check_budget("agent-1", estimated_cost=2.0)
        assert result["allowed"] is False
        assert result["reason_code"] == "COST_BUDGET_EXCEEDED"

    def test_denies_exceeding_per_agent_max(self):
        enforcer = self._make_enforcer(per_agent_max=20.0)
        enforcer.record_cost("agent-1", cost=19.0)
        result = enforcer.check_budget("agent-1", estimated_cost=2.0)
        assert result["allowed"] is False
        assert result["reason_code"] == "COST_BUDGET_EXCEEDED"

    def test_reasoning_token_budget_exceeded(self):
        enforcer = self._make_enforcer(reasoning_token_budget=1000)
        enforcer.record_cost("agent-1", cost=0.1, reasoning_tokens=900)
        result = enforcer.check_budget(
            "agent-1", estimated_cost=0.1, reasoning_tokens=200
        )
        assert result["allowed"] is False
        assert result["reason_code"] == "REASONING_TOKEN_BUDGET_EXCEEDED"

    def test_no_governance_limits_allows_everything(self):
        enforcer = GovernanceCostEnforcer(CostGovernanceConfig(governance_limits=None))
        result = enforcer.check_budget("agent-1", estimated_cost=999999.0)
        assert result["allowed"] is True
        assert result["remaining_budget"] == float("inf")

    def test_remaining_budget_is_most_restrictive(self):
        enforcer = self._make_enforcer(
            per_request_max=10.0,
            per_session_max=5.0,
            per_daily_max=100.0,
            per_agent_max=500.0,
        )
        result = enforcer.check_budget("agent-1", estimated_cost=2.0, session_id="s1")
        # Most restrictive is per_session_max - 0 - 2 = 3.0
        assert result["allowed"] is True
        assert result["remaining_budget"] == 3.0


class TestCostAnomalyDetector:
    """CostAnomalyDetector anomaly detection."""

    def test_no_anomaly_on_first_request(self):
        detector = CostAnomalyDetector(AnomalyDetectorConfig(
            baseline_window=10, spike_multiplier=10, growth_rate_threshold=0.5
        ))
        result = detector.check_anomaly("agent-1", "openai", cost=0.05)
        assert result["anomaly"] is False

    def test_detects_single_request_anomaly(self):
        detector = CostAnomalyDetector(AnomalyDetectorConfig(
            baseline_window=10, spike_multiplier=10, growth_rate_threshold=0.5
        ))
        # Build baseline with small costs
        for _ in range(5):
            detector.check_anomaly("agent-1", "openai", cost=0.01)
        # Spike: 100x the baseline
        result = detector.check_anomaly("agent-1", "openai", cost=1.0)
        assert result["anomaly"] is True
        assert result["alert_type"] == "single_request_anomaly"
        assert result["reason_code"] == "COST_ANOMALY_DETECTED"

    def test_no_anomaly_within_normal_range(self):
        detector = CostAnomalyDetector(AnomalyDetectorConfig(
            baseline_window=10, spike_multiplier=10, growth_rate_threshold=0.5
        ))
        for _ in range(5):
            detector.check_anomaly("agent-1", "openai", cost=0.05)
        # 2x is within 10x multiplier
        result = detector.check_anomaly("agent-1", "openai", cost=0.10)
        assert result["anomaly"] is False

    def test_detects_session_cost_spike(self):
        detector = CostAnomalyDetector(AnomalyDetectorConfig(
            baseline_window=100, spike_multiplier=100, growth_rate_threshold=0.5
        ))
        # First call establishes session baseline
        detector.check_anomaly("agent-1", "openai", cost=0.01, session_cost_total=1.0)
        # Second call with 100% growth (exceeds 50% threshold)
        result = detector.check_anomaly(
            "agent-1", "openai", cost=0.01, session_cost_total=2.5
        )
        assert result["anomaly"] is True
        assert result["alert_type"] == "session_cost_spike"
        assert result["reason_code"] == "COST_SPIKE_DETECTED"

    def test_rolling_window_evicts_old_entries(self):
        detector = CostAnomalyDetector(AnomalyDetectorConfig(
            baseline_window=3, spike_multiplier=10, growth_rate_threshold=0.5
        ))
        # Fill window
        detector.check_anomaly("agent-1", "openai", cost=0.01)
        detector.check_anomaly("agent-1", "openai", cost=0.01)
        detector.check_anomaly("agent-1", "openai", cost=0.01)
        # Add one more — should evict oldest
        detector.check_anomaly("agent-1", "openai", cost=0.01)
        assert detector.get_baseline_size("agent-1", "openai") == 3

    def test_baseline_mean_calculation(self):
        detector = CostAnomalyDetector(AnomalyDetectorConfig(
            baseline_window=10, spike_multiplier=10, growth_rate_threshold=0.5
        ))
        detector.check_anomaly("agent-1", "openai", cost=0.10)
        detector.check_anomaly("agent-1", "openai", cost=0.20)
        mean = detector.get_baseline_mean("agent-1", "openai")
        assert mean is not None
        assert abs(mean - 0.15) < 0.001
