"""Unit tests for verify_contiguity (Python SDK).

Tests the contiguity verification function against:
- Empty and single-decision arrays (trivially contiguous)
- Valid multi-decision chains
- Sequence gaps
- Running count regression
- Receipt chain breaks (tampered decisions)
- Version-incompatible decisions (missing v2.1 fields)
- Agent ID filtering

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 7.4, 9.4, 10.4, 10.5
"""

from __future__ import annotations

from dataclasses import asdict

import pytest

from tealtiger.core.engine.v2_1.crypto_service import CryptoService
from tealtiger.core.engine.v2_1.governance_engine import (
    GovernanceEngineV21,
    GovernanceEngineV21Options,
)
from tealtiger.core.engine.v2_1.types import (
    ContiguityFailure,
    ContiguitySuccess,
    DecisionV21,
    GENESIS_RECEIPT_REF,
    GovernanceSeal,
)
from tealtiger.core.engine.v2_1.verify_contiguity import verify_contiguity


# ── Helpers ────────────────────────────────────────────────────────

SEAL_SECRET = "test-secret-for-contiguity"
AGENT_ID = "agent-contiguity"


@pytest.fixture
def engine():
    """GovernanceEngineV21 configured for testing."""
    opts = GovernanceEngineV21Options(
        seal_secret=SEAL_SECRET,
        agent_id=AGENT_ID,
    )
    return GovernanceEngineV21(opts)


@pytest.fixture
async def three_decisions(engine):
    """Produce three sequential decisions from the same engine/agent."""
    payloads = [
        {"action": "tool.execute", "tool": "read_file", "index": 1},
        {"action": "tool.execute", "tool": "write_file", "index": 2},
        {"action": "tool.execute", "tool": "delete_file", "index": 3},
    ]
    decisions = []
    for p in payloads:
        d = await engine.evaluate(p, {"correlation_id": f"corr-{len(decisions)+1}"})
        decisions.append(d)
    return decisions


def _build_chain(count: int, agent_id: str = "test-agent") -> list:
    """Build a valid chain of decision dicts manually for testing."""
    decisions = []
    prev_receipt_ref = GENESIS_RECEIPT_REF

    for i in range(1, count + 1):
        decision_without_chain = {
            "action": "ALLOW",
            "reason_codes": ["POLICY_COMPLIANT"],
            "risk_score": 0,
            "mode": "ENFORCE",
            "policy_id": "test-policy",
            "policy_version": "1.0.0",
            "component_versions": {},
            "correlation_id": f"corr-{i}",
            "reason": "Allowed",
            "event_type": "policy.evaluation",
            "timestamp": 1000000000000 + i,
            "module": "GovernanceEngineV21",
            "metadata": {},
            "trace_id": None,
            "workflow_id": None,
            "run_id": None,
            "span_id": None,
            "parent_span_id": None,
            "provider": None,
            "registry_refs": None,
            "findings": None,
            "intent_ref": "a" * 64,
            "seq": i,
            "running_count": i,
            "normalization_id": "b" * 64,
            "teec_version": "2.1",
        }

        # Compute receipt_ref
        payload = CryptoService.deterministic_serialize(decision_without_chain)
        receipt_ref = CryptoService.sha256(payload + prev_receipt_ref)

        decision_without_chain["receipt_ref"] = receipt_ref

        # Compute seal
        full_for_seal = dict(decision_without_chain)
        seal_payload = CryptoService.deterministic_serialize(full_for_seal)
        seal_ts = 1000000000000 + i
        hmac_input = seal_payload + str(seal_ts) + agent_id
        hmac_value = CryptoService.hmac_sha256(SEAL_SECRET, hmac_input)

        decision_without_chain["governance_seal"] = {
            "hmac": hmac_value,
            "timestamp": seal_ts,
            "agent_id": agent_id,
        }

        decisions.append(decision_without_chain)
        prev_receipt_ref = receipt_ref

    return decisions


# ── Trivially Contiguous Cases ─────────────────────────────────────


class TestTrivialContiguity:
    """Test that empty and single-decision inputs are trivially contiguous."""

    def test_empty_array_returns_success(self):
        """An empty array is trivially contiguous."""
        result = verify_contiguity([])

        assert isinstance(result, ContiguitySuccess)
        assert result.valid is True
        assert result.count == 0

    def test_single_decision_returns_success(self):
        """A single decision is trivially contiguous."""
        chain = _build_chain(1)
        result = verify_contiguity(chain)

        assert isinstance(result, ContiguitySuccess)
        assert result.valid is True
        assert result.count == 1

    @pytest.mark.asyncio
    async def test_single_engine_decision_returns_success(self, engine):
        """A single decision from engine is trivially contiguous."""
        payload = {"test": "data"}
        d = await engine.evaluate(payload, {"correlation_id": "c1"})
        result = verify_contiguity([d])

        assert isinstance(result, ContiguitySuccess)
        assert result.valid is True
        assert result.count == 1


