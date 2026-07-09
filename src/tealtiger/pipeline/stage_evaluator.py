"""Multi-Stage Defense Pipeline — Stage Evaluator (Python SDK).

Responsible for parallel module evaluation within a single pipeline stage,
timeout enforcement per module, and result merging using MostRestrictiveWins.

Module: pipeline/stage_evaluator
Requirements: 11.2, 11.5, 11.6, 11.8
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from .errors import ModuleTimeoutError
from .types import ACTION_SEVERITY, ModuleEvalDetail, PipelineStage


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class TealModule(Protocol):
    """Protocol for governance modules compatible with the pipeline.

    Mirrors the TealModule interface from TealEngineV12 (v1.2 types).
    """

    @property
    def name(self) -> str:
        """Module name identifier."""
        ...

    @property
    def version(self) -> str:
        """Module version string."""
        ...

    async def evaluate(
        self, request: Any, ctx: Any, policy: Any
    ) -> Dict[str, Any]:
        """Evaluate the request/response and return a ModuleResult dict.

        Returns a dict with keys:
        - action: str (e.g., "ALLOW", "DENY", "MONITOR")
        - reason_codes: List[str]
        - event_type: str
        - metadata: Optional[Dict[str, Any]]
        """
        ...


# ---------------------------------------------------------------------------
# Result Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ModuleResultWithMeta:
    """A module result enriched with timing and identity metadata."""

    name: str
    """Module name."""

    version: str
    """Module version."""

    latency_ms: float
    """Evaluation latency in milliseconds."""

    result: Dict[str, Any]
    """The module's evaluation result dict."""

    error: Optional[str] = None
    """Error message if module threw or timed out."""


@dataclass
class MergedResult:
    """The merged result of all modules at a stage."""

    action: str
    """The most restrictive action across all module results."""

    reason_codes: List[str]
    """All reason codes collected from all modules."""


@dataclass
class StageEvaluationResult:
    """Complete evaluation result for a single pipeline stage."""

    action: str
    """The merged action (most restrictive wins)."""

    reason_codes: List[str]
    """All reason codes collected from evaluated modules."""

    module_details: List[ModuleEvalDetail]
    """Per-module evaluation details for audit trail."""

    latency_ms: float
    """Total stage evaluation latency in milliseconds."""


# ---------------------------------------------------------------------------
# StageEvaluator
# ---------------------------------------------------------------------------


