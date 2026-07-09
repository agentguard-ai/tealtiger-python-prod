"""Unit tests for stage_adapter — v1.2 module wrapping utility.

Validates:
- assign_stage creates a shallow copy with stage attribute (Req 11.2)
- Original module is not mutated (Req 11.5)
- Adapted module preserves isinstance checks (Req 11.6)
- Property 7: Module Composability Preservation
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from tealtiger.pipeline.stage_adapter import assign_stage
from tealtiger.pipeline.types import PipelineStage


class FakeTealModule:
    """Minimal v1.2 TealModule implementation for testing."""

    def __init__(self, name: str = "fake-module", version: str = "1.0.0") -> None:
        self.name = name
        self.version = version
        self._calls: List[Any] = []

    async def evaluate(
        self, request: Dict[str, Any], context: Dict[str, Any], policy: Any = None
    ) -> Dict[str, Any]:
        self._calls.append((request, context, policy))
        return {"action": "ALLOW", "reason_codes": []}


class TestAssignStageBasic:
    """Test basic assign_stage behavior."""

    def test_returns_object_with_stage_attribute(self) -> None:
        """assign_stage adds a stage attribute to the returned object."""
        module = FakeTealModule()
        adapted = assign_stage(module, PipelineStage.PRE_EXECUTION)

        assert hasattr(adapted, "stage")
        assert adapted.stage == PipelineStage.PRE_EXECUTION

    def test_preserves_name_and_version(self) -> None:
        """Adapted module retains name and version from the original."""
        module = FakeTealModule(name="test-mod", version="2.3.1")
        adapted = assign_stage(module, PipelineStage.POST_EXECUTION)

        assert adapted.name == "test-mod"
        assert adapted.version == "2.3.1"

    def test_original_module_not_modified(self) -> None:
        """The original module does not gain a stage attribute."""
        module = FakeTealModule()
        assign_stage(module, PipelineStage.PRE_EXECUTION)

        assert not hasattr(module, "stage")

    def test_adapted_is_different_object(self) -> None:
        """The adapted module is a distinct object from the original."""
        module = FakeTealModule()
        adapted = assign_stage(module, PipelineStage.EXECUTION)

        assert adapted is not module


class TestAssignStagePreservesInterface:
    """Test that the adapted module preserves the TealModule interface."""

    def test_preserves_isinstance(self) -> None:
        """Adapted module passes isinstance check for original class."""
        module = FakeTealModule()
        adapted = assign_stage(module, PipelineStage.PRE_EXECUTION)

        assert isinstance(adapted, FakeTealModule)

    @pytest.mark.asyncio
    async def test_evaluate_method_works(self) -> None:
        """Adapted module's evaluate method is callable and works."""
        module = FakeTealModule()
        adapted = assign_stage(module, PipelineStage.PRE_EXECUTION)

        result = await adapted.evaluate(
            {"payload": "test"}, {"agent_id": "a1"}, None
        )

        assert result["action"] == "ALLOW"

    def test_has_evaluate_method(self) -> None:
        """Adapted module retains the evaluate method."""
        module = FakeTealModule()
        adapted = assign_stage(module, PipelineStage.POST_EXECUTION)

        assert callable(adapted.evaluate)


class TestAssignStageAllStages:
    """Test assign_stage with each pipeline stage."""

    @pytest.mark.parametrize(
        "stage",
        [PipelineStage.PRE_EXECUTION, PipelineStage.EXECUTION, PipelineStage.POST_EXECUTION],
    )
    def test_all_stages(self, stage: PipelineStage) -> None:
        """assign_stage works with all PipelineStage values."""
        module = FakeTealModule()
        adapted = assign_stage(module, stage)

        assert adapted.stage == stage
        assert adapted.name == module.name


class TestAssignStageShallowCopy:
    """Test shallow copy semantics."""

    def test_shared_mutable_attributes(self) -> None:
        """Shallow copy means mutable attributes are shared references."""
        module = FakeTealModule()
        module.config = {"key": "value"}  # type: ignore[attr-defined]
        adapted = assign_stage(module, PipelineStage.PRE_EXECUTION)

        # Shallow copy shares the same dict reference
        assert adapted.config is module.config  # type: ignore[attr-defined]

    def test_multiple_assignments_are_independent(self) -> None:
        """Multiple assign_stage calls produce independent copies."""
        module = FakeTealModule()
        pre = assign_stage(module, PipelineStage.PRE_EXECUTION)
        post = assign_stage(module, PipelineStage.POST_EXECUTION)

        assert pre.stage == PipelineStage.PRE_EXECUTION
        assert post.stage == PipelineStage.POST_EXECUTION
        assert pre is not post
        assert not hasattr(module, "stage")
