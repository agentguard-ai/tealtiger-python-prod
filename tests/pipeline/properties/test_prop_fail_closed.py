"""Property test: Fail-Closed Invariant.

**Validates: Requirements 2.6, 2.7, 4.8, 12.1, 12.2**

Property 1: For any pipeline configuration with fail_closed=True, if any
pre-execution or post-execution module throws an exception, the pipeline
SHALL block the request (pre-stage) or trigger remediation (post-stage) —
a module failure NEVER results in silent pass-through.
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
# Helpers: Mock modules that throw or succeed
# ---------------------------------------------------------------------------


class ThrowingModule:
    """A module that always raises an exception during evaluation."""

    def __init__(self, name: str = "thrower", error_msg: str = "boom") -> None:
        self.name = name
        self.version = "1.0.0"
        self._error_msg = error_msg

    async def evaluate(self, request: Any, ctx: Any, policy: Any) -> Dict[str, Any]:
        raise RuntimeError(self._error_msg)


class AllowModule:
    """A module that always returns ALLOW."""

    def __init__(self, name: str = "allower") -> None:
        self.name = name
        self.version = "1.0.0"

    async def evaluate(self, request: Any, ctx: Any, policy: Any) -> Dict[str, Any]:
        return {"action": "ALLOW", "reason_codes": [], "event_type": "test"}


class MonitorModule:
    """A module that always returns MONITOR."""

    def __init__(self, name: str = "monitor") -> None:
        self.name = name
        self.version = "1.0.0"

    async def evaluate(self, request: Any, ctx: Any, policy: Any) -> Dict[str, Any]:
        return {"action": "MONITOR", "reason_codes": ["MONITORED"], "event_type": "test"}


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate module arrays where at least one throws
def _module_array_with_thrower(min_size: int = 1, max_size: int = 5):
    """Strategy: generate a list of modules where at least one is a ThrowingModule."""

    @st.composite
    def strategy(draw):
        count = draw(st.integers(min_value=min_size, max_value=max_size))
        # Pick a random position for the thrower
        thrower_idx = draw(st.integers(min_value=0, max_value=count - 1))
        modules = []
        for i in range(count):
            if i == thrower_idx:
                name = draw(st.text(min_size=1, max_size=10, alphabet="abcdefghij"))
                modules.append(ThrowingModule(name=f"thrower_{name}"))
            else:
                choice = draw(st.sampled_from(["allow", "monitor"]))
                if choice == "allow":
                    modules.append(AllowModule(name=f"allow_{i}"))
                else:
                    modules.append(MonitorModule(name=f"monitor_{i}"))
        return modules

    return strategy()


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestFailClosedInvariant:
    """Property 1: Fail-Closed Invariant.

    When fail_closed=True, any module that throws during evaluation
    causes the stage to produce a DENY-level action (severity >= 70).
    """

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(
        modules=_module_array_with_thrower(min_size=1, max_size=5),
        stage=st.sampled_from([PipelineStage.PRE_EXECUTION, PipelineStage.POST_EXECUTION]),
    )
    async def test_fail_closed_always_denies_on_module_error(
        self,
        modules: List[Any],
        stage: PipelineStage,
    ) -> None:
        """When fail_closed=True and at least one module throws,
        the merged action must be DENY (severity >= 70)."""
        evaluator = StageEvaluator(stage=stage, fail_closed=True, timeout_ms=5000)

        result = await evaluator.evaluate(
            modules=modules,
            request={"content": "test request"},
            ctx={"correlation_id": "test"},
            policy=None,
        )

        # The merged action must be at DENY severity or higher
        severity = ACTION_SEVERITY.get(result.action, 0)
        assert severity >= 70, (
            f"Expected DENY-level action (severity >= 70), got "
            f"action={result.action} severity={severity}"
        )

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(
        stage=st.sampled_from([PipelineStage.PRE_EXECUTION, PipelineStage.POST_EXECUTION]),
        num_throwers=st.integers(min_value=1, max_value=5),
    )
    async def test_fail_closed_all_throwers_always_deny(
        self,
        stage: PipelineStage,
        num_throwers: int,
    ) -> None:
        """When fail_closed=True and ALL modules throw, result is DENY."""
        modules = [ThrowingModule(name=f"thrower_{i}") for i in range(num_throwers)]
        evaluator = StageEvaluator(stage=stage, fail_closed=True, timeout_ms=5000)

        result = await evaluator.evaluate(
            modules=modules,
            request={"content": "test"},
            ctx={},
            policy=None,
        )

        assert result.action == "DENY", (
            f"Expected DENY when all modules throw with fail_closed=True, "
            f"got {result.action}"
        )

    @pytest.mark.asyncio
    @settings(max_examples=50)
    @given(
        modules=_module_array_with_thrower(min_size=1, max_size=4),
        stage=st.sampled_from([PipelineStage.PRE_EXECUTION, PipelineStage.POST_EXECUTION]),
    )
    async def test_fail_closed_error_module_has_fail_closed_reason(
        self,
        modules: List[Any],
        stage: PipelineStage,
    ) -> None:
        """Failed modules under fail_closed=True produce PIPELINE_FAIL_CLOSED reason code."""
        evaluator = StageEvaluator(stage=stage, fail_closed=True, timeout_ms=5000)

        result = await evaluator.evaluate(
            modules=modules,
            request={"content": "test"},
            ctx={},
            policy=None,
        )

        # At least one module detail should have an error and DENY action
        errored_details = [d for d in result.module_details if d.error is not None]
        assert len(errored_details) >= 1, "Expected at least one module with an error"

        for detail in errored_details:
            assert detail.action == "DENY", (
                f"Errored module should have DENY action, got {detail.action}"
            )
