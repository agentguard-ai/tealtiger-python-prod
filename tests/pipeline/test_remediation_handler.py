"""Tests for the RemediationHandler (Python SDK).

Verifies:
- select_action priority: RESAMPLE > REDACT > DENY_RESPONSE
- execute_resample_loop budget enforcement and success path
- apply_redaction delegation to module-provided functions
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from tealtiger.pipeline.remediation_handler import (
    RemediationHandler,
    RemediationResult,
)
from tealtiger.pipeline.types import (
    ACTION_SEVERITY,
    ModuleEvalDetail,
    PipelineRequest,
    RemediationAction,
)


# ---------------------------------------------------------------------------
# Helpers / Mocks
# ---------------------------------------------------------------------------


@dataclass
class MockExecutionResult:
    """Mimics ExecutionResult dataclass from execution_stage module."""

    success: bool
    response: Any = None
    metadata: Any = None
    error: Optional[Dict[str, str]] = None


@dataclass
class MockStageEvaluationResult:
    """Mimics StageEvaluationResult dataclass from stage_evaluator module."""

    action: str
    reason_codes: List[str]
    module_details: List[ModuleEvalDetail]
    latency_ms: float


class MockExecutionStage:
    """Mock execution stage that returns pre-configured responses."""

    def __init__(self, responses: List[MockExecutionResult]) -> None:
        self._responses = responses
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    async def execute(self, request: PipelineRequest) -> MockExecutionResult:
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return self._responses[idx]


class MockStageEvaluator:
    """Mock stage evaluator that returns pre-configured evaluation results."""

    def __init__(self, results: List[MockStageEvaluationResult]) -> None:
        self._results = results
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    async def evaluate(
        self, modules: List[Any], request: Any, ctx: Any, policy: Any
    ) -> MockStageEvaluationResult:
        idx = min(self._call_count, len(self._results) - 1)
        self._call_count += 1
        return self._results[idx]


def make_detail(
    action: str = "ALLOW",
    remediation: Optional[str] = None,
    name: str = "test-module",
) -> ModuleEvalDetail:
    """Helper to build ModuleEvalDetail with optional remediation metadata."""
    metadata = {"remediation": remediation} if remediation else None
    return ModuleEvalDetail(
        name=name,
        version="1.0.0",
        latency_ms=5.0,
        action=action,
        reason_codes=[],
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# select_action tests
# ---------------------------------------------------------------------------


class TestSelectAction:
    """Tests for RemediationHandler.select_action."""

    def test_returns_deny_response_when_no_modules_have_remediation(self):
        handler = RemediationHandler(resample_budget=2)
        details = [make_detail(action="DENY")]
        assert handler.select_action(details) == RemediationAction.DENY_RESPONSE

    def test_returns_resample_when_module_specifies_resample(self):
        handler = RemediationHandler(resample_budget=2)
        details = [make_detail(action="DENY", remediation="resample")]
        assert handler.select_action(details) == RemediationAction.RESAMPLE

    def test_returns_redact_when_module_specifies_redact(self):
        handler = RemediationHandler(resample_budget=2)
        details = [make_detail(action="DENY", remediation="redact")]
        assert handler.select_action(details) == RemediationAction.REDACT

    def test_resample_takes_priority_over_redact(self):
        handler = RemediationHandler(resample_budget=2)
        details = [
            make_detail(action="DENY", remediation="redact", name="mod-a"),
            make_detail(action="DENY", remediation="resample", name="mod-b"),
        ]
        assert handler.select_action(details) == RemediationAction.RESAMPLE

    def test_ignores_modules_below_deny_severity(self):
        handler = RemediationHandler(resample_budget=2)
        details = [
            make_detail(action="MONITOR", remediation="resample"),  # severity 10
            make_detail(action="DENY"),  # severity 100, no remediation
        ]
        assert handler.select_action(details) == RemediationAction.DENY_RESPONSE

    def test_handles_empty_module_details(self):
        handler = RemediationHandler(resample_budget=2)
        assert handler.select_action([]) == RemediationAction.DENY_RESPONSE

    def test_case_insensitive_remediation_value(self):
        handler = RemediationHandler(resample_budget=2)
        details = [make_detail(action="DENY", remediation="RESAMPLE")]
        assert handler.select_action(details) == RemediationAction.RESAMPLE

    def test_redact_severity_threshold(self):
        """REDACT action (severity 70) is considered DENY-level."""
        handler = RemediationHandler(resample_budget=2)
        details = [make_detail(action="REDACT", remediation="redact")]
        assert handler.select_action(details) == RemediationAction.REDACT

    def test_modules_with_no_metadata_ignored(self):
        handler = RemediationHandler(resample_budget=2)
        detail = ModuleEvalDetail(
            name="no-meta",
            version="1.0.0",
            latency_ms=5.0,
            action="DENY",
            reason_codes=[],
            metadata=None,
        )
        assert handler.select_action([detail]) == RemediationAction.DENY_RESPONSE


# ---------------------------------------------------------------------------
# execute_resample_loop tests
# ---------------------------------------------------------------------------


class TestExecuteResampleLoop:
    """Tests for RemediationHandler.execute_resample_loop."""

    @pytest.mark.asyncio
    async def test_success_on_first_resample(self):
        handler = RemediationHandler(resample_budget=3)

        exec_stage = MockExecutionStage([
            MockExecutionResult(success=True, response="good response"),
        ])
        eval_stage = MockStageEvaluator([
            MockStageEvaluationResult(
                action="ALLOW", reason_codes=[], module_details=[], latency_ms=5.0
            ),
        ])

        result = await handler.execute_resample_loop(
            request=PipelineRequest(payload={"content": "test"}),
            execution_stage=exec_stage,
            post_stage_evaluator=eval_stage,
            modules=[],
            ctx={},
            policy=None,
            current_attempt=0,
        )

        assert result.success is True
        assert result.response == "good response"
        assert result.resample_count == 1
        assert result.exhausted is False

    @pytest.mark.asyncio
    async def test_budget_exhausted(self):
        handler = RemediationHandler(resample_budget=2)

        exec_stage = MockExecutionStage([
            MockExecutionResult(success=True, response="bad response"),
        ])
        eval_stage = MockStageEvaluator([
            MockStageEvaluationResult(
                action="DENY", reason_codes=["VIOLATION"], module_details=[], latency_ms=5.0
            ),
        ])

        result = await handler.execute_resample_loop(
            request=PipelineRequest(payload={"content": "test"}),
            execution_stage=exec_stage,
            post_stage_evaluator=eval_stage,
            modules=[],
            ctx={},
            policy=None,
            current_attempt=0,
        )

        assert result.success is False
        assert result.response is None
        assert result.resample_count == 2
        assert result.exhausted is True
        assert exec_stage.call_count == 2

    @pytest.mark.asyncio
    async def test_success_on_second_attempt(self):
        handler = RemediationHandler(resample_budget=3)

        exec_stage = MockExecutionStage([
            MockExecutionResult(success=True, response="still bad"),
            MockExecutionResult(success=True, response="now good"),
        ])
        eval_stage = MockStageEvaluator([
            MockStageEvaluationResult(
                action="DENY", reason_codes=["VIOLATION"], module_details=[], latency_ms=5.0
            ),
            MockStageEvaluationResult(
                action="ALLOW", reason_codes=[], module_details=[], latency_ms=5.0
            ),
        ])

        result = await handler.execute_resample_loop(
            request=PipelineRequest(payload={"content": "test"}),
            execution_stage=exec_stage,
            post_stage_evaluator=eval_stage,
            modules=[],
            ctx={},
            policy=None,
            current_attempt=0,
        )

        assert result.success is True
        assert result.response == "now good"
        assert result.resample_count == 2
        assert result.exhausted is False

    @pytest.mark.asyncio
    async def test_provider_error_counts_as_failed_attempt(self):
        handler = RemediationHandler(resample_budget=2)

        exec_stage = MockExecutionStage([
            MockExecutionResult(success=False, response=None, error={"message": "fail"}),
            MockExecutionResult(success=True, response="recovered"),
        ])
        eval_stage = MockStageEvaluator([
            MockStageEvaluationResult(
                action="ALLOW", reason_codes=[], module_details=[], latency_ms=5.0
            ),
        ])

        result = await handler.execute_resample_loop(
            request=PipelineRequest(payload={"content": "test"}),
            execution_stage=exec_stage,
            post_stage_evaluator=eval_stage,
            modules=[],
            ctx={},
            policy=None,
            current_attempt=0,
        )

        assert result.success is True
        assert result.response == "recovered"
        assert result.resample_count == 2

    @pytest.mark.asyncio
    async def test_respects_current_attempt_offset(self):
        """Starting at current_attempt=1 with budget=2 leaves only 1 attempt."""
        handler = RemediationHandler(resample_budget=2)

        exec_stage = MockExecutionStage([
            MockExecutionResult(success=True, response="bad"),
        ])
        eval_stage = MockStageEvaluator([
            MockStageEvaluationResult(
                action="DENY", reason_codes=[], module_details=[], latency_ms=5.0
            ),
        ])

        result = await handler.execute_resample_loop(
            request=PipelineRequest(payload={"content": "test"}),
            execution_stage=exec_stage,
            post_stage_evaluator=eval_stage,
            modules=[],
            ctx={},
            policy=None,
            current_attempt=1,
        )

        assert result.success is False
        assert result.resample_count == 2
        assert result.exhausted is True
        assert exec_stage.call_count == 1


# ---------------------------------------------------------------------------
# apply_redaction tests
# ---------------------------------------------------------------------------


class TestApplyRedaction:
    """Tests for RemediationHandler.apply_redaction."""

    @pytest.mark.asyncio
    async def test_applies_sync_redaction_function(self):
        handler = RemediationHandler(resample_budget=2)

        def redact_fn(resp: str) -> str:
            return resp.replace("secret", "[REDACTED]")

        details = [
            ModuleEvalDetail(
                name="pii-scanner",
                version="1.0.0",
                latency_ms=5.0,
                action="DENY",
                reason_codes=["PII_DETECTED"],
                metadata={"remediation": "redact", "redact": redact_fn},
            ),
        ]

        result = await handler.apply_redaction("contains secret data", details)
        assert result == "contains [REDACTED] data"

    @pytest.mark.asyncio
    async def test_applies_async_redaction_function(self):
        handler = RemediationHandler(resample_budget=2)

        async def redact_fn(resp: str) -> str:
            return resp.replace("pii", "[REMOVED]")

        details = [
            ModuleEvalDetail(
                name="pii-scanner",
                version="1.0.0",
                latency_ms=5.0,
                action="DENY",
                reason_codes=["PII_DETECTED"],
                metadata={"remediation": "redact", "redact": redact_fn},
            ),
        ]

        result = await handler.apply_redaction("found pii here", details)
        assert result == "found [REMOVED] here"

    @pytest.mark.asyncio
    async def test_chains_multiple_redaction_functions(self):
        handler = RemediationHandler(resample_budget=2)

        def redact_a(resp: str) -> str:
            return resp.replace("aaa", "XXX")

        def redact_b(resp: str) -> str:
            return resp.replace("bbb", "YYY")

        details = [
            ModuleEvalDetail(
                name="mod-a",
                version="1.0.0",
                latency_ms=5.0,
                action="DENY",
                reason_codes=[],
                metadata={"redact": redact_a},
            ),
            ModuleEvalDetail(
                name="mod-b",
                version="1.0.0",
                latency_ms=5.0,
                action="REDACT",
                reason_codes=[],
                metadata={"redaction_fn": redact_b},
            ),
        ]

        result = await handler.apply_redaction("aaa and bbb", details)
        assert result == "XXX and YYY"

    @pytest.mark.asyncio
    async def test_returns_original_when_no_redaction_functions(self):
        handler = RemediationHandler(resample_budget=2)

        details = [
            ModuleEvalDetail(
                name="mod-no-fn",
                version="1.0.0",
                latency_ms=5.0,
                action="DENY",
                reason_codes=[],
                metadata={"remediation": "redact"},
            ),
        ]

        result = await handler.apply_redaction("original response", details)
        assert result == "original response"

    @pytest.mark.asyncio
    async def test_ignores_modules_below_deny_severity(self):
        handler = RemediationHandler(resample_budget=2)

        def should_not_be_called(resp: str) -> str:
            raise AssertionError("Should not be called")

        details = [
            ModuleEvalDetail(
                name="monitor-module",
                version="1.0.0",
                latency_ms=5.0,
                action="MONITOR",
                reason_codes=[],
                metadata={"redact": should_not_be_called},
            ),
        ]

        result = await handler.apply_redaction("unchanged", details)
        assert result == "unchanged"


# ---------------------------------------------------------------------------
# Constructor / property tests
# ---------------------------------------------------------------------------


class TestRemediationHandlerConstruction:
    """Tests for RemediationHandler construction and properties."""

    def test_resample_budget_property(self):
        handler = RemediationHandler(resample_budget=5)
        assert handler.resample_budget == 5

    def test_default_budget_behavior(self):
        handler = RemediationHandler(resample_budget=0)
        assert handler.resample_budget == 0
