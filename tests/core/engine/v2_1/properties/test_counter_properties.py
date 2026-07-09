"""Property-based tests for TEEC v2.1 CounterManager.

Tests verify:
- Property 4: Sequence Monotonicity — seq values form [1..N] per agent
- Property 5: Running Count Global Monotonicity — running_count forms [1..M] globally

**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6**

Uses Hypothesis library for property-based testing.
"""

from hypothesis import given, settings
import hypothesis.strategies as st

from tealtiger.core.engine.v2_1.counter_manager import CounterManager


# ---------------------------------------------------------------------------
# Property 4: Sequence Monotonicity
# For any sequence of N decisions produced for a single agent, the seq values
# SHALL form the sequence [1, 2, 3, ..., N] with no gaps or duplicates.
# ---------------------------------------------------------------------------


class TestSeqMonotonicity:
    """Property 4: Sequence Monotonicity.

    **Validates: Requirements 4.1, 4.3, 4.5**
    """

    @given(n=st.integers(min_value=1, max_value=200))
    @settings(max_examples=100)
    def test_seq_monotonicity_single_agent(self, n: int) -> None:
        """For any N calls to next_seq for a single agent, results form [1..N]."""
        cm = CounterManager()
        results = [cm.next_seq("agent-a") for _ in range(n)]
        assert results == list(range(1, n + 1))

    @given(
        num_agents=st.integers(min_value=1, max_value=10),
        decisions_per_agent=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=100)
    def test_seq_independent_per_agent(
        self, num_agents: int, decisions_per_agent: int
    ) -> None:
        """Per-agent seq counters are independent — incrementing one does not affect another.

        **Validates: Requirements 4.1, 4.3**
        """
        cm = CounterManager()
        for agent_idx in range(num_agents):
            agent_id = f"agent-{agent_idx}"
            results = [cm.next_seq(agent_id) for _ in range(decisions_per_agent)]
            assert results == list(range(1, decisions_per_agent + 1))


# ---------------------------------------------------------------------------
# Property 5: Running Count Global Monotonicity
# For any sequence of M decisions produced across all agents, the running_count
# values SHALL form the sequence [1, 2, 3, ..., M] with no gaps or duplicates.
# ---------------------------------------------------------------------------


class TestRunningCountGlobalMonotonicity:
    """Property 5: Running Count Global Monotonicity.

    **Validates: Requirements 4.2, 4.4, 4.6**
    """

    @given(m=st.integers(min_value=1, max_value=200))
    @settings(max_examples=100)
    def test_running_count_global_monotonicity(self, m: int) -> None:
        """For any M calls to next_running_count, results form [1..M]."""
        cm = CounterManager()
        results = [cm.next_running_count() for _ in range(m)]
        assert results == list(range(1, m + 1))

    @given(
        ops=st.lists(
            st.tuples(
                st.sampled_from(["agent-a", "agent-b", "agent-c"]),
                st.just("seq"),
            ),
            min_size=1,
            max_size=100,
        )
    )
    @settings(max_examples=100)
    def test_running_count_monotonic_with_interleaved_agents(
        self, ops: list
    ) -> None:
        """Running count remains monotonic [1..M] regardless of interleaved agent operations.

        **Validates: Requirements 4.2, 4.4, 4.6**
        """
        cm = CounterManager()
        running_counts = []
        for agent_id, _ in ops:
            cm.next_seq(agent_id)
            running_counts.append(cm.next_running_count())
        assert running_counts == list(range(1, len(ops) + 1))
