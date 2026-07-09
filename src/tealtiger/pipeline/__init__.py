"""TealTiger Multi-Stage Defense Pipeline.

Active governance orchestration layer that evaluates LLM requests and responses
at three lifecycle stages: PRE_EXECUTION, EXECUTION, and POST_EXECUTION.

Requirements: 11.2, 11.4
"""

from .defense_pipeline import DefensePipeline
from .errors import (
    ModuleTimeoutError,
    ModuleValidationError,
    PipelineConfigError,
    PipelineError,
    ResampleBudgetExhaustedError,
)
from .execution_stage import ExecutionStage
from .hook_runner import HookRunner
from .remediation_handler import RemediationHandler, RemediationResult
from .stage_adapter import assign_stage
from .stage_decision_builder import (
    ContiguityResult,
    StageDecisionBuilder,
    StageDecisionBuildParams,
)
from .stage_evaluator import StageEvaluator
from .types import (
    ACTION_SEVERITY,
    ExecutionMetadata,
    ExecutionResult,
    ModuleEvalDetail,
    PipelineConfig,
    PipelineHooks,
    PipelineRequest,
    PipelineResult,
    PipelineStage,
    PipelineTimingMetadata,
    RemediationAction,
    StageDecision,
)

__all__ = [
    # Orchestrator
    "DefensePipeline",
    # Core components
    "StageEvaluator",
    "StageDecisionBuilder",
    "StageDecisionBuildParams",
    "ContiguityResult",
    "HookRunner",
    "ExecutionStage",
    "RemediationHandler",
    "RemediationResult",
    # Adapter utility
    "assign_stage",
    # Types / dataclasses
    "PipelineStage",
    "RemediationAction",
    "ACTION_SEVERITY",
    "ModuleEvalDetail",
    "StageDecision",
    "PipelineTimingMetadata",
    "ExecutionMetadata",
    "ExecutionResult",
    "PipelineResult",
    "PipelineRequest",
    "PipelineConfig",
    "PipelineHooks",
    # Errors
    "PipelineError",
    "ModuleValidationError",
    "PipelineConfigError",
    "ModuleTimeoutError",
    "ResampleBudgetExhaustedError",
]
