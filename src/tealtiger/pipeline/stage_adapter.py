"""Multi-Stage Defense Pipeline — Stage Adapter Utility (Python SDK).

Wraps an existing v1.2 TealModule with a pipeline stage assignment,
enabling composability with the multi-stage defense pipeline without
modifying the original module.

Module: pipeline/stage_adapter
Requirements: 11.2, 11.5, 11.6
"""

from __future__ import annotations

import copy
from typing import Any

from .types import PipelineStage


def assign_stage(module: Any, stage: PipelineStage) -> Any:
    """Wrap a v1.2 TealModule with a stage assignment.

    Creates a shallow copy of the module that preserves all existing
    attributes and adds a ``stage`` property indicating which pipeline
    stage the module is assigned to.

    The original module is NOT modified.

    Args:
        module: Any v1.2 TealModule (must have name, version, evaluate).
        stage: The pipeline stage to assign the module to.

    Returns:
        A new object that has all properties of the original module plus
        an additional ``stage`` attribute set to the given PipelineStage.

    Example::

        from tealtiger.pipeline.stage_adapter import assign_stage
        from tealtiger.pipeline.types import PipelineStage

        secrets = PIIScannerModule()
        pre_secrets = assign_stage(secrets, PipelineStage.PRE_EXECUTION)
        # pre_secrets.stage == PipelineStage.PRE_EXECUTION
        # pre_secrets.evaluate() delegates to the original module
        # Original `secrets` is unchanged
    """
    # Create a shallow copy to avoid mutating the original
    wrapped = copy.copy(module)
    wrapped.stage = stage
    return wrapped
