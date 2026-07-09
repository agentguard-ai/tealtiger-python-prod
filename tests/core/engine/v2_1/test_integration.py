"""Integration tests for the full TEEC v2.1 governance pipeline.

Tests the end-to-end flow: evaluate → validate → verify_contiguity
across single-agent, multi-agent, and ObserveProxy scenarios.

Validates: Requirements 1.7, 5.1, 6.7, 8.7
"""

from __future__ import annotations

import pytest

from tealtiger.core.engine.v2_1 import (
    GovernanceEngineV21,
    GovernanceEngineV21Options,
    validate_governance_decision,
    verify_contiguity,
    ValidationContext,
)

SEAL_SECRET = "integration-test-secret-key"


class TestFullPipeline:
    """Test full pipeline: evaluate → validate → verify_contiguity."""

    @pytest.mark.asyncio
    async def test_single_decision_passes_validation_and_contiguity(self):
        """A single evaluated decision should pass both validation and contiguity."""
        engine = GovernanceEngineV21(
            GovernanceEngineV21Options(
                seal_secret=SEAL_SECRET,
                agent_id="agent-integ-001",
            )
        )

        request = {"action": "chat.create", "model": "gpt-4", "prompt": "Hello"}
        ctx = {"correlation_id": "integ-corr-001"}

        # Step 1: Evaluate
        decision = await engine.evaluate(request, ctx)

        # Verify basic v2.1 fields are populated
        assert decision.teec_version == "2.1"
        assert len(decision.intent_ref) == 64
        assert len(decision.receipt_ref) == 64
        assert decision.seq == 1
        assert decision.running_count == 1
        assert len(decision.normalization_id) == 64
        assert decision.governance_seal is not None
        assert len(decision.governance_seal.hmac) == 64

        # Step 2: Validate
        validation_context = ValidationContext(
            request_payload=request,
            seal_secret=SEAL_SECRET,
            reference_time=decision.governance_seal.timestamp,
            timestamp_tolerance_ms=60000,
        )
        validation_result = validate_governance_decision(decision, validation_context)
        assert validation_result.valid is True
        assert validation_result.receipt_ref == decision.receipt_ref
        assert validation_result.intent_ref == decision.intent_ref

        # Step 3: Verify contiguity (single decision is trivially contiguous)
        contiguity_result = verify_contiguity([decision])
        assert contiguity_result.valid is True
        assert contiguity_result.count == 1

    @pytest.mark.asyncio
    async def test_multi_decision_chain_passes_validation_and_contiguity(self):
        """A chain of 5 decisions should all pass validation and contiguity."""
        engine = GovernanceEngineV21(
            GovernanceEngineV21Options(
                seal_secret=SEAL_SECRET,
                agent_id="agent-chain-001",
            )
        )

        requests = [
            {"action": "chat.create", "prompt": "First request"},
            {"action": "tool.execute", "tool": "read_file", "path": "/tmp/a"},
            {"action": "chat.create", "prompt": "Second request"},
            {"action": "tool.execute", "tool": "write_file", "path": "/tmp/b"},
            {"action": "chat.create", "prompt": "Third request"},
        ]

        decisions = []

        for i, request in enumerate(requests):
            decision = await engine.evaluate(request, {"correlation_id": f"chain-corr-{i}"})

            # Validate each decision individually
            validation_context = ValidationContext(
                request_payload=request,
                seal_secret=SEAL_SECRET,
                reference_time=decision.governance_seal.timestamp,
            )
            validation_result = validate_governance_decision(decision, validation_context)
            assert validation_result.valid is True, (
                f"Decision {i} failed validation: {validation_result}"
            )

            decisions.append(decision)

        # Verify the full chain is contiguous
        contiguity_result = verify_contiguity(decisions)
        assert contiguity_result.valid is True
        assert contiguity_result.count == 5

        # Verify seq forms [1, 2, 3, 4, 5]
        seqs = [d.seq for d in decisions]
        assert seqs == [1, 2, 3, 4, 5]

        # Verify running_count forms [1, 2, 3, 4, 5]
        running_counts = [d.running_count for d in decisions]
        assert running_counts == [1, 2, 3, 4, 5]


