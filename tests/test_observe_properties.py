"""
Property-based tests for TealTiger observe() module.

Uses hypothesis to validate universal correctness properties.
"""
import sys
sys.path.insert(0, r"c:\Users\satis\OneDrive\AI Agent Security Platform\packages\tealtiger-python\src")

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from tealtiger.observe.freeze_registry import FreezeRegistry, freeze, unfreeze
from tealtiger.observe.behavioral_baseline import BehavioralBaseline
from tealtiger.observe.types import BaselineSample
from tealtiger.observe.cost_accumulator import CostAccumulator
from tealtiger.observe.pii_scanner import ObservePIIScanner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_freeze_registry():
    """Reset the FreezeRegistry singleton between every test."""
    registry = FreezeRegistry.get_instance()
    registry._reset()
    yield
    registry._reset()


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

agent_ids = st.text(min_size=1, max_size=50)
window_sizes = st.integers(min_value=1, max_value=500)
costs = st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False)
latencies = st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False)
token_counts = st.integers(min_value=0, max_value=10000)
tool_call_counts = st.integers(min_value=0, max_value=50)

baseline_samples = st.builds(
    BaselineSample,
    latency_ms=latencies,
    input_tokens=token_counts,
    output_tokens=token_counts,
    cost_usd=costs,
    tool_call_count=tool_call_counts,
)


# ---------------------------------------------------------------------------
# Property 5: Freeze Idempotence
# freeze(A); freeze(A) ≡ freeze(A) — calling freeze multiple times has the
# same effect as calling it once.
# ---------------------------------------------------------------------------


class TestFreezeIdempotence:
    """Property 5: freeze(id) called N times ≡ called once."""

    @settings(max_examples=100)
    @given(agent_id=agent_ids, repeat_count=st.integers(min_value=2, max_value=20))
    def test_freeze_idempotent_same_state(self, agent_id, repeat_count):
        """Freezing N times produces the same state as freezing once."""
        registry = FreezeRegistry.get_instance()
        registry._reset()

        # Freeze once
        registry.freeze(agent_id)
        state_after_one = registry.is_frozen(agent_id)

        # Freeze N more times
        for _ in range(repeat_count):
            registry.freeze(agent_id)

        state_after_many = registry.is_frozen(agent_id)

        assert state_after_one == state_after_many
        assert state_after_one is True

    @settings(max_examples=100)
    @given(agent_id=agent_ids)
    def test_freeze_idempotent_single_unfreeze_clears(self, agent_id):
        """After multiple freezes, a single unfreeze still clears the state."""
        registry = FreezeRegistry.get_instance()
        registry._reset()

        # Freeze multiple times
        registry.freeze(agent_id)
        registry.freeze(agent_id)
        registry.freeze(agent_id)

        # Single unfreeze restores
        registry.unfreeze(agent_id)
        assert registry.is_frozen(agent_id) is False


# ---------------------------------------------------------------------------
# Property 6: Freeze/Unfreeze Round-Trip
# freeze(A); unfreeze(A) → is_frozen(A) == False
# ---------------------------------------------------------------------------


class TestFreezeUnfreezeRoundTrip:
    """Property 6: freeze then unfreeze returns to unfrozen state."""

    @settings(max_examples=100)
    @given(agent_id=agent_ids)
    def test_freeze_unfreeze_returns_to_unfrozen(self, agent_id):
        """freeze(A); unfreeze(A) → is_frozen(A) == False."""
        registry = FreezeRegistry.get_instance()
        registry._reset()

        # Precondition: not frozen initially
        assert registry.is_frozen(agent_id) is False

        # Round trip
        registry.freeze(agent_id)
        assert registry.is_frozen(agent_id) is True

        registry.unfreeze(agent_id)
        assert registry.is_frozen(agent_id) is False

    @settings(max_examples=100)
    @given(agent_id=agent_ids)
    def test_unfreeze_non_frozen_is_noop(self, agent_id):
        """Unfreezing a non-frozen agent is a no-op (no error)."""
        registry = FreezeRegistry.get_instance()
        registry._reset()

        # Should not raise
        registry.unfreeze(agent_id)
        assert registry.is_frozen(agent_id) is False

    @settings(max_examples=100)
    @given(agent_id=agent_ids)
    def test_wildcard_freeze_unfreeze_round_trip(self, agent_id):
        """Wildcard freeze/unfreeze does not affect individually frozen agents."""
        registry = FreezeRegistry.get_instance()
        registry._reset()

        # Freeze individually
        registry.freeze(agent_id)

        # Wildcard freeze then unfreeze
        registry.freeze("*")
        registry.unfreeze("*")

        # Individual freeze should still be active
        assert registry.is_frozen(agent_id) is True


# ---------------------------------------------------------------------------
# Property 7: Baseline Window Exactness
# Baseline uses exactly N samples; subsequent add_sample is no-op.
# ---------------------------------------------------------------------------


