"""Property-based tests for verify_contiguity (Python SDK).

Tests verify:
- Property 8: Verify Contiguity Accepts Valid Chains — honestly-produced chains
  always pass contiguity verification, including multi-agent filtered scenarios.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.6**

Uses Hypothesis library for property-based testing.
"""

from __future__ import annotations

import asyncio

from hypothesis import given, settings, HealthCheck
import hypothesis.strategies as st

from tealtiger.core.engine.v2_1.governance_engine import (
    GovernanceEngineV21,
    GovernanceEngineV21Options,
)
from tealtiger.core.engine.v2_1.types import ContiguitySuccess
from tealtiger.core.engine.v2_1.verify_contiguity import verify_contiguity


# ---------------------------------------------------------------------------
# Property 8: Verify Contiguity Accepts Valid Chains
# For any sequence of N decisions produced by a single GovernanceEngine
# instance for a single agent in order, verify_contiguity() SHALL return
# success with valid: True and count: N.
#
# ∀ N, ∀ agent_id:
#   decisions = [engine.evaluate(P₁), ..., engine.evaluate(Pₙ)]
#   verify_contiguity(decisions).valid === True
# ---------------------------------------------------------------------------


class TestVerifyContiguityAcceptsValidChains:
    """Property 8: Verify Contiguity Accepts Valid Chains.

    Verifies that honestly-produced decision chains always pass
    contiguity verification — no false negatives for valid chains.

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.6**
    """

    @given(n=st.integers(min_value=2, max_value=15))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_chains_pass_contiguity(self, n: int) -> None:
        """Honestly-produced chains of length n always pass verify_contiguity."""

        async def _run():
            engine = GovernanceEngineV21(
                GovernanceEngineV21Options(seal_secret="test", agent_id="agent")
            )
            ctx = {"correlation_id": "c1"}
            decisions = []
            for i in range(n):
                d = await engine.evaluate({"index": i}, ctx)
                decisions.append(d)
            result = verify_contiguity(decisions)
            assert isinstance(result, ContiguitySuccess)
            assert result.valid is True
            assert result.count == n

        asyncio.run(_run())

    @given(
        n_a=st.integers(min_value=1, max_value=5),
        n_b=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_multi_agent_filtered_contiguity(self, n_a: int, n_b: int) -> None:
        """Multi-agent decisions filtered by agent_id pass contiguity independently."""

        async def _run():
            engine = GovernanceEngineV21(
                GovernanceEngineV21Options(seal_secret="test")
            )
            all_decisions = []
            for i in range(n_a):
                d = await engine.evaluate(
                    {"a": i}, {"correlation_id": f"a{i}", "agent_id": "agent-a"}
                )
                all_decisions.append(d)
            for i in range(n_b):
                d = await engine.evaluate(
                    {"b": i}, {"correlation_id": f"b{i}", "agent_id": "agent-b"}
                )
                all_decisions.append(d)

            result_a = verify_contiguity(all_decisions, agent_id="agent-a")
            assert isinstance(result_a, ContiguitySuccess)
            assert result_a.count == n_a

            result_b = verify_contiguity(all_decisions, agent_id="agent-b")
            assert isinstance(result_b, ContiguitySuccess)
            assert result_b.count == n_b

        asyncio.run(_run())