# ── Valid Chain Cases ──────────────────────────────────────────────


class TestValidChains:
    """Test that honestly-produced chains pass contiguity verification."""

    @pytest.mark.asyncio
    async def test_two_decisions_pass(self, engine):
        """Two sequential decisions from the same agent pass."""
        d1 = await engine.evaluate({"a": 1}, {"correlation_id": "c1"})
        d2 = await engine.evaluate({"b": 2}, {"correlation_id": "c2"})
        result = verify_contiguity([d1, d2])

        assert isinstance(result, ContiguitySuccess)
        assert result.valid is True
        assert result.count == 2

    @pytest.mark.asyncio
    async def test_three_decisions_pass(self, three_decisions):
        """Three sequential decisions from the same agent pass."""
        result = verify_contiguity(three_decisions)

        assert isinstance(result, ContiguitySuccess)
        assert result.valid is True
        assert result.count == 3

    def test_manually_built_chain_passes(self):
        """A manually-built valid chain of 5 decisions passes."""
        chain = _build_chain(5)
        result = verify_contiguity(chain)

        assert isinstance(result, ContiguitySuccess)
        assert result.valid is True
        assert result.count == 5

    @pytest.mark.asyncio
    async def test_decisions_as_dicts_pass(self, three_decisions):
        """Decisions converted to dicts still pass contiguity."""
        dicts = [asdict(d) for d in three_decisions]
        result = verify_contiguity(dicts)

        assert isinstance(result, ContiguitySuccess)
        assert result.valid is True
        assert result.count == 3


# ── Sequence Gap Cases ─────────────────────────────────────────────


class TestSeqGap:
    """Test that seq gaps are detected."""

    def test_seq_gap_detected(self):
        """A gap in seq (1, 3) is detected."""
        chain = _build_chain(3)
        # Skip seq=2 by removing middle and adjusting
        chain[1]["seq"] = 3  # now seq goes 1, 3, 3
        result = verify_contiguity(chain)

        assert isinstance(result, ContiguityFailure)
        assert result.valid is False
        assert result.index == 1
        assert result.check == "seq_gap"
        assert "Expected seq 2" in result.message
        assert "got 3" in result.message

    def test_duplicate_seq_detected(self):
        """Duplicate seq values (1, 1, 2) are detected."""
        chain = _build_chain(3)
        chain[1]["seq"] = 1  # now seq goes 1, 1, 3
        result = verify_contiguity(chain)

        assert isinstance(result, ContiguityFailure)
        assert result.valid is False
        assert result.index == 1
        assert result.check == "seq_gap"

    def test_decreasing_seq_detected(self):
        """Decreasing seq values are detected."""
        chain = _build_chain(3)
        chain[1]["seq"] = 0  # now seq goes 1, 0, 3
        # Note: seq=0 means version_incompatible
        result = verify_contiguity(chain)

        assert isinstance(result, ContiguityFailure)
        assert result.valid is False
        assert result.check == "version_incompatible"


# ── Running Count Regression Cases ─────────────────────────────────


class TestCountRegression:
    """Test that running_count regression is detected."""

    def test_equal_running_count_detected(self):
        """Equal running_count values are detected (must be strictly increasing)."""
        chain = _build_chain(3)
        chain[1]["running_count"] = 1  # Same as first decision
        result = verify_contiguity(chain)

        assert isinstance(result, ContiguityFailure)
        assert result.valid is False
        assert result.index == 1
        assert result.check == "count_regression"
        assert "strictly increasing" in result.message

    def test_decreasing_running_count_detected(self):
        """Decreasing running_count values are detected."""
        chain = _build_chain(3)
        chain[2]["running_count"] = 1  # Goes backwards
        result = verify_contiguity(chain)

        assert isinstance(result, ContiguityFailure)
        assert result.valid is False
        assert result.index == 2
        assert result.check == "count_regression"


# ── Chain Break Cases ──────────────────────────────────────────────


