"""Unit tests for GovernanceEngineV21 (Python SDK).

Tests the full v2.1 governance pipeline including:
- Opt-in/opt-out behavior based on seal_secret
- Intent binding (intent_ref, normalization_id)
- Receipt chaining (receipt_ref)
- Sequence counters (seq, running_count)
- GovernanceSeal HMAC computation
- Multi-agent scenarios
"""

from __future__ import annotations

import time
from dataclasses import asdict

import pytest

from tealtiger.core.engine.v2_1.counter_manager import CounterManager
from tealtiger.core.engine.v2_1.crypto_service import CryptoService
from tealtiger.core.engine.v2_1.governance_engine import (
    GovernanceEngineV21,
    GovernanceEngineV21Options,
)
from tealtiger.core.engine.v2_1.types import (
    GENESIS_RECEIPT_REF,
    DecisionV21,
    GovernanceSeal,
)


# ── Helpers ────────────────────────────────────────────────────────


@pytest.fixture
def basic_request():
    """A simple request payload for testing."""
    return {"action": "tool.execute", "tool": "read_file", "args": {"path": "/tmp/x"}}


@pytest.fixture
def basic_ctx():
    """A simple evaluation context."""
    return {"correlation_id": "test-corr-001"}


@pytest.fixture
def engine_with_seal():
    """Engine configured with seal_secret (v2.1 mode)."""
    opts = GovernanceEngineV21Options(
        seal_secret="test-secret-key",
        agent_id="agent-alpha",
    )
    return GovernanceEngineV21(opts)


@pytest.fixture
def engine_without_seal():
    """Engine without seal_secret (v1.2 fallback mode)."""
    opts = GovernanceEngineV21Options()
    return GovernanceEngineV21(opts)


# ── Opt-in / Opt-out Tests ─────────────────────────────────────────


class TestOptInOptOut:
    """Test seal_secret opt-in/opt-out behavior."""

    @pytest.mark.asyncio
    async def test_no_seal_secret_produces_basic_decision(
        self, engine_without_seal, basic_request, basic_ctx
    ):
        """Without seal_secret, produces v1.2-equivalent decision."""
        decision = await engine_without_seal.evaluate(basic_request, basic_ctx)

        assert decision.action == "ALLOW"
        assert decision.reason_codes == ["POLICY_COMPLIANT"]
        assert decision.risk_score == 0
        assert decision.teec_version == "0.1.0"
        # Crypto fields should be empty/default
        assert decision.intent_ref == ""
        assert decision.receipt_ref == ""
        assert decision.seq == 0
        assert decision.running_count == 0
        assert decision.normalization_id == ""
        assert decision.governance_seal is None

    @pytest.mark.asyncio
    async def test_with_seal_secret_produces_v21_decision(
        self, engine_with_seal, basic_request, basic_ctx
    ):
        """With seal_secret, produces full v2.1 decision."""
        decision = await engine_with_seal.evaluate(basic_request, basic_ctx)

        assert decision.action == "ALLOW"
        assert decision.teec_version == "2.1"
        assert decision.intent_ref != ""
        assert len(decision.intent_ref) == 64  # SHA-256 hex
        assert decision.receipt_ref != ""
        assert len(decision.receipt_ref) == 64
        assert decision.seq == 1
        assert decision.running_count == 1
        assert decision.normalization_id != ""
        assert len(decision.normalization_id) == 64
        assert decision.governance_seal is not None
        assert len(decision.governance_seal.hmac) == 64
        assert decision.governance_seal.agent_id == "agent-alpha"
        assert decision.governance_seal.timestamp > 0


# ── Intent Binding Tests ───────────────────────────────────────────


