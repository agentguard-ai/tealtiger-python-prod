"""Property test: Resample Budget Bound.

**Validates: Requirements 4.5, 4.6**

Property 4: For any pipeline with resample_budget=N, the total number of
provider invocations SHALL NOT exceed N+1, and resample_count in the result
SHALL NOT exceed N.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tealtiger.pipeline.remediation_handler import RemediationHandler
from tealtiger.pipeline.types import (
    PipelineRequest,
    PipelineStage,
)


# ---------------------------------------------------------------------------
# Helpers: Always-failing evaluator and provider mocks
# ---------------------------------------------------------------------------


@dataclass
class MockExecutionResult:
    """Mimics ExecutionResult from execution_stage."""

    success: bool = True
    response: Any = None
    metadata: Any = None
    error: Any = None


class AlwaysFailingPostEvaluator:
    """A post-stage evaluator that always returns DENY."""

    def __init__(self) -> None:
        self.call_count = 0

    async def evaluate(
        self,
        modules: List[Any],
        request: Any,
        ctx: Any,
        policy: Any,
    ) -> Any:
        self.call_count += 1

        @dataclass
        class Result:
            action: str = "DENY"
            reason_codes: List[str] = None  # type: ignore
            module_details: List[Any] = None  # type: ignore
            latency_ms: float = 1.0

            def __post_init__(self):
                if self.reason_codes is None:
                    self.reason_codes = ["ALWAYS_FAIL"]
                if self.module_details is None:
                    self.module_details = []

        return Result()


class CountingExecutionStage:
    """A mock execution stage that counts provider calls."""

    def __init__(self) -> None:
        self.call_count = 0

    async def execute(self, request: PipelineRequest) -> MockExecutionResult:
        self.call_count += 1
        return MockExecutionResult(
            success=True,
            response={"content": f"response_{self.call_count}"},
        )


class FailingExecutionStage:
    """A mock execution stage that always fails (provider error)."""

    def __init__(self) -> None:
        self.call_count = 0

    async def execute(self, request: PipelineRequest) -> MockExecutionResult:
        self.call_count += 1
        return MockExecutionResult(
            success=False,
            response=None,
            error={"message": "provider error", "code": "500"},
        )


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestResampleBudgetBound:
    """Property 4: Resample Budget Bound.

    The resample loop never exceeds the configured budget.
    """

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(budget=st.integers(min_value=0, max_value=10))
    async def test_resample_count_never_exceeds_budget(
        self,
        budget: int,
    ) -> None:
        """resample_count <= budget for any budget value."""
        handler = RemediationHandler(resample_budget=budget)
        execution_stage = CountingExecutionStage()
        post_evaluator = AlwaysFailingPostEvaluator()

        request = PipelineRequest(payload={"content": "test"})

        result = await handler.execute_resample_loop(
            request=request,
            execution_stage=execution_stage,
            post_stage_evaluator=post_evaluator,
            modules=[],
            ctx={},
            policy=None,
            current_attempt=0,
        )

        assert result.resample_count <= budget, (
            f"resample_count ({result.resample_count}) exceeded budget ({budget})"
        )

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(budget=st.integers(min_value=0, max_value=10))
    async def test_provider_calls_never_exceed_budget(
        self,
        budget: int,
    ) -> None:
        """Provider call count <= budget (within the resample loop only)."""
        handler = RemediationHandler(resample_budget=budget)
        execution_stage = CountingExecutionStage()
        post_evaluator = AlwaysFailingPostEvaluator()

        request = PipelineRequest(payload={"content": "test"})

        await handler.execute_resample_loop(
            request=request,
            execution_stage=execution_stage,
            post_stage_evaluator=post_evaluator,
            modules=[],
            ctx={},
            policy=None,
            current_attempt=0,
        )

        # Provider calls in the resample loop should not exceed budget
        assert execution_stage.call_count <= budget, (
            f"Provider calls ({execution_stage.call_count}) exceeded budget ({budget})"
        )

    @pytest.mark.asyncio
    @settings(max_examples=50)
    @given(budget=st.integers(min_value=1, max_value=10))
    async def test_budget_exhausted_when_always_failing(
        self,
        budget: int,
    ) -> None:
        """When post-evaluation always fails, budget is exhausted."""
        handler = RemediationHandler(resample_budget=budget)
        execution_stage = CountingExecutionStage()
        post_evaluator = AlwaysFailingPostEvaluator()

        request = PipelineRequest(payload={"content": "test"})

        result = await handler.execute_resample_loop(
            request=request,
            execution_stage=execution_stage,
            post_stage_evaluator=post_evaluator,
            modules=[],
            ctx={},
            policy=None,
            current_attempt=0,
        )

        assert result.exhausted is True, "Budget should be exhausted when always failing"
        assert result.success is False, "Result should not be success when exhausted"
        assert result.resample_count == budget, (
            f"Should have used exactly {budget} attempts, got {result.resample_count}"
        )

    @pytest.mark.asyncio
    @settings(max_examples=50)
    @given(budget=st.integers(min_value=0, max_value=10))
    async def test_provider_errors_still_respect_budget(
        self,
        budget: int,
    ) -> None:
        """Even when the provider fails, budget is still respected."""
        handler = RemediationHandler(resample_budget=budget)
        execution_stage = FailingExecutionStage()
        post_evaluator = AlwaysFailingPostEvaluator()

        request = PipelineRequest(payload={"content": "test"})

        result = await handler.execute_resample_loop(
            request=request,
            execution_stage=execution_stage,
            post_stage_evaluator=post_evaluator,
            modules=[],
            ctx={},
            policy=None,
            current_attempt=0,
        )

        assert result.resample_count <= budget, (
            f"resample_count ({result.resample_count}) exceeded budget ({budget}) "
            f"even with provider errors"
        )
        assert execution_stage.call_count <= budget, (
            f"Provider calls ({execution_stage.call_count}) exceeded budget ({budget})"
        )