class TestChainBreak:
    """Test that receipt_ref chain breaks are detected."""

    def test_tampered_receipt_ref_detected(self):
        """A tampered receipt_ref is detected as a chain break."""
        chain = _build_chain(3)
        chain[1]["receipt_ref"] = "f" * 64  # Tampered
        result = verify_contiguity(chain)

        assert isinstance(result, ContiguityFailure)
        assert result.valid is False
        assert result.index == 1
        assert result.check == "chain_break"
        assert "chain verification failed" in result.message

    def test_swapped_decisions_detected(self):
        """Swapping two decisions breaks the chain."""
        chain = _build_chain(3)
        # Swap positions 1 and 2 (but keep seq/running_count in order)
        chain[1], chain[2] = chain[2], chain[1]
        # Fix seq and running_count to be in order (so chain_break fires, not seq_gap)
        chain[1]["seq"] = 2
        chain[1]["running_count"] = 2
        chain[2]["seq"] = 3
        chain[2]["running_count"] = 3
        result = verify_contiguity(chain)

        assert isinstance(result, ContiguityFailure)
        assert result.valid is False
        assert result.check == "chain_break"

    @pytest.mark.asyncio
    async def test_tampered_field_breaks_chain(self, three_decisions):
        """Tampering with a field in the middle decision breaks the chain for subsequent."""
        dicts = [asdict(d) for d in three_decisions]
        # Tamper with a field in decision[1] that would affect decision[2]'s receipt_ref check
        # But the receipt_ref stored on decision[1] was computed from original data,
        # so modifying decision[1]'s non-receipt fields after production won't directly
        # break the chain. Instead we need to verify that the stored receipt_ref on
        # decision[2] chains from decision[1]'s receipt_ref.
        # The simplest tamper test: modify decision[1]'s receipt_ref
        dicts[1]["receipt_ref"] = "0" * 64  # Wrong receipt_ref
        result = verify_contiguity(dicts)

        assert isinstance(result, ContiguityFailure)
        assert result.valid is False
        # Index 1 chain_break because decision[1]'s receipt_ref doesn't match
        # what we'd compute from decision[0]'s receipt_ref
        assert result.check == "chain_break"


# ── Version Incompatible Cases ─────────────────────────────────────


class TestVersionIncompatible:
    """Test that non-v2.1 decisions are detected."""

    def test_v12_decision_in_array_returns_version_incompatible(self):
        """A v1.2 decision (no seq/receipt_ref) fails with version_incompatible."""
        v12_decision = {
            "action": "ALLOW",
            "reason_codes": ["POLICY_COMPLIANT"],
            "risk_score": 0,
            "mode": "ENFORCE",
            "policy_id": "v1.2-governance",
        }
        chain = _build_chain(2)
        # Insert v1.2 decision at position 1
        decisions = [chain[0], v12_decision, chain[1]]
        result = verify_contiguity(decisions)

        assert isinstance(result, ContiguityFailure)
        assert result.valid is False
        assert result.index == 1
        assert result.check == "version_incompatible"
        assert "lacks TEEC v2.1 fields" in result.message

    def test_decision_with_seq_zero_is_version_incompatible(self):
        """A decision with seq=0 is version-incompatible."""
        chain = _build_chain(2)
        chain[0]["seq"] = 0  # Invalid
        result = verify_contiguity(chain)

        assert isinstance(result, ContiguityFailure)
        assert result.valid is False
        assert result.index == 0
        assert result.check == "version_incompatible"

    def test_decision_with_empty_receipt_ref_is_version_incompatible(self):
        """A decision with empty receipt_ref is version-incompatible."""
        chain = _build_chain(2)
        chain[0]["receipt_ref"] = ""
        result = verify_contiguity(chain)

        assert isinstance(result, ContiguityFailure)
        assert result.valid is False
        assert result.index == 0
        assert result.check == "version_incompatible"

    def test_decision_with_none_seq_is_version_incompatible(self):
        """A decision with seq=None is version-incompatible."""
        chain = _build_chain(2)
        chain[0]["seq"] = None
        result = verify_contiguity(chain)

        assert isinstance(result, ContiguityFailure)
        assert result.valid is False
        assert result.index == 0
        assert result.check == "version_incompatible"


# ── Agent ID Filtering Cases ───────────────────────────────────────