class TestIntentBinding:
    """Test intent_ref and normalization_id computation."""

    @pytest.mark.asyncio
    async def test_intent_ref_equals_sha256_of_serialized_request(
        self, engine_with_seal, basic_request, basic_ctx
    ):
        """intent_ref should equal SHA-256 of deterministically serialized request."""
        decision = await engine_with_seal.evaluate(basic_request, basic_ctx)

        expected_serialized = CryptoService.deterministic_serialize(basic_request)
        expected_intent_ref = CryptoService.sha256(expected_serialized)
        assert decision.intent_ref == expected_intent_ref

    @pytest.mark.asyncio
    async def test_normalization_id_equals_sha256_of_normalized_request(
        self, engine_with_seal, basic_request, basic_ctx
    ):
        """normalization_id should equal SHA-256 of normalized request."""
        decision = await engine_with_seal.evaluate(basic_request, basic_ctx)

        expected_normalized = CryptoService.normalize_payload(basic_request)
        expected_normalization_id = CryptoService.sha256(expected_normalized)
        assert decision.normalization_id == expected_normalization_id

    @pytest.mark.asyncio
    async def test_different_requests_produce_different_intent_refs(
        self, engine_with_seal, basic_ctx
    ):
        """Different request payloads must produce different intent_refs."""
        request_a = {"action": "read", "path": "/a"}
        request_b = {"action": "write", "path": "/b"}

        decision_a = await engine_with_seal.evaluate(request_a, basic_ctx)
        decision_b = await engine_with_seal.evaluate(request_b, basic_ctx)

        assert decision_a.intent_ref != decision_b.intent_ref


# ── Sequence Counter Tests ─────────────────────────────────────────


class TestSequenceCounters:
    """Test seq and running_count assignment."""

    @pytest.mark.asyncio
    async def test_first_decision_has_seq_1(
        self, engine_with_seal, basic_request, basic_ctx
    ):
        """First decision for an agent starts with seq=1."""
        decision = await engine_with_seal.evaluate(basic_request, basic_ctx)
        assert decision.seq == 1

    @pytest.mark.asyncio
    async def test_sequential_decisions_increment_seq(
        self, engine_with_seal, basic_request, basic_ctx
    ):
        """Sequential evaluations increment seq monotonically."""
        d1 = await engine_with_seal.evaluate(basic_request, basic_ctx)
        d2 = await engine_with_seal.evaluate(basic_request, basic_ctx)
        d3 = await engine_with_seal.evaluate(basic_request, basic_ctx)

        assert d1.seq == 1
        assert d2.seq == 2
        assert d3.seq == 3

    @pytest.mark.asyncio
    async def test_running_count_increments_globally(
        self, engine_with_seal, basic_request, basic_ctx
    ):
        """running_count increments globally across all evaluations."""
        d1 = await engine_with_seal.evaluate(basic_request, basic_ctx)
        d2 = await engine_with_seal.evaluate(basic_request, basic_ctx)

        assert d1.running_count == 1
        assert d2.running_count == 2

    @pytest.mark.asyncio
    async def test_multi_agent_independent_seq(self, basic_request):
        """Different agents have independent seq counters."""
        opts = GovernanceEngineV21Options(seal_secret="secret")
        engine = GovernanceEngineV21(opts)

        ctx_a = {"correlation_id": "c1", "agent_id": "agent-a"}
        ctx_b = {"correlation_id": "c2", "agent_id": "agent-b"}

        da1 = await engine.evaluate(basic_request, ctx_a)
        db1 = await engine.evaluate(basic_request, ctx_b)
        da2 = await engine.evaluate(basic_request, ctx_a)

        assert da1.seq == 1
        assert db1.seq == 1
        assert da2.seq == 2

    @pytest.mark.asyncio
    async def test_multi_agent_shared_running_count(self, basic_request):
        """running_count is shared across all agents."""
        opts = GovernanceEngineV21Options(seal_secret="secret")
        engine = GovernanceEngineV21(opts)

        ctx_a = {"correlation_id": "c1", "agent_id": "agent-a"}
        ctx_b = {"correlation_id": "c2", "agent_id": "agent-b"}

        da1 = await engine.evaluate(basic_request, ctx_a)
        db1 = await engine.evaluate(basic_request, ctx_b)
        da2 = await engine.evaluate(basic_request, ctx_a)

        assert da1.running_count == 1
        assert db1.running_count == 2
        assert da2.running_count == 3


# ── Receipt Chain Tests ────────────────────────────────────────────