class StageEvaluator:
    """Evaluates all modules registered at a single pipeline stage in parallel.

    Enforces per-module timeouts and merges results using MostRestrictiveWins.

    Fail-closed behavior:
    - When ``fail_closed`` is True: module errors/timeouts → DENY
    - When ``fail_closed`` is False:
      - PRE_EXECUTION stage: module errors/timeouts → MONITOR
      - POST_EXECUTION stage: module errors/timeouts → ALLOW (per Req 12.4)

    Args:
        stage: The pipeline stage this evaluator operates at.
        fail_closed: Whether module failures block the request.
        timeout_ms: Per-module evaluation timeout in milliseconds.
    """

    def __init__(
        self,
        stage: PipelineStage,
        fail_closed: bool,
        timeout_ms: int = 5000,
    ) -> None:
        self._stage = stage
        self._fail_closed = fail_closed
        self._timeout_ms = timeout_ms

    async def evaluate(
        self,
        modules: List[Any],
        request: Any,
        ctx: Any,
        policy: Any,
    ) -> StageEvaluationResult:
        """Evaluate all modules in parallel with timeout enforcement.

        Returns per-module results and the merged stage action.

        Args:
            modules: List of TealModule implementations to evaluate.
            request: The evaluation request (ModuleEvaluationRequest equivalent).
            ctx: The module context (ModuleContext equivalent).
            policy: The policy configuration.

        Returns:
            A StageEvaluationResult with the merged action, reason codes,
            per-module details, and total latency.
        """
        stage_start = time.perf_counter()

        # No modules registered → pass-through (ALLOW)
        if not modules:
            return StageEvaluationResult(
                action="ALLOW",
                reason_codes=[],
                module_details=[],
                latency_ms=(time.perf_counter() - stage_start) * 1000,
            )

        # Evaluate all modules in parallel with timeout enforcement
        coroutines = [
            self._evaluate_module(mod, request, ctx, policy)
            for mod in modules
        ]
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        # Process results into ModuleResultWithMeta
        module_results: List[ModuleResultWithMeta] = []
        for i, result in enumerate(results):
            mod = modules[i]
            if isinstance(result, BaseException):
                # asyncio.gather with return_exceptions=True returned an exception
                # This is a safety net — _evaluate_module handles errors internally
                module_results.append(self._build_error_result(mod, result))
            else:
                module_results.append(result)

        # Merge results using MostRestrictiveWins
        merged = self._merge_results(module_results)

        # Build per-module detail records for audit trail
        module_details: List[ModuleEvalDetail] = []
        for mr in module_results:
            detail = ModuleEvalDetail(
                name=mr.name,
                version=mr.version,
                latency_ms=mr.latency_ms,
                action=mr.result.get("action", "ALLOW"),
                reason_codes=mr.result.get("reason_codes", []),
                error=mr.error,
                metadata=mr.result.get("metadata"),
            )
            module_details.append(detail)

        return StageEvaluationResult(
            action=merged.action,
            reason_codes=merged.reason_codes,
            module_details=module_details,
            latency_ms=(time.perf_counter() - stage_start) * 1000,
        )

    async def _evaluate_module(
        self,
        mod: Any,
        request: Any,
        ctx: Any,
        policy: Any,
    ) -> ModuleResultWithMeta:
        """Evaluate a single module with timeout enforcement.

        Catches errors and applies fail-closed/fail-open policy.

        Args:
            mod: The TealModule to evaluate.
            request: The evaluation request.
            ctx: The module context.
            policy: The policy configuration.

        Returns:
            ModuleResultWithMeta with the module's result or an error fallback.
        """
        start = time.perf_counter()

        try:
            result = await self._with_timeout(
                mod.evaluate(request, ctx, policy),
                mod.name,
            )
            return ModuleResultWithMeta(
                name=mod.name,
                version=mod.version,
                latency_ms=(time.perf_counter() - start) * 1000,
                result=result,
            )
        except Exception as error:
            latency_ms = (time.perf_counter() - start) * 1000
            error_message = str(error)

            # Determine fallback action based on fail-closed policy and stage
            fallback_action = self._get_error_fallback_action()

            return ModuleResultWithMeta(
                name=mod.name,
                version=mod.version,
                latency_ms=latency_ms,
                result={
                    "action": fallback_action,
                    "reason_codes": ["PIPELINE_FAIL_CLOSED"],
                    "event_type": "pipeline.module_error",
                    "metadata": {"error": error_message, "module": mod.name},
                },
                error=error_message,
            )

    async def _with_timeout(
        self,
        coro: Any,
        module_name: str,
    ) -> Dict[str, Any]:
        """Wrap a module evaluation with timeout enforcement.

        Uses asyncio.wait_for to race the module's evaluate() against a timer.
        On timeout, raises ModuleTimeoutError.

        Args:
            coro: The coroutine from module.evaluate().
            module_name: Name of the module (for error reporting).

        Returns:
            The module result dict.

        Raises:
            ModuleTimeoutError: When the module exceeds the configured timeout.
        """
        try:
            return await asyncio.wait_for(
                coro,
                timeout=self._timeout_ms / 1000.0,
            )
        except asyncio.TimeoutError:
            raise ModuleTimeoutError(module_name, self._timeout_ms)

    def _merge_results(self, results: List[ModuleResultWithMeta]) -> MergedResult:
        """Merge module results using MostRestrictiveWins strategy.

        Uses ACTION_SEVERITY map: picks the action with highest severity.
        - DENY (severity >= 70): Stage blocks
        - MONITOR (severity 10–60): Stage proceeds with monitoring
        - ALLOW (severity 0): Stage permits

        All reason codes from all modules are collected into the merged result.

        Args:
            results: List of per-module results with metadata.

        Returns:
            MergedResult with the most restrictive action and all reason codes.
        """
        highest_severity = 0
        merged_action = "ALLOW"
        all_reason_codes: List[str] = []

        for module_result in results:
            action = module_result.result.get("action", "ALLOW")
            severity = ACTION_SEVERITY.get(action, 0)

            if severity > highest_severity:
                highest_severity = severity
                merged_action = action

            # Collect all reason codes
            reason_codes = module_result.result.get("reason_codes", [])
            all_reason_codes.extend(reason_codes)

        return MergedResult(
            action=merged_action,
            reason_codes=all_reason_codes,
        )

    def _get_error_fallback_action(self) -> str:
        """Determine the fallback action when a module errors or times out.

        - fail_closed=True → DENY (for both stages)
        - fail_closed=False, PRE_EXECUTION → MONITOR
        - fail_closed=False, POST_EXECUTION → ALLOW (per Req 12.4)

        Returns:
            The fallback action string.
        """
        if self._fail_closed:
            return "DENY"

        # fail_closed=False: stage-dependent fallback
        if self._stage == PipelineStage.POST_EXECUTION:
            return "ALLOW"

        # PRE_EXECUTION (or EXECUTION, though not typically used here)
        return "MONITOR"

    def _build_error_result(
        self,
        mod: Any,
        error: BaseException,
    ) -> ModuleResultWithMeta:
        """Build an error result for a module that failed at the gather level.

        This is a safety net — normally _evaluate_module handles errors internally.

        Args:
            mod: The module that failed.
            error: The exception that was raised.

        Returns:
            ModuleResultWithMeta with the error fallback action.
        """
        error_message = str(error)
        fallback_action = self._get_error_fallback_action()

        return ModuleResultWithMeta(
            name=getattr(mod, "name", "unknown"),
            version=getattr(mod, "version", "0.0.0"),
            latency_ms=0.0,
            result={
                "action": fallback_action,
                "reason_codes": ["PIPELINE_FAIL_CLOSED"],
                "event_type": "pipeline.module_error",
                "metadata": {
                    "error": error_message,
                    "module": getattr(mod, "name", "unknown"),
                },
            },
            error=error_message,
        )
