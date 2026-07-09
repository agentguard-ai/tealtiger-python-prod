"""Property-based tests for GovernanceEngineV21 (Python SDK).

Tests verify:
- Property 2: Intent Ref Binding — intent_ref equals SHA-256 of serialized request
- Property 6: Receipt Chain Integrity — receipt_ref chain is self-consistent
- Property 7: Validate Round-Trip — freshly produced decisions pass validation

**Validates: Requirements 3.1, 3.2, 3.3, 10.1, 10.2, 10.3, 6.2, 6.3, 6.7**

Uses Hypothesis library for property-based testing.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict

from hypothesis import given, settings, HealthCheck
import hypothesis.strategies as st

from tealtiger.core.engine.v2_1.crypto_service import CryptoService
from tealtiger.core.engine.v2_1.governance_engine import (
    GovernanceEngineV21,
    GovernanceEngineV21Options,
)
from tealtiger.core.engine.v2_1.types import GENESIS_RECEIPT_REF


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Payload strategy: dict with simple lowercase alpha keys and mixed values
payload_strategy = st.dictionaries(
    keys=st.text(
        min_size=1,
        max_size=10,
        alphabet="abcdefghijklmnopqrstuvwxyz",
    ),
    values=st.one_of(
        st.text(min_size=1, max_size=50),
        st.integers(),
        st.booleans(),
    ),
    min_size=1,
    max_size=5,
)


# ---------------------------------------------------------------------------
# Property 2: Intent Ref Binding
# For any request payload P, the intent_ref stored in the resulting Decision
# SHALL equal the SHA-256 hash that an independent verifier computes from
# the same serialized payload P.
#
# ∀ P:
#   decision = evaluate(P)
#   sha256(serialize(P)) === decision.intent_ref
# ---------------------------------------------------------------------------


class TestIntentRefBinding:
    """Property 2: Intent Ref Binding.

    Verifies that for any request payload, the intent_ref in the produced
    decision equals SHA-256 of the deterministically serialized request.

    **Validates: Requirements 3.1, 3.2, 3.3**
    """

    @given(payload=payload_strategy)
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_intent_ref_equals_sha256_of_serialized_request(
        self, payload: dict
    ) -> None:
        """intent_ref matches independent SHA-256 recomputation of the request payload."""

        async def _run():
            engine = GovernanceEngineV21(
                GovernanceEngineV21Options(seal_secret="test-secret")
            )
            ctx = {"correlation_id": "c1"}
            decision = await engine.evaluate(payload, ctx)
            expected = CryptoService.sha256(
                CryptoService.deterministic_serialize(payload)
            )
            assert decision.intent_ref == expected

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Property 6: Receipt Chain Integrity
# For any contiguous sequence of Decisions for a single agent, recomputing
# receipt_ref for Decision[i] using Decision[i-1]'s receipt_ref (or
# GENESIS_RECEIPT_REF for i=1) SHALL match the stored receipt_ref.
#
# ∀ sequence S of length N, ∀ i ∈ [1..N]:
#   computeReceiptRef(S[i], S[i-1].receipt_ref) === S[i].receipt_ref
# ---------------------------------------------------------------------------


class TestReceiptChainIntegrity:
    """Property 6: Receipt Chain Integrity.

    Verifies that the receipt_ref hash chain is self-consistent for
    any sequence of decisions produced by a single engine/agent.

    **Validates: Requirements 10.1, 10.2, 10.3**
    """

    @given(n=st.integers(min_value=2, max_value=15))
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_receipt_chain_integrity(self, n: int) -> None:
        """Receipt chain links are correctly computed for sequences of length n."""

        async def _run():
            engine = GovernanceEngineV21(
                GovernanceEngineV21Options(
                    seal_secret="secret", agent_id="agent-a"
                )
            )
            ctx = {"correlation_id": "c1"}
            request = {"action": "test"}

            decisions = []
            for _ in range(n):
                d = await engine.evaluate(request, ctx)
                decisions.append(d)

            # Verify first decision chains from GENESIS_RECEIPT_REF
            d1_dict = asdict(decisions[0])
            d1_dict.pop("receipt_ref", None)
            d1_dict.pop("governance_seal", None)
            expected_first = CryptoService.sha256(
                CryptoService.deterministic_serialize(d1_dict)
                + GENESIS_RECEIPT_REF
            )
            assert decisions[0].receipt_ref == expected_first

            # Verify subsequent decisions chain correctly
            for i in range(1, n):
                d_dict = asdict(decisions[i])
                d_dict.pop("receipt_ref", None)
                d_dict.pop("governance_seal", None)
                expected = CryptoService.sha256(
                    CryptoService.deterministic_serialize(d_dict)
                    + decisions[i - 1].receipt_ref
                )
                assert decisions[i].receipt_ref == expected

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Property 7: Validate Round-Trip
# For any Decision produced by the GovernanceEngine with a known request
# payload and seal_secret, the governance seal can be independently
# verified by recomputing the HMAC.
#
# ∀ P, K:
#   decision = engine.evaluate(P, K)
#   recomputed_seal == decision.governance_seal.hmac
# ---------------------------------------------------------------------------


class TestSealRoundTrip:
    """Property 7: Validate Round-Trip.

    Verifies that freshly produced decisions have a governance seal
    that can be independently recomputed and validated.

    **Validates: Requirements 6.2, 6.3, 6.7**
    """

    @given(payload=payload_strategy)
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_seal_round_trip(self, payload: dict) -> None:
        """Freshly produced decision's governance seal is independently verifiable."""

        async def _run():
            seal_secret = "my-test-secret"
            engine = GovernanceEngineV21(
                GovernanceEngineV21Options(seal_secret=seal_secret)
            )
            ctx = {"correlation_id": "c1"}
            decision = await engine.evaluate(payload, ctx)

            # Recompute seal HMAC
            d_dict = asdict(decision)
            d_dict.pop("governance_seal", None)
            payload_str = CryptoService.deterministic_serialize(d_dict)
            hmac_input = (
                payload_str
                + str(decision.governance_seal.timestamp)
                + decision.governance_seal.agent_id
            )
            expected_hmac = CryptoService.hmac_sha256(seal_secret, hmac_input)
            assert decision.governance_seal.hmac == expected_hmac

        asyncio.run(_run())