class TestBaselineWindowExactness:
    """Property 7: baseline uses exactly window_size samples, then ignores more."""

    @settings(max_examples=100)
    @given(
        window_size=window_sizes,
        samples=st.lists(baseline_samples, min_size=1, max_size=600),
    )
    def test_baseline_uses_exactly_n_samples(self, window_size, samples):
        """Baseline collects at most window_size samples."""
        baseline = BehavioralBaseline(window_size=window_size)

        for sample in samples:
            baseline.add_sample(sample)

        result = baseline.get_baseline()

        if len(samples) >= window_size:
            # Should be complete with exactly window_size samples
            assert result.is_complete is True
            assert result.sample_count == window_size
            assert result.stats is not None
        else:
            # Not enough samples yet
            assert result.is_complete is False
            assert result.sample_count == len(samples)
            assert result.stats is None

    @settings(max_examples=100)
    @given(
        window_size=st.integers(min_value=1, max_value=50),
        extra_samples=st.lists(baseline_samples, min_size=1, max_size=100),
    )
    def test_add_sample_after_completion_is_noop(self, window_size, extra_samples):
        """Once baseline is complete, add_sample does not change state."""
        baseline = BehavioralBaseline(window_size=window_size)

        # Fill baseline to completion
        for i in range(window_size):
            baseline.add_sample(BaselineSample(
                latency_ms=float(i + 1),
                input_tokens=i * 10,
                output_tokens=i * 5,
                cost_usd=float(i) * 0.01,
                tool_call_count=i % 5,
            ))

        assert baseline.is_complete() is True
        stats_before = baseline.get_baseline().stats

        # Add extra samples — should all be no-ops
        for sample in extra_samples:
            baseline.add_sample(sample)

        assert baseline.get_baseline().sample_count == window_size
        assert baseline.get_baseline().stats == stats_before


# ---------------------------------------------------------------------------
# Property 3: Cost Monotonicity
# For any sequence of N requests, cumulative cost at i >= cumulative cost
# at i-1.
# ---------------------------------------------------------------------------


class TestCostMonotonicity:
    """Property 3: cumulative cost is monotonically non-decreasing."""

    @settings(max_examples=100)
    @given(
        request_costs=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=5000),   # input_tokens
                st.integers(min_value=0, max_value=5000),   # output_tokens
            ),
            min_size=2,
            max_size=50,
        ),
    )
    def test_session_cost_never_decreases(self, request_costs):
        """Session cost total is monotonically non-decreasing across requests."""
        accumulator = CostAccumulator()
        agent_id = "test-agent"
        session_id = "test-session"
        model = "gpt-4o"
        provider = "openai"

        previous_total = 0.0

        for i, (input_tokens, output_tokens) in enumerate(request_costs):
            # Create a simple usage object
            usage = type("Usage", (), {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            })()

            accumulator.record_cost(
                agent_id=agent_id,
                session_id=session_id,
                request_id=f"req-{i}",
                model=model,
                provider=provider,
                usage=usage,
            )

            current_total = accumulator.get_session_cost(session_id).total_cost
            assert current_total >= previous_total, (
                f"Cost decreased from {previous_total} to {current_total} "
                f"after request {i}"
            )
            previous_total = current_total

    @settings(max_examples=100)
    @given(
        request_costs=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=5000),
                st.integers(min_value=0, max_value=5000),
            ),
            min_size=2,
            max_size=50,
        ),
    )
    def test_agent_cost_never_decreases(self, request_costs):
        """Agent cost total is monotonically non-decreasing across requests."""
        accumulator = CostAccumulator()
        agent_id = "test-agent"
        session_id = "test-session"
        model = "claude-3-sonnet"
        provider = "anthropic"

        previous_total = 0.0

        for i, (input_tokens, output_tokens) in enumerate(request_costs):
            usage = type("Usage", (), {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            })()

            accumulator.record_cost(
                agent_id=agent_id,
                session_id=session_id,
                request_id=f"req-{i}",
                model=model,
                provider=provider,
                usage=usage,
            )

            current_total = accumulator.get_agent_cost(agent_id).total_cost
            assert current_total >= previous_total
            previous_total = current_total


# ---------------------------------------------------------------------------
# Property 4: PII Non-Interference
# For any payload (including PII), scan never throws and never blocks.
# ---------------------------------------------------------------------------


class TestPIINonInterference:
    """Property 4: PII scanner never throws, never blocks, always returns."""

    @settings(max_examples=100)
    @given(payload=st.text(max_size=5000))
    def test_scan_never_throws_on_arbitrary_text(self, payload):
        """PII scan never raises an exception regardless of input text."""
        scanner = ObservePIIScanner()

        # Must not throw for any text input
        result = scanner.scan(payload, phase="request")

        # Result is either None (no PII) or a valid summary
        if result is not None:
            assert result.count > 0
            assert len(result.types) > 0
            assert result.phase == "request"

    @settings(max_examples=100)
    @given(
        payload=st.one_of(
            st.none(),
            st.text(max_size=1000),
            st.dictionaries(
                keys=st.text(min_size=1, max_size=20),
                values=st.text(max_size=200),
                max_size=10,
            ),
            st.lists(st.text(max_size=100), max_size=10),
            st.integers(),
            st.floats(allow_nan=True, allow_infinity=True),
            st.booleans(),
        ),
        phase=st.sampled_from(["request", "response"]),
    )
    def test_scan_never_throws_on_any_type(self, payload, phase):
        """PII scan gracefully handles any payload type without raising."""
        scanner = ObservePIIScanner()

        # Must not throw for any payload type
        result = scanner.scan(payload, phase=phase)

        # Result is either None or a valid PIIDetectionSummary
        if result is not None:
            assert result.count > 0
            assert len(result.types) > 0
            assert result.phase == phase
            # Never exposes actual PII values — only types and counts
            for pii_type in result.types:
                assert pii_type in ("email", "phone", "ssn", "credit_card")

    @settings(max_examples=100)
    @given(
        emails=st.lists(
            st.from_regex(r"[a-z]{3,10}@[a-z]{3,8}\.[a-z]{2,4}", fullmatch=True),
            min_size=1,
            max_size=5,
        ),
    )
    def test_scan_detects_pii_without_blocking(self, emails):
        """Scanner detects known PII patterns and reports without blocking."""
        scanner = ObservePIIScanner()
        payload = " ".join(emails)

        result = scanner.scan(payload, phase="response")

        # Should detect email PII
        assert result is not None
        assert "email" in result.types
        assert result.count >= 1
        assert result.phase == "response"
