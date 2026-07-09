"""Multi-Stage Defense Pipeline — RemediationHandler (Python SDK).

Manages remediation logic for failed post-execution evaluations:
action selection (RESAMPLE > REDACT > DENY_RESPONSE), resample loop
with budget enforcement, and redaction delegation.

Module: pipeline/remediation_handler
Requirements: 11.2, 11.5, 11.6
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol, Union

from .types import ACTION_SEVERITY, ModuleEvalDetail, PipelineRequest, RemediationAction


# ---------------------------------------------------------------------------
# Protocols (structural typing for dependency injection)
# ---------------------------------------------------------------------------


class ExecutionStageProtocol(Protocol):
    """Protocol for the ExecutionStage dependency (used for resample loop).

    Declared here to avoid circular imports — the actual ExecutionStage
    class implements this shape. Returns an ExecutionResult dataclass with
    attributes: success, response, metadata, error.
    """

    async def execute(self, request: PipelineRequest) -> Any:
        """Execute a request against the LLM provider.

        Returns an ExecutionResult dataclass with attributes:
        success (bool), response (Any), metadata, error (Optional[Dict]).
        """
        ...


class StageEvaluatorProtocol(Protocol):
    """Protocol for the StageEvaluator dependency (used for post-stage re-evaluation).

    Returns a StageEvaluationResult dataclass with attributes:
    action (str), reason_codes (List[str]), module_details, latency_ms.
    """

    async def evaluate(
        self,
        modules: List[Any],
        request: Any,
        ctx: Any,
        policy: Any,
    ) -> Any:
        """Evaluate modules and return merged result.

        Returns a StageEvaluationResult dataclass with attributes:
        action, reason_codes, module_details, latency_ms.
        """
        ...


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class RemediationResult:
    """Result of a remediation operation.

    Attributes:
        success: Whether remediation produced a passing response.
        response: The response (new from resample, or redacted, or None).
        resample_count: Number of resample attempts made.
        exhausted: Whether the resample budget was exhausted.
    """

    success: bool
    response: Any
    resample_count: int
    exhausted: bool


# ---------------------------------------------------------------------------
# RemediationHandler
# ---------------------------------------------------------------------------


class RemediationHandler:
    """Handles post-execution remediation when a module reports a policy violation.

    Action selection priority (from module metadata):
        RESAMPLE > REDACT > DENY_RESPONSE (default)

    Resample loop re-invokes the LLM provider and re-evaluates the post-execution
    stage until the response passes or the budget is exhausted.

    Redaction delegates to the module-provided redaction function to strip
    violating content from the response.

    Args:
        resample_budget: Maximum number of resample attempts permitted.
    """

    def __init__(self, resample_budget: int) -> None:
        self._resample_budget = resample_budget

    @property
    def resample_budget(self) -> int:
        """The configured resample budget."""
        return self._resample_budget

    def select_action(self, module_details: List[ModuleEvalDetail]) -> RemediationAction:
        """Determine the remediation action from module metadata.

        Scans all module details with a DENY-level action for a ``remediation``
        field in their metadata. Priority order:
            1. If any module specifies "resample" → RESAMPLE
            2. If any module specifies "redact" → REDACT
            3. Otherwise → DENY_RESPONSE (default)

        Args:
            module_details: Per-module evaluation details from the post-stage.

        Returns:
            The selected RemediationAction.
        """
        has_redact = False

        for detail in module_details:
            # Only consider modules that produced a DENY-level action
            severity = ACTION_SEVERITY.get(detail.action, 0)
            if severity < 70:
                continue

            metadata = detail.metadata
            if not metadata:
                continue

            remediation = metadata.get("remediation")
            if not remediation:
                continue

            normalized = str(remediation).lower()

            # RESAMPLE has highest priority — return immediately
            if normalized == "resample":
                return RemediationAction.RESAMPLE

            if normalized == "redact":
                has_redact = True

        if has_redact:
            return RemediationAction.REDACT

        return RemediationAction.DENY_RESPONSE

    async def execute_resample_loop(
        self,
        request: PipelineRequest,
        execution_stage: ExecutionStageProtocol,
        post_stage_evaluator: StageEvaluatorProtocol,
        modules: List[Any],
        ctx: Any,
        policy: Any,
        current_attempt: int,
    ) -> RemediationResult:
        """Execute the resample loop: re-invoke the LLM provider and re-evaluate
        the post-execution stage until the response passes or the budget is exhausted.

        Args:
            request: The original pipeline request.
            execution_stage: The execution stage for re-invoking the provider.
            post_stage_evaluator: The post-execution stage evaluator.
            modules: The post-execution modules to evaluate.
            ctx: Module evaluation context.
            policy: Policy configuration.
            current_attempt: Current attempt count (starts at 0 for first resample).

        Returns:
            RemediationResult indicating success/failure and attempt count.
        """
        attempt = current_attempt

        while attempt < self._resample_budget:
            attempt += 1

            # Re-invoke provider — returns an ExecutionResult dataclass
            execution_result = await execution_stage.execute(request)

            if not execution_result.success or execution_result.response is None:
                # Provider error during resample — count as failed attempt
                continue

            response = execution_result.response

            # Re-evaluate post-execution stage on the new response
            content = (
                response if isinstance(response, str) else json.dumps(response)
            )
            evaluation_request = {
                "content": content,
                **request.payload,
                "_response": response,
            }

            # Returns a StageEvaluationResult dataclass
            eval_result = await post_stage_evaluator.evaluate(
                modules,
                evaluation_request,
                ctx,
                policy,
            )

            # Check if the new response passes (merged action is not DENY-level)
            severity = ACTION_SEVERITY.get(eval_result.action, 0)
            if severity < 70:
                # Response passed — return success
                return RemediationResult(
                    success=True,
                    response=response,
                    resample_count=attempt,
                    exhausted=False,
                )

            # Still DENY — continue loop if budget allows

        # Budget exhausted
        return RemediationResult(
            success=False,
            response=None,
            resample_count=attempt,
            exhausted=True,
        )

    async def apply_redaction(
        self,
        response: Any,
        module_details: List[ModuleEvalDetail],
    ) -> Any:
        """Apply redaction via module-provided redaction functions.

        Searches module details for modules that have a ``redact`` or
        ``redaction_fn`` function in their metadata. Calls the redaction
        function with the response and returns the redacted result.

        Redaction functions are chained: the output of one becomes the
        input of the next.

        Args:
            response: The LLM response to redact.
            module_details: Per-module evaluation details (may contain
                redaction functions).

        Returns:
            The redacted response, or the original response if no
            redaction function is found.
        """
        redacted_response = response

        for detail in module_details:
            # Only consider modules with DENY-level actions
            severity = ACTION_SEVERITY.get(detail.action, 0)
            if severity < 70:
                continue

            metadata = detail.metadata
            if not metadata:
                continue

            # Look for a redaction function in metadata
            redaction_fn = metadata.get("redact") or metadata.get("redaction_fn")

            if callable(redaction_fn):
                result = redaction_fn(redacted_response)
                # Support both sync and async redaction functions
                if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                    redacted_response = await result
                else:
                    redacted_response = result

        return redacted_response