class TestMultiAgentScenario:
    """Test multi-agent scenario with interleaved evaluations."""

    @pytest.mark.asyncio
    async def test_per_agent_contiguity_and_global_running_count(self):
        """Two agents, interleaved evaluations — verify per-agent contiguity and global running_count."""
        engine = GovernanceEngineV21(
            GovernanceEngineV21Options(seal_secret=SEAL_SECRET)
        )

        all_decisions = []
        agent_a_decisions = []
        agent_b_decisions = []

        # Interleave evaluations between agent-a and agent-b (3 each)
        evaluations = [
            {"agent_id": "agent-a", "request": {"action": "read", "file": "/a1"}},
            {"agent_id": "agent-b", "request": {"action": "write", "file": "/b1"}},
            {"agent_id": "agent-a", "request": {"action": "read", "file": "/a2"}},
            {"agent_id": "agent-b", "request": {"action": "write", "file": "/b2"}},
            {"agent_id": "agent-a", "request": {"action": "read", "file": "/a3"}},
            {"agent_id": "agent-b", "request": {"action": "write", "file": "/b3"}},
        ]

        for i, evaluation in enumerate(evaluations):
            agent_id = evaluation["agent_id"]
            request = evaluation["request"]
            decision = await engine.evaluate(
                request, {"correlation_id": f"multi-{i}", "agent_id": agent_id}
            )

            all_decisions.append(decision)
            if agent_id == "agent-a":
                agent_a_decisions.append(decision)
            else:
                agent_b_decisions.append(decision)

        # Verify global running_count forms [1, 2, 3, 4, 5, 6]
        running_counts = [d.running_count for d in all_decisions]
        assert running_counts == [1, 2, 3, 4, 5, 6]

        # Verify per-agent seq for agent-a: [1, 2, 3]
        agent_a_seqs = [d.seq for d in agent_a_decisions]
        assert agent_a_seqs == [1, 2, 3]

        # Verify per-agent seq for agent-b: [1, 2, 3]
        agent_b_seqs = [d.seq for d in agent_b_decisions]
        assert agent_b_seqs == [1, 2, 3]

        # Verify per-agent contiguity for agent-a (filtered)
        contiguity_a = verify_contiguity(all_decisions, agent_id="agent-a")
        assert contiguity_a.valid is True
        assert contiguity_a.count == 3

        # Verify per-agent contiguity for agent-b (filtered)
        contiguity_b = verify_contiguity(all_decisions, agent_id="agent-b")
        assert contiguity_b.valid is True
        assert contiguity_b.count == 3

        # Validate each decision individually
        for i, evaluation in enumerate(evaluations):
            decision = all_decisions[i]
            validation_context = ValidationContext(
                request_payload=evaluation["request"],
                seal_secret=SEAL_SECRET,
                reference_time=decision.governance_seal.timestamp,
            )
            result = validate_governance_decision(decision, validation_context)
            assert result.valid is True, (
                f"Decision {i} (agent={evaluation['agent_id']}) failed: {result}"
            )


class TestObserveProxyGovernance:
    """Test ObserveProxy governance behavior (simulated via GovernanceEngineV21)."""

    @pytest.mark.asyncio
    async def test_three_sequential_calls_pass_validation_and_contiguity(self):
        """3 sequential calls should produce valid decisions that pass contiguity."""
        # Simulate ObserveProxy governance using GovernanceEngineV21 directly.
        # The ObserveProxy with governance: true internally uses the same pipeline.
        engine = GovernanceEngineV21(
            GovernanceEngineV21Options(
                seal_secret=SEAL_SECRET,
                agent_id="observe-proxy-agent",
            )
        )

        calls = [
            {
                "action": "chat.completions.create",
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            {
                "action": "chat.completions.create",
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "World"}],
            },
            {
                "action": "chat.completions.create",
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "Test"}],
            },
        ]

        decisions = []

        for i, call in enumerate(calls):
            decision = await engine.evaluate(call, {"correlation_id": f"observe-{i}"})
            decisions.append(decision)

        # Verify all decisions have the correct agent_id in their seal
        for decision in decisions:
            assert decision.governance_seal.agent_id == "observe-proxy-agent"

        # Verify each decision passes validation
        for i, call in enumerate(calls):
            validation_context = ValidationContext(
                request_payload=call,
                seal_secret=SEAL_SECRET,
                reference_time=decisions[i].governance_seal.timestamp,
            )
            result = validate_governance_decision(decisions[i], validation_context)
            assert result.valid is True, f"Decision {i} failed validation: {result}"

        # Verify contiguity of the full chain
        contiguity_result = verify_contiguity(decisions)
        assert contiguity_result.valid is True
        assert contiguity_result.count == 3

        # Verify seq is [1, 2, 3]
        seqs = [d.seq for d in decisions]
        assert seqs == [1, 2, 3]

        # Verify running_count is [1, 2, 3]
        running_counts = [d.running_count for d in decisions]
        assert running_counts == [1, 2, 3]
