"""Multi-Stage Defense Pipeline — DefensePipeline Orchestrator (Python SDK).

Top-level orchestrator that manages the three lifecycle stages
(PRE_EXECUTION → EXECUTION → POST_EXECUTION) for a governed LLM request.
Validates configuration, wires internal components, and coordinates
the full pipeline flow including remediation.

Module: pipeline/defense_pipeline
Requirements: 11.2, 11.5, 11.6
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .errors import ModuleValidationError, PipelineConfigError
from .execution_stage import ExecutionStage
from .hook_runner import HookRunner
from .remediation_handler import RemediationHandler
from .stage_decision_builder import StageDecisionBuilder, StageDecisionBuildParams
from .stage_evaluator import StageEvaluator
from .types import (
    ACTION_SEVERITY,
    PipelineConfig,
    PipelineHooks,
    PipelineRequest,
    PipelineResult,
    PipelineStage,
    PipelineTimingMetadata,
    RemediationAction,
    StageDecision,
)


# ---------------------------------------------------------------------------
# Module Status Types
# ---------------------------------------------------------------------------


@dataclass
class ModuleStatusEntry:
    """Status information for a registered module."""

    name: str
    version: str
    stage: PipelineStage
    registered: bool


@dataclass
class PipelineModuleStatus:
    """Aggregated module status for all registered modules."""

    modules: List[ModuleStatusEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# DefensePipeline
# ---------------------------------------------------------------------------


class DefensePipeline:
    """Top-level orchestrator for multi-stage governance enforcement on LLM requests.

    Coordinates:
    1. Pre-execution stage: evaluate request → block if DENY
    2. Execution stage: forward to LLM provider via ObserveProxy
    3. Post-execution stage: evaluate response → remediate if DENY

    Each stage produces a StageDecision optionally enriched with
    TEEC v2.1 cryptographic provenance fields.

    Args:
        config: PipelineConfig specifying modules, proxy, and settings.

    Raises:
        ModuleValidationError: If any module doesn't implement TealModule interface.
        PipelineConfigError: If neither observe_proxy nor provider_client is provided.
    """

    def __init__(self, config: PipelineConfig) -> None:
        # Validate modules implement TealModule interface
        self._validate_modules(config)

        # Validate that either observe_proxy or provider_client is provided
        if config.observe_proxy is None and config.provider_client is None:
            raise PipelineConfigError(
                "Either observe_proxy or provider_client must be provided in PipelineConfig"
            )

        self._config = config

        fail_closed = config.fail_closed
        timeout_ms = config.module_timeout_ms
        resample_budget = config.resample_budget

        # Initialize internal components
        self._pre_stage = StageEvaluator(
            PipelineStage.PRE_EXECUTION, fail_closed, timeout_ms
        )
        self._post_stage = StageEvaluator(
            PipelineStage.POST_EXECUTION, fail_closed, timeout_ms
        )

        # Resolve ObserveProxy: use provided or wrap provider_client
        observe_proxy = config.observe_proxy or config.provider_client
        self._execution_stage = ExecutionStage(observe_proxy)

        self._hook_runner = HookRunner(config.hooks)
        self._decision_builder = StageDecisionBuilder(
            config.seal_secret, config.agent_id or "default"
        )
        self._remediation_handler = RemediationHandler(resample_budget)

    async def execute(self, request: PipelineRequest) -> PipelineResult:
        """Execute the full multi-stage defense pipeline for a request.

        Flow: hooks → pre-stage → execution → post-stage → remediation → result

        Args:
            request: The pipeline request containing the LLM payload.

        Returns:
            A PipelineResult with governance outcome, response, and audit trail.
        """
        # Record pipeline entry timestamp
        pipeline_entry = time.time() * 1000  # Unix milliseconds

        # Generate correlation_id if not provided
        correlation_id = request.correlation_id or str(uuid.uuid4())
        resolved_request = PipelineRequest(
            payload=request.payload,
            correlation_id=correlation_id,
            context=request.context,
        )

        # Build module context for evaluation
        ctx = self._build_module_context(resolved_request)

        # Initialize timing metadata
        timing = PipelineTimingMetadata(
            pipeline_entry=pipeline_entry,
            pre_execution_start=0.0,
            pre_execution_end=0.0,
        )

        decisions: List[StageDecision] = []

        # ── PRE-EXECUTION STAGE ─────────────────────────────────────

        # Run before_pre_execution hook
        await self._hook_runner.run("before_pre_execution", resolved_request)

        # Evaluate pre-execution stage
        timing.pre_execution_start = time.time() * 1000
        pre_eval_result = await self._pre_stage.evaluate(
            self._config.pre_execution_modules,
            self._build_evaluation_request(resolved_request),
            ctx,
            None,
        )
        timing.pre_execution_end = time.time() * 1000

        # Build pre-execution StageDecision
        pre_decision = self._decision_builder.build(
            StageDecisionBuildParams(
                action=pre_eval_result.action,
                reason_codes=pre_eval_result.reason_codes,
                stage=PipelineStage.PRE_EXECUTION,
                latency_ms=pre_eval_result.latency_ms,
                module_details=pre_eval_result.module_details,
                payload=resolved_request.payload,
            )
        )
        decisions.append(pre_decision)

        # Run after_pre_execution hook
        await self._hook_runner.run("after_pre_execution", pre_decision)

        # If pre-decision is DENY (severity >= 70): return blocked result
        pre_severity = ACTION_SEVERITY.get(pre_decision.action, 0)
        if pre_severity >= 70:
            timing.hook_time_ms = self._hook_runner.get_hook_time()
            return PipelineResult(
                allowed=False,
                response=None,
                pre_decision=pre_decision,
                post_decision=None,
                blocked_stage=PipelineStage.PRE_EXECUTION,
                total_latency_ms=time.time() * 1000 - pipeline_entry,
                resample_count=0,
                remediation_action=None,
                redacted=False,
                remediation_exhausted=False,
                provider_error=False,
                decisions=decisions,
                timing=timing,
            )

        # ── EXECUTION STAGE ─────────────────────────────────────────

        # Run before_execution hook
        await self._hook_runner.run("before_execution", resolved_request)

        # Execute via ExecutionStage (ObserveProxy delegation)
        timing.execution_start = time.time() * 1000
        execution_result = await self._execution_stage.execute(resolved_request)
        timing.execution_end = time.time() * 1000

        # Run after_execution hook
        await self._hook_runner.run(
            "after_execution", execution_result.response, execution_result.metadata
        )

        # If provider error: return provider_error result
        if not execution_result.success:
            timing.hook_time_ms = self._hook_runner.get_hook_time()
            return PipelineResult(
                allowed=False,
                response=None,
                pre_decision=pre_decision,
                post_decision=None,
                blocked_stage=None,
                total_latency_ms=time.time() * 1000 - pipeline_entry,
                resample_count=0,
                remediation_action=None,
                redacted=False,
                remediation_exhausted=False,
                provider_error=True,
                provider_error_details=execution_result.error,
                decisions=decisions,
                timing=timing,
            )

        # ── POST-EXECUTION STAGE ────────────────────────────────────

        # Run before_post_execution hook
        await self._hook_runner.run(
            "before_post_execution", execution_result.response, resolved_request
        )

        # Evaluate post-execution stage
        timing.post_execution_start = time.time() * 1000
        post_eval_result = await self._post_stage.evaluate(
            self._config.post_execution_modules,
            self._build_post_evaluation_request(
                resolved_request, execution_result.response
            ),
            ctx,
            None,
        )
        timing.post_execution_end = time.time() * 1000

        # Build post-execution StageDecision
        post_payload = (
            execution_result.response
            if isinstance(execution_result.response, dict)
            else {"_response": execution_result.response}
        )
        post_decision = self._decision_builder.build(
            StageDecisionBuildParams(
                action=post_eval_result.action,
                reason_codes=post_eval_result.reason_codes,
                stage=PipelineStage.POST_EXECUTION,
                latency_ms=post_eval_result.latency_ms,
                module_details=post_eval_result.module_details,
                payload=post_payload,
            )
        )
        decisions.append(post_decision)

        # Run after_post_execution hook
        await self._hook_runner.run("after_post_execution", post_decision)

        # If post-decision is DENY (severity >= 70): run remediation logic
        post_severity = ACTION_SEVERITY.get(post_decision.action, 0)
        if post_severity >= 70:
            return await self._handle_remediation(
                resolved_request,
                pre_decision,
                post_decision,
                execution_result.response,
                ctx,
                decisions,
                timing,
                pipeline_entry,
            )

        # ── SUCCESS: Response passes all stages ─────────────────────
        timing.hook_time_ms = self._hook_runner.get_hook_time()
        return PipelineResult(
            allowed=True,
            response=execution_result.response,
            pre_decision=pre_decision,
            post_decision=post_decision,
            blocked_stage=None,
            total_latency_ms=time.time() * 1000 - pipeline_entry,
            resample_count=0,
            remediation_action=None,
            redacted=False,
            remediation_exhausted=False,
            provider_error=False,
            decisions=decisions,
            timing=timing,
        )

    def get_module_status(self) -> PipelineModuleStatus:
        """Return per-module registration status information.

        Returns:
            PipelineModuleStatus with entries for all registered modules.
        """
        modules: List[ModuleStatusEntry] = []

        for mod in self._config.pre_execution_modules:
            modules.append(
                ModuleStatusEntry(
                    name=mod.name,
                    version=mod.version,
                    stage=PipelineStage.PRE_EXECUTION,
                    registered=True,
                )
            )

        for mod in self._config.post_execution_modules:
            modules.append(
                ModuleStatusEntry(
                    name=mod.name,
                    version=mod.version,
                    stage=PipelineStage.POST_EXECUTION,
                    registered=True,
                )
            )

        return PipelineModuleStatus(modules=modules)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize pipeline configuration to a dictionary.

        Returns:
            A dictionary representation of the pipeline configuration.
        """
        return {
            "pre_execution_modules": [
                {"name": m.name, "version": m.version}
                for m in self._config.pre_execution_modules
            ],
            "post_execution_modules": [
                {"name": m.name, "version": m.version}
                for m in self._config.post_execution_modules
            ],
            "fail_closed": self._config.fail_closed,
            "module_timeout_ms": self._config.module_timeout_ms,
            "resample_budget": self._config.resample_budget,
            "agent_id": self._config.agent_id,
            "seal_secret_configured": self._config.seal_secret is not None,
        }

    # ------------------------------------------------------------------
    # Private Methods
    # ------------------------------------------------------------------

    async def _handle_remediation(
        self,
        request: PipelineRequest,
        pre_decision: StageDecision,
        post_decision: StageDecision,
        original_response: Any,
        ctx: Any,
        decisions: List[StageDecision],
        timing: PipelineTimingMetadata,
        pipeline_entry: float,
    ) -> PipelineResult:
        """Handle post-execution remediation when the post-stage decision is DENY.

        Selects the remediation action and executes the appropriate strategy
        (resample loop, redaction, or deny response).
        """
        # Select remediation action from module metadata
        action = self._remediation_handler.select_action(post_decision.module_details)

        # Run on_remediation hook
        await self._hook_runner.run("on_remediation", action, post_decision, 0)

        if action == RemediationAction.RESAMPLE:
            # Execute resample loop
            resample_start = time.time() * 1000
            remediation_result = await self._remediation_handler.execute_resample_loop(
                request,
                self._execution_stage,
                self._post_stage,
                self._config.post_execution_modules,
                ctx,
                None,
                0,
            )
            resample_end = time.time() * 1000
            timing.remediation_attempts.append(
                {"start": resample_start, "end": resample_end}
            )

            timing.hook_time_ms = self._hook_runner.get_hook_time()

            if remediation_result.success:
                return PipelineResult(
                    allowed=True,
                    response=remediation_result.response,
                    pre_decision=pre_decision,
                    post_decision=post_decision,
                    blocked_stage=None,
                    total_latency_ms=time.time() * 1000 - pipeline_entry,
                    resample_count=remediation_result.resample_count,
                    remediation_action=RemediationAction.RESAMPLE,
                    redacted=False,
                    remediation_exhausted=False,
                    provider_error=False,
                    decisions=decisions,
                    timing=timing,
                )

            # Budget exhausted → DENY_RESPONSE
            return PipelineResult(
                allowed=False,
                response=None,
                pre_decision=pre_decision,
                post_decision=post_decision,
                blocked_stage=PipelineStage.POST_EXECUTION,
                total_latency_ms=time.time() * 1000 - pipeline_entry,
                resample_count=remediation_result.resample_count,
                remediation_action=RemediationAction.RESAMPLE,
                redacted=False,
                remediation_exhausted=True,
                provider_error=False,
                decisions=decisions,
                timing=timing,
            )

        elif action == RemediationAction.REDACT:
            # Apply redaction via module-provided functions
            redact_start = time.time() * 1000
            redacted_response = await self._remediation_handler.apply_redaction(
                original_response, post_decision.module_details
            )
            redact_end = time.time() * 1000
            timing.remediation_attempts.append(
                {"start": redact_start, "end": redact_end}
            )

            timing.hook_time_ms = self._hook_runner.get_hook_time()

            return PipelineResult(
                allowed=True,
                response=redacted_response,
                pre_decision=pre_decision,
                post_decision=post_decision,
                blocked_stage=None,
                total_latency_ms=time.time() * 1000 - pipeline_entry,
                resample_count=0,
                remediation_action=RemediationAction.REDACT,
                redacted=True,
                remediation_exhausted=False,
                provider_error=False,
                decisions=decisions,
                timing=timing,
            )

        else:
            # DENY_RESPONSE (default)
            timing.hook_time_ms = self._hook_runner.get_hook_time()

            return PipelineResult(
                allowed=False,
                response=None,
                pre_decision=pre_decision,
                post_decision=post_decision,
                blocked_stage=PipelineStage.POST_EXECUTION,
                total_latency_ms=time.time() * 1000 - pipeline_entry,
                resample_count=0,
                remediation_action=RemediationAction.DENY_RESPONSE,
                redacted=False,
                remediation_exhausted=False,
                provider_error=False,
                decisions=decisions,
                timing=timing,
            )

    def _validate_modules(self, config: PipelineConfig) -> None:
        """Validate that all modules implement the TealModule interface.

        Checks each module for: name (str), version (str), evaluate (callable).

        Raises:
            ModuleValidationError: If any module is non-conforming.
        """
        all_modules = [
            *config.pre_execution_modules,
            *config.post_execution_modules,
        ]

        for mod in all_modules:
            missing_fields: List[str] = []

            if mod is None or not hasattr(mod, "__class__"):
                raise ModuleValidationError(
                    "unknown", ["name", "version", "evaluate"]
                )

            name = getattr(mod, "name", None)
            if not isinstance(name, str) or len(name) == 0:
                missing_fields.append("name")

            version = getattr(mod, "version", None)
            if not isinstance(version, str) or len(version) == 0:
                missing_fields.append("version")

            evaluate = getattr(mod, "evaluate", None)
            if not callable(evaluate):
                missing_fields.append("evaluate")

            if missing_fields:
                module_name = name if isinstance(name, str) and len(name) > 0 else "unknown"
                raise ModuleValidationError(module_name, missing_fields)

    def _build_module_context(self, request: PipelineRequest) -> Dict[str, Any]:
        """Build module context for evaluation.

        Returns:
            A dictionary with correlation_id, policy_version, timestamps,
            and optional agent/session/tenant/user IDs.
        """
        ctx: Dict[str, Any] = {
            "correlation_id": request.correlation_id,
            "policy_version": "1.4.0",
            "teec_version": "2.1",
            "timestamp": time.time() * 1000,
        }

        if self._config.agent_id is not None:
            ctx["agent_id"] = self._config.agent_id

        if request.context:
            for key in ("session_id", "tenant_id", "user_id"):
                if key in request.context:
                    ctx[key] = request.context[key]

        return ctx

    def _build_evaluation_request(self, request: PipelineRequest) -> Dict[str, Any]:
        """Build a module evaluation request from the pipeline request (pre-execution).

        Returns:
            A dictionary with content and all payload fields.
        """
        content = request.payload.get("content")
        if isinstance(content, str):
            eval_content = content
        else:
            eval_content = json.dumps(request.payload)

        return {"content": eval_content, **request.payload}

    def _build_post_evaluation_request(
        self, request: PipelineRequest, response: Any
    ) -> Dict[str, Any]:
        """Build a module evaluation request for post-execution (includes response).

        Returns:
            A dictionary with content, all payload fields, and _response.
        """
        if isinstance(response, str):
            content = response
        else:
            content = json.dumps(response) if response is not None else ""

        return {"content": content, **request.payload, "_response": response}
