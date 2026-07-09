"""Property test: MostRestrictiveWins Merge Correctness.

**Validates: Requirements 2.2, 4.2**

Property 3: For any set of module results at any stage, the merged action
SHALL be the most restrictive action present according to the severity
ordering. If any result is DENY, merged is DENY. If no DENY but any MONITOR,
merged is MONITOR. Otherwise ALLOW.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tealtiger.pipeline.stage_evaluator import StageEvaluator
from tealtiger.pipeline.types import ACTION_SEVERITY, PipelineStage


# ---------------------------------------------------------------------------
# Helpers: Configurable mock module
# ---------------------------------------------------------------------------


class ConfigurableModule:
    """A module that returns a configured action."""

    def __init__(self, name: str, action: str) -> None:
        self.name = name
        self.version = "1.0.0"
        self._action = action

    async def evaluate(self, request: Any, ctx: Any, policy: Any) -> Dict[str, Any]:
        return {
            "action": self._action,
            "reason_codes": [f"{self._action}_REASON"],
            "event_type": "test",
        }


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# All action keys from ACTION_SEVERITY
ALL_ACTIONS = list(ACTION_SEVERITY.keys())

# Generate random action arrays (at least 1 action)
action_arrays = st.lists(
    st.sampled_from(ALL_ACTIONS),
    min_size=1,
    max_size=8,
)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestMostRestrictiveWins:
    """Property 3: MostRestrictiveWins Merge Correctness.

    The merged action is always the highest severity action present in
    the module results.
    """

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(
        actions=action_arrays,
        stage=st.sampled_from([PipelineStage.PRE_EXECUTION, PipelineStage.POST_EXECUTION]),
    )
    async def test_merged_action_is_highest_severity(
        self,
        actions: List[str],
        stage: PipelineStage,
    ) -> None:
        """The merged action always has the highest severity among all module results."""
        modules = [
            ConfigurableModule(name=f"mod_{i}", action=action)
            for i, action in enumerate(actions)
        ]

        evaluator = StageEvaluator(stage=stage, fail_closed=True, timeout_ms=5000)

        result = await evaluator.evaluate(
            modules=modules,
            request={"content": "test"},
            ctx={},
            policy=None,
        )

        # Compute expected: the action with the highest severity
        expected_severity = max(ACTION_SEVERITY.get(a, 0) for a in actions)
        actual_severity = ACTION_SEVERITY.get(result.action, 0)

        assert actual_severity == expected_severity, (
            f"Expected merged severity {expected_severity}, got {actual_severity} "
            f"(action={result.action}). Input actions: {actions}"
        )

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(
        actions=action_arrays,
    )
    async def test_deny_always_wins(
        self,
        actions: List[str],
    ) -> None:
        """If any action is DENY-level (severity >= 100), merged is DENY-level."""
        # Ensure at least one DENY in the mix
        actions_with_deny = actions + ["DENY"]
        modules = [
            ConfigurableModule(name=f"mod_{i}", action=action)
            for i, action in enumerate(actions_with_deny)
        ]

        evaluator = StageEvaluator(
            stage=PipelineStage.PRE_EXECUTION, fail_closed=True, timeout_ms=5000
        )

        result = await evaluator.evaluate(
            modules=modules,
            request={"content": "test"},
            ctx={},
            policy=None,
        )

        # DENY has severity 100 — must be the highest
        actual_severity = ACTION_SEVERITY.get(result.action, 0)
        assert actual_severity >= 100, (
            f"With DENY present, merged severity should be >= 100, "
            f"got {actual_severity} (action={result.action})"
        )

    @pytest.mark.asyncio
    @settings(max_examples=50)
    @given(
        num_allows=st.integers(min_value=1, max_value=5),
    )
    async def test_all_allow_merges_to_allow(
        self,
        num_allows: int,
    ) -> None:
        """If all modules return ALLOW, the merged result is ALLOW."""
        modules = [
            ConfigurableModule(name=f"allow_{i}", action="ALLOW")
            for i in range(num_allows)
        ]

        evaluator = StageEvaluator(
            stage=PipelineStage.PRE_EXECUTION, fail_closed=True, timeout_ms=5000
        )

        result = await evaluator.evaluate(
            modules=modules,
            request={"content": "test"},
            ctx={},
            policy=None,
        )

        assert result.action == "ALLOW", (
            f"All ALLOW modules should merge to ALLOW, got {result.action}"
        )