class TestReceiptChain:
    """Test receipt_ref hash-chain linking."""

    @pytest.mark.asyncio
    async def test_first_decision_chains_from_genesis(
        self, engine_with_seal, basic_request, basic_ctx
    ):
        """First decision's receipt_ref is computed using GENESIS_RECEIPT_REF."""
        decision = await engine_with_seal.evaluate(basic_request, basic_ctx)

        # Manually recompute: partial decision dict without receipt_ref/governance_seal
        decision_dict = asdict(decision)
        decision_dict.pop("receipt_ref", None)
        decision_dict.pop("governance_seal", None)
        payload = CryptoService.deterministic_serialize(decision_dict)
        expected = CryptoService.sha256(payload + GENESIS_RECEIPT_REF)

        assert decision.receipt_ref == expected

    @pytest.mark.asyncio
    async def test_second_decision_chains_from_first(
        self, engine_with_seal, basic_request, basic_ctx
    ):
        """Second decision's receipt_ref chains from first decision's receipt_ref."""
        d1 = await engine_with_seal.evaluate(basic_request, basic_ctx)
        d2 = await engine_with_seal.evaluate(basic_request, basic_ctx)

        # Recompute expected receipt_ref for d2 using d1.receipt_ref
        d2_dict = asdict(d2)
        d2_dict.pop("receipt_ref", None)
        d2_dict.pop("governance_seal", None)
        payload = CryptoService.deterministic_serialize(d2_dict)
        expected = CryptoService.sha256(payload + d1.receipt_ref)

        assert d2.receipt_ref == expected

    @pytest.mark.asyncio
    async def test_receipt_refs_are_unique_per_decision(
        self, engine_with_seal, basic_request, basic_ctx
    ):
        """Each decision in a chain has a unique receipt_ref."""
        d1 = await engine_with_seal.evaluate(basic_request, basic_ctx)
        d2 = await engine_with_seal.evaluate(basic_request, basic_ctx)
        d3 = await engine_with_seal.evaluate(basic_request, basic_ctx)

        receipt_refs = {d1.receipt_ref, d2.receipt_ref, d3.receipt_ref}
        assert len(receipt_refs) == 3


# ── GovernanceSeal Tests ───────────────────────────────────────────


class TestGovernanceSeal:
    """Test GovernanceSeal HMAC computation."""

    @pytest.mark.asyncio
    async def test_seal_is_reproducible(self, basic_request, basic_ctx):
        """Governance seal HMAC can be independently recomputed from decision fields."""
        opts = GovernanceEngineV21Options(
            seal_secret="my-secret", agent_id="agent-x"
        )
        engine = GovernanceEngineV21(opts)
        decision = await engine.evaluate(basic_request, basic_ctx)

        # Recompute seal
        seal = decision.governance_seal
        decision_dict = asdict(decision)
        decision_dict.pop("governance_seal", None)
        payload = CryptoService.deterministic_serialize(decision_dict)
        hmac_input = payload + str(seal.timestamp) + seal.agent_id
        expected_hmac = CryptoService.hmac_sha256("my-secret", hmac_input)

        assert seal.hmac == expected_hmac

    @pytest.mark.asyncio
    async def test_seal_agent_id_matches_context(self, basic_request):
        """GovernanceSeal agent_id reflects the resolved agent identity."""
        opts = GovernanceEngineV21Options(seal_secret="s", agent_id="default-agent")
        engine = GovernanceEngineV21(opts)

        # Context agent_id takes priority
        ctx = {"correlation_id": "c", "agent_id": "ctx-agent"}
        decision = await engine.evaluate(basic_request, ctx)
        assert decision.governance_seal.agent_id == "ctx-agent"

    @pytest.mark.asyncio
    async def test_seal_uses_default_agent_id_when_ctx_missing(self, basic_request):
        """When ctx has no agent_id, falls back to options.agent_id."""
        opts = GovernanceEngineV21Options(seal_secret="s", agent_id="opts-agent")
        engine = GovernanceEngineV21(opts)

        ctx = {"correlation_id": "c"}
        decision = await engine.evaluate(basic_request, ctx)
        assert decision.governance_seal.agent_id == "opts-agent"

    @pytest.mark.asyncio
    async def test_seal_uses_default_when_no_agent_id_anywhere(self, basic_request):
        """When no agent_id in ctx or options, uses 'default'."""
        opts = GovernanceEngineV21Options(seal_secret="s")
        engine = GovernanceEngineV21(opts)

        ctx = {"correlation_id": "c"}
        decision = await engine.evaluate(basic_request, ctx)
        assert decision.governance_seal.agent_id == "default"

    @pytest.mark.asyncio
    async def test_different_secrets_produce_different_seals(
        self, basic_request, basic_ctx
    ):
        """Different seal_secrets produce different HMAC values."""
        opts_a = GovernanceEngineV21Options(seal_secret="secret-a")
        opts_b = GovernanceEngineV21Options(seal_secret="secret-b")
        engine_a = GovernanceEngineV21(opts_a)
        engine_b = GovernanceEngineV21(opts_b)

        d_a = await engine_a.evaluate(basic_request, basic_ctx)
        d_b = await engine_b.evaluate(basic_request, basic_ctx)

        # Different secrets → different HMACs (timestamps may differ too,
        # but even with same timestamp, HMAC would differ)
        assert d_a.governance_seal.hmac != d_b.governance_seal.hmac


