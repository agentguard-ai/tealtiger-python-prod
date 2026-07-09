"""Property test: Hook Non-Interference.

**Validates: Requirements 10.2, 10.5**

Property 10: For any pipeline execution, the final governance outcomes
(allowed, pre_decision.action, post_decision.action, remediation_action)
SHALL be identical regardless of whether hooks are registered or what hooks
do (including throwing exceptions) — hooks observe but do not modify
pipeline behavior.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from tealtiger.pipeline.defense_pipeline import DefensePipeline
from tealtiger.pipeline.types import (
    PipelineConfig,
    PipelineHooks,
    PipelineRequest,
    PipelineStage,
)


# ---------------------------------------------------------------------------
# Helpers: Mock modules and provider
# ---------------------------------------------------------------------------


class SimpleAllowModule:
    """Module that always returns ALLOW."""

    def __init__(self, name: str = "allow_mod") -> None:
        self.name = name
        self.version = "1.0.0"

    async def evaluate(self, request: Any, ctx: Any, policy: Any) -> Dict[str, Any]:
        return {"action": "ALLOW", "reason_codes": [], "event_type": "test"}


class SimpleDenyModule:
    """Module that always returns DENY."""

    def __init__(self, name: str = "deny_mod") -> None:
        self.name = name
        self.version = "1.0.0"

    async def evaluate(self, request: Any, ctx: Any, policy: Any) -> Dict[str, Any]:
        return {"action": "DENY", "reason_codes": ["DENIED"], "event_type": "test"}


class SimpleMonitorModule:
    """Module that always returns MONITOR."""

    def __init__(self, name: str = "monitor_mod") -> None:
        self.name = name
        self.version = "1.0.0"

    async def evaluate(self, request: Any, ctx: Any, policy: Any) -> Dict[str, Any]:
        return {"action": "MONITOR", "reason_codes": ["MONITORED"], "event_type": "test"}


class MockProvider:
    """A mock LLM provider that returns a fixed response."""

    def __init__(self) -> None:
        self.call_count = 0

    async def call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.call_count += 1
        return {"content": "mock response", "model": "test-model"}

    def get_cost(self) -> Dict[str, Any]:
        return {"total_cost": 0.01, "request_count": self.call_count}


# ---------------------------------------------------------------------------
# Hook configurations (strategy)
# ---------------------------------------------------------------------------

HOOK_TYPES = ["noop", "throwing", "slow"]


def _build_hooks(config: Dict[str, str]) -> PipelineHooks:
    """Build a PipelineHooks based on a config dict mapping hook names to types."""

    def _make_hook(hook_type: str):
        if hook_type == "noop":
            return lambda *args: None
        elif hook_type == "throwing":

            def thrower(*args):
                raise RuntimeError("hook error")

            return thrower
        elif hook_type == "slow":

            async def slow(*args):
                await asyncio.sleep(0.001)

            return slow
        return None

    return PipelineHooks(
        before_pre_execution=_make_hook(config.get("before_pre_execution", "noop")),
        after_pre_execution=_make_hook(config.get("after_pre_execution", "noop")),
        before_execution=_make_hook(config.get("before_execution", "noop")),
        after_execution=_make_hook(config.get("after_execution", "noop")),
        before_post_execution=_make_hook(config.get("before_post_execution", "noop")),
        after_post_execution=_make_hook(config.get("after_post_execution", "noop")),
        on_remediation=_make_hook(config.get("on_remediation", "noop")),
    )


# Strategy for hook configs
hook_config_strategy = st.fixed_dictionaries({
    "before_pre_execution": st.sampled_from(HOOK_TYPES),
    "after_pre_execution": st.sampled_from(HOOK_TYPES),
    "before_execution": st.sampled_from(HOOK_TYPES),
    "after_execution": st.sampled_from(HOOK_TYPES),
    "before_post_execution": st.sampled_from(HOOK_TYPES),
    "after_post_execution": st.sampled_from(HOOK_TYPES),
    "on_remediation": st.sampled_from(HOOK_TYPES),
})


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestHookNonInterference:
    """Property 10: Hook Non-Interference.

    Pipeline governance outcomes are identical with and without hooks,
    regardless of hook behavior (noop, throwing, slow).
    """

    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(hook_config=hook_config_strategy)
    async def test_hooks_do_not_change_allow_result(
        self,
        hook_config: Dict[str, str],
    ) -> None:
        """When all modules ALLOW, hooks don't change the outcome."""
        # Run without hooks
        pipeline_no_hooks = DefensePipeline(
            PipelineConfig(
                pre_execution_modules=[SimpleAllowModule()],
                post_execution_modules=[SimpleAllowModule(name="post_allow")],
                provider_client=MockProvider(),
                hooks=None,
            )
        )
        result_no_hooks = await pipeline_no_hooks.execute(
            PipelineRequest(payload={"content": "test"})
        )

        # Run with hooks
        hooks = _build_hooks(hook_config)
        pipeline_with_hooks = DefensePipeline(
            PipelineConfig(
                pre_execution_modules=[SimpleAllowModule()],
                post_execution_modules=[SimpleAllowModule(name="post_allow")],
                provider_client=MockProvider(),
                hooks=hooks,
            )
        )
        result_with_hooks = await pipeline_with_hooks.execute(
            PipelineRequest(payload={"content": "test"})
        )

        # Governance outcomes must be identical
        assert result_no_hooks.allowed == result_with_hooks.allowed, (
            f"allowed mismatch: {result_no_hooks.allowed} vs {result_with_hooks.allowed}"
        )
        assert result_no_hooks.pre_decision.action == result_with_hooks.pre_decision.action
        if result_no_hooks.post_decision and result_with_hooks.post_decision:
            assert (
                result_no_hooks.post_decision.action
                == result_with_hooks.post_decision.action
            )
        assert result_no_hooks.remediation_action == result_with_hooks.remediation_action

    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(hook_config=hook_config_strategy)
    async def test_hooks_do_not_change_deny_result(
        self,
        hook_config: Dict[str, str],
    ) -> None:
        """When pre-execution DENY, hooks don't change the blocking outcome."""
        # Run without hooks
        pipeline_no_hooks = DefensePipeline(
            PipelineConfig(
                pre_execution_modules=[SimpleDenyModule()],
                post_execution_modules=[SimpleAllowModule(name="post_allow")],
                provider_client=MockProvider(),
                hooks=None,
            )
        )
        result_no_hooks = await pipeline_no_hooks.execute(
            PipelineRequest(payload={"content": "test"})
        )

        # Run with hooks
        hooks = _build_hooks(hook_config)
        pipeline_with_hooks = DefensePipeline(
            PipelineConfig(
                pre_execution_modules=[SimpleDenyModule()],
                post_execution_modules=[SimpleAllowModule(name="post_allow")],
                provider_client=MockProvider(),
                hooks=hooks,
            )
        )
        result_with_hooks = await pipeline_with_hooks.execute(
            PipelineRequest(payload={"content": "test"})
        )

        # Both should be denied
        assert result_no_hooks.allowed == result_with_hooks.allowed == False
        assert result_no_hooks.pre_decision.action == result_with_hooks.pre_decision.action
        assert result_no_hooks.blocked_stage == result_with_hooks.blocked_stage

    @pytest.mark.asyncio
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(hook_config=hook_config_strategy)
    async def test_hooks_do_not_change_post_deny_result(
        self,
        hook_config: Dict[str, str],
    ) -> None:
        """When post-execution DENY, hooks don't change remediation outcome."""
        # Run without hooks
        pipeline_no_hooks = DefensePipeline(
            PipelineConfig(
                pre_execution_modules=[SimpleAllowModule()],
                post_execution_modules=[SimpleDenyModule(name="post_deny")],
                provider_client=MockProvider(),
                resample_budget=0,  # No resamples — immediate DENY_RESPONSE
                hooks=None,
            )
        )
        result_no_hooks = await pipeline_no_hooks.execute(
            PipelineRequest(payload={"content": "test"})
        )

        # Run with hooks
        hooks = _build_hooks(hook_config)
        pipeline_with_hooks = DefensePipeline(
            PipelineConfig(
                pre_execution_modules=[SimpleAllowModule()],
                post_execution_modules=[SimpleDenyModule(name="post_deny")],
                provider_client=MockProvider(),
                resample_budget=0,
                hooks=hooks,
            )
        )
        result_with_hooks = await pipeline_with_hooks.execute(
            PipelineRequest(payload={"content": "test"})
        )

        # Both should be denied at post stage
        assert result_no_hooks.allowed == result_with_hooks.allowed == False
        assert result_no_hooks.remediation_action == result_with_hooks.remediation_action