class TestAgentIdFiltering:
    """Test that agent_id filtering works correctly."""

    def test_filter_by_agent_id_selects_matching(self):
        """Filtering by agent_id selects only matching decisions."""
        chain_a = _build_chain(3, agent_id="agent-a")
        chain_b = _build_chain(2, agent_id="agent-b")

        # Interleave decisions from both agents
        mixed = [chain_a[0], chain_b[0], chain_a[1], chain_b[1], chain_a[2]]

        result = verify_contiguity(mixed, agent_id="agent-a")

        assert isinstance(result, ContiguitySuccess)
        assert result.valid is True
        assert result.count == 3

    def test_filter_by_agent_id_selects_other_agent(self):
        """Filtering by a different agent_id selects those decisions."""
        chain_a = _build_chain(3, agent_id="agent-a")
        chain_b = _build_chain(2, agent_id="agent-b")

        mixed = [chain_a[0], chain_b[0], chain_a[1], chain_b[1], chain_a[2]]

        result = verify_contiguity(mixed, agent_id="agent-b")

        assert isinstance(result, ContiguitySuccess)
        assert result.valid is True
        assert result.count == 2

    def test_filter_no_match_returns_empty_success(self):
        """Filtering by non-existent agent_id returns empty success."""
        chain = _build_chain(3, agent_id="agent-a")
        result = verify_contiguity(chain, agent_id="non-existent")

        assert isinstance(result, ContiguitySuccess)
        assert result.valid is True
        assert result.count == 0

    def test_filter_single_match_returns_success(self):
        """Filtering to a single matching decision is trivially contiguous."""
        chain_a = _build_chain(1, agent_id="agent-a")
        chain_b = _build_chain(2, agent_id="agent-b")

        mixed = [chain_a[0], chain_b[0], chain_b[1]]

        result = verify_contiguity(mixed, agent_id="agent-a")

        assert isinstance(result, ContiguitySuccess)
        assert result.valid is True
        assert result.count == 1

    @pytest.mark.asyncio
    async def test_engine_with_agent_id_filter(self):
        """Engine-produced decisions are filtered correctly by agent_id."""
        engine_a = GovernanceEngineV21(
            GovernanceEngineV21Options(seal_secret=SEAL_SECRET, agent_id="a")
        )
        engine_b = GovernanceEngineV21(
            GovernanceEngineV21Options(seal_secret=SEAL_SECRET, agent_id="b")
        )

        d_a1 = await engine_a.evaluate({"x": 1}, {"correlation_id": "c1"})
        d_b1 = await engine_b.evaluate({"y": 1}, {"correlation_id": "c2"})
        d_a2 = await engine_a.evaluate({"x": 2}, {"correlation_id": "c3"})

        # All mixed: verify only agent "a"
        result = verify_contiguity([d_a1, d_b1, d_a2], agent_id="a")

        assert isinstance(result, ContiguitySuccess)
        assert result.valid is True
        assert result.count == 2


# ── Edge Cases ─────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_large_chain_passes(self):
        """A larger chain (10 decisions) passes."""
        chain = _build_chain(10)
        result = verify_contiguity(chain)

        assert isinstance(result, ContiguitySuccess)
        assert result.valid is True
        assert result.count == 10

    def test_first_failure_reported(self):
        """When multiple failures exist, the first one is reported."""
        chain = _build_chain(5)
        # Create failures at indices 2 and 4
        chain[2]["seq"] = 10  # seq gap at index 2
        chain[4]["seq"] = 20  # another gap at index 4
        result = verify_contiguity(chain)

        assert isinstance(result, ContiguityFailure)
        assert result.index == 2  # First failure reported

    def test_dataclass_decisions_accepted(self):
        """DecisionV21 dataclass instances are accepted and processed."""
        # Build a valid chain of dataclass instances
        decisions = []
        prev_receipt_ref = GENESIS_RECEIPT_REF

        for i in range(1, 4):
            d = DecisionV21(
                action="ALLOW",
                reason_codes=["POLICY_COMPLIANT"],
                seq=i,
                running_count=i,
                intent_ref="a" * 64,
                normalization_id="b" * 64,
                teec_version="2.1",
            )

            # Compute receipt_ref
            d_dict = {
                k: v for k, v in asdict(d).items()
                if k not in ("receipt_ref", "governance_seal")
            }
            payload = CryptoService.deterministic_serialize(d_dict)
            receipt_ref = CryptoService.sha256(payload + prev_receipt_ref)
            d.receipt_ref = receipt_ref

            # Compute seal
            full_dict = asdict(d)
            full_dict.pop("governance_seal", None)
            seal_payload = CryptoService.deterministic_serialize(full_dict)
            seal_ts = 1000000000000 + i
            hmac_input = seal_payload + str(seal_ts) + "test-agent"
            hmac_value = CryptoService.hmac_sha256(SEAL_SECRET, hmac_input)
            d.governance_seal = GovernanceSeal(
                hmac=hmac_value, timestamp=seal_ts, agent_id="test-agent"
            )

            decisions.append(d)
            prev_receipt_ref = receipt_ref

        result = verify_contiguity(decisions)

        assert isinstance(result, ContiguitySuccess)
        assert result.valid is True
        assert result.count == 3
