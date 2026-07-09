"""Property test: Decision Chain Contiguity.

**Validates: Requirements 5.3, 9.6**

Property 5: For any pipeline execution with TEEC v2.1 enabled (seal_secret
configured), the decisions array SHALL pass verify_contiguity() — seq values
are monotonically increasing and each receipt_ref correctly chains to the
previous decision.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from tealtiger.pipeline.stage_decision_builder import StageDecisionBuilder, StageDecisionBuildParams
from tealtiger.pipeline.types import ModuleEvalDetail, PipelineStage


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate random seal secrets (non-empty strings)
seal_secrets = st.text(min_size=8, max_size=32, alphabet="abcdefghijklmnopqrstuvwxyz0123456789")

# Generate random agent IDs
agent_ids = st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_-0123456789")

# Generate random payloads (simple JSON-compatible dicts) — kept small for performance
payloads = st.fixed_dictionaries(
    {"key": st.text(min_size=1, max_size=10, alphabet="abcdefgh")},
    optional={"val": st.integers(min_value=-100, max_value=100)},
)

# Generate random actions
actions = st.sampled_from(["ALLOW", "DENY", "MONITOR", "REDACT"])


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestDecisionChainContiguity:
    """Property 5: Decision Chain Contiguity.

    Chains built by StageDecisionBuilder always pass verify_contiguity().
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        seal_secret=seal_secrets,
        agent_id=agent_ids,
        pre_payload=payloads,
        post_payload=payloads,
        pre_action=actions,
        post_action=actions,
    )
    def test_two_stage_chain_verifies(
        self,
        seal_secret: str,
        agent_id: str,
        pre_payload: Dict[str, Any],
        post_payload: Dict[str, Any],
        pre_action: str,
        post_action: str,
    ) -> None:
        """A PRE + POST decision chain always passes contiguity verification."""
        builder = StageDecisionBuilder(seal_secret=seal_secret, agent_id=agent_id)

        # Build pre-execution decision
        pre_decision = builder.build(
            StageDecisionBuildParams(
                action=pre_action,
                reason_codes=["PRE_REASON"],
                stage=PipelineStage.PRE_EXECUTION,
                latency_ms=10.0,
                module_details=[
                    ModuleEvalDetail(
                        name="test_mod",
                        version="1.0.0",
                        latency_ms=5.0,
                        action=pre_action,
                        reason_codes=["PRE_REASON"],
                    )
                ],
                payload=pre_payload,
            )
        )

        # Build post-execution decision
        post_decision = builder.build(
            StageDecisionBuildParams(
                action=post_action,
                reason_codes=["POST_REASON"],
                stage=PipelineStage.POST_EXECUTION,
                latency_ms=15.0,
                module_details=[
                    ModuleEvalDetail(
                        name="test_mod_post",
                        version="1.0.0",
                        latency_ms=8.0,
                        action=post_action,
                        reason_codes=["POST_REASON"],
                    )
                ],
                payload=post_payload,
            )
        )

        # Verify contiguity
        decisions = [pre_decision, post_decision]
        result = builder.verify_contiguity(decisions)

        assert result.valid is True, (
            f"Contiguity verification failed: {result.error}. "
            f"seal_secret={seal_secret!r}, agent_id={agent_id!r}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        seal_secret=seal_secrets,
        agent_id=agent_ids,
        payload=payloads,
        action=actions,
    )
    def test_single_decision_verifies(
        self,
        seal_secret: str,
        agent_id: str,
        payload: Dict[str, Any],
        action: str,
    ) -> None:
        """A single decision chain always passes contiguity verification."""
        builder = StageDecisionBuilder(seal_secret=seal_secret, agent_id=agent_id)

        decision = builder.build(
            StageDecisionBuildParams(
                action=action,
                reason_codes=["REASON"],
                stage=PipelineStage.PRE_EXECUTION,
                latency_ms=5.0,
                module_details=[],
                payload=payload,
            )
        )

        result = builder.verify_contiguity([decision])
        assert result.valid is True, (
            f"Single decision contiguity failed: {result.error}"
        )

    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(
        seal_secret=seal_secrets,
        agent_id=agent_ids,
        num_decisions=st.integers(min_value=2, max_value=6),
        payload=payloads,
    )
    def test_multi_decision_chain_verifies(
        self,
        seal_secret: str,
        agent_id: str,
        num_decisions: int,
        payload: Dict[str, Any],
    ) -> None:
        """Chains of N decisions (built sequentially) always verify."""
        builder = StageDecisionBuilder(seal_secret=seal_secret, agent_id=agent_id)
        decisions = []

        stages = [PipelineStage.PRE_EXECUTION, PipelineStage.POST_EXECUTION]

        for i in range(num_decisions):
            stage = stages[i % 2]
            decision = builder.build(
                StageDecisionBuildParams(
                    action="ALLOW",
                    reason_codes=[f"REASON_{i}"],
                    stage=stage,
                    latency_ms=float(i + 1),
                    module_details=[],
                    payload={**payload, "_seq": i},
                )
            )
            decisions.append(decision)

        result = builder.verify_contiguity(decisions)
        assert result.valid is True, (
            f"Multi-decision chain (n={num_decisions}) contiguity failed: {result.error}"
        )

    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(
        seal_secret=seal_secrets,
        agent_id=agent_ids,
        pre_payload=payloads,
        post_payload=payloads,
    )
    def test_seq_is_monotonically_increasing(
        self,
        seal_secret: str,
        agent_id: str,
        pre_payload: Dict[str, Any],
        post_payload: Dict[str, Any],
    ) -> None:
        """seq values in a chain are strictly increasing."""
        builder = StageDecisionBuilder(seal_secret=seal_secret, agent_id=agent_id)

        d1 = builder.build(
            StageDecisionBuildParams(
                action="ALLOW",
                reason_codes=[],
                stage=PipelineStage.PRE_EXECUTION,
                latency_ms=1.0,
                module_details=[],
                payload=pre_payload,
            )
        )
        d2 = builder.build(
            StageDecisionBuildParams(
                action="DENY",
                reason_codes=[],
                stage=PipelineStage.POST_EXECUTION,
                latency_ms=2.0,
                module_details=[],
                payload=post_payload,
            )
        )

        assert d1.seq is not None
        assert d2.seq is not None
        assert d2.seq > d1.seq, (
            f"seq must be monotonically increasing: d1.seq={d1.seq}, d2.seq={d2.seq}"
        )