# ── Base Decision Fields Tests ─────────────────────────────────────


class TestBaseDecisionFields:
    """Test that base decision fields are correctly populated."""

    @pytest.mark.asyncio
    async def test_correlation_id_from_context(
        self, engine_with_seal, basic_request
    ):
        """correlation_id is taken from ctx."""
        ctx = {"correlation_id": "my-correlation-123"}
        decision = await engine_with_seal.evaluate(basic_request, ctx)
        assert decision.correlation_id == "my-correlation-123"

    @pytest.mark.asyncio
    async def test_mode_from_options(self, basic_request, basic_ctx):
        """mode field reflects the engine's configured mode."""
        opts = GovernanceEngineV21Options(seal_secret="s", mode="MONITOR")
        engine = GovernanceEngineV21(opts)
        decision = await engine.evaluate(basic_request, basic_ctx)
        assert decision.mode == "MONITOR"

    @pytest.mark.asyncio
    async def test_policy_id_and_version(
        self, engine_with_seal, basic_request, basic_ctx
    ):
        """policy_id and policy_version are set to v1.2 governance defaults."""
        decision = await engine_with_seal.evaluate(basic_request, basic_ctx)
        assert decision.policy_id == "v1.2-governance"
        assert decision.policy_version == "1.2.0"

    @pytest.mark.asyncio
    async def test_module_name(self, engine_with_seal, basic_request, basic_ctx):
        """module field is 'GovernanceEngineV21'."""
        decision = await engine_with_seal.evaluate(basic_request, basic_ctx)
        assert decision.module == "GovernanceEngineV21"

    @pytest.mark.asyncio
    async def test_timestamp_is_reasonable(
        self, engine_with_seal, basic_request, basic_ctx
    ):
        """timestamp is a reasonable Unix ms value (recent)."""
        before = int(time.time() * 1000)
        decision = await engine_with_seal.evaluate(basic_request, basic_ctx)
        after = int(time.time() * 1000)

        assert before <= decision.timestamp <= after


# ── Counter Manager Access ─────────────────────────────────────────


class TestCounterManagerAccess:
    """Test that get_counter_manager() exposes internal state."""

    def test_get_counter_manager_returns_instance(self, engine_with_seal):
        """get_counter_manager() returns the internal CounterManager."""
        cm = engine_with_seal.get_counter_manager()
        assert isinstance(cm, CounterManager)

    @pytest.mark.asyncio
    async def test_counter_manager_reflects_evaluations(
        self, engine_with_seal, basic_request, basic_ctx
    ):
        """Counter manager state reflects evaluations performed."""
        await engine_with_seal.evaluate(basic_request, basic_ctx)
        cm = engine_with_seal.get_counter_manager()

        assert cm.current_seq("agent-alpha") == 1
        assert cm.current_running_count() == 1
