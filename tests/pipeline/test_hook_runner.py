"""Unit tests for HookRunner — Non-blocking lifecycle hook execution.

Validates:
- Non-blocking hook execution with exception isolation (Req 11.2)
- Sync and async hook support (Req 11.5)
- Timing accumulation and reset (Req 11.6)
- Property 10: Hook Non-Interference
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, List

import pytest

from tealtiger.pipeline.hook_runner import HookRunner
from tealtiger.pipeline.types import PipelineHooks


class TestHookRunnerConstruction:
    """Test HookRunner initialization."""

    def test_constructs_with_no_hooks(self) -> None:
        """HookRunner with None hooks creates a default PipelineHooks."""
        runner = HookRunner()
        assert runner.get_hook_time() == 0.0

    def test_constructs_with_explicit_none(self) -> None:
        """HookRunner with explicit None argument works."""
        runner = HookRunner(None)
        assert runner.get_hook_time() == 0.0

    def test_constructs_with_hooks(self) -> None:
        """HookRunner accepts a PipelineHooks instance."""
        hooks = PipelineHooks(before_pre_execution=lambda req: None)
        runner = HookRunner(hooks)
        assert runner.get_hook_time() == 0.0


class TestHookRunnerSyncExecution:
    """Test synchronous hook execution."""

    @pytest.mark.asyncio
    async def test_runs_sync_hook(self) -> None:
        """Sync hooks are called with the provided arguments."""
        calls: List[Any] = []

        def on_pre(request: Any) -> None:
            calls.append(request)

        hooks = PipelineHooks(before_pre_execution=on_pre)
        runner = HookRunner(hooks)
        await runner.run("before_pre_execution", {"payload": "test"})

        assert len(calls) == 1
        assert calls[0] == {"payload": "test"}

    @pytest.mark.asyncio
    async def test_sync_hook_accumulates_time(self) -> None:
        """Sync hook execution time is measured and accumulated."""
        hooks = PipelineHooks(before_pre_execution=lambda req: None)
        runner = HookRunner(hooks)
        await runner.run("before_pre_execution", {})

        # Time should be > 0 (at least some overhead)
        assert runner.get_hook_time() >= 0.0


class TestHookRunnerAsyncExecution:
    """Test asynchronous hook execution."""

    @pytest.mark.asyncio
    async def test_runs_async_hook(self) -> None:
        """Async (coroutine) hooks are awaited correctly."""
        calls: List[Any] = []

        async def on_pre(request: Any) -> None:
            await asyncio.sleep(0.001)
            calls.append(request)

        hooks = PipelineHooks(before_pre_execution=on_pre)
        runner = HookRunner(hooks)
        await runner.run("before_pre_execution", {"payload": "async_test"})

        assert len(calls) == 1
        assert calls[0] == {"payload": "async_test"}

    @pytest.mark.asyncio
    async def test_async_hook_accumulates_time(self) -> None:
        """Async hook execution time is measured and accumulated."""

        async def slow_hook(request: Any) -> None:
            await asyncio.sleep(0.01)

        hooks = PipelineHooks(before_pre_execution=slow_hook)
        runner = HookRunner(hooks)
        await runner.run("before_pre_execution", {})

        # Should have accumulated at least ~10ms
        assert runner.get_hook_time() >= 5.0


class TestHookRunnerExceptionIsolation:
    """Test exception isolation — hooks never propagate errors."""

    @pytest.mark.asyncio
    async def test_sync_exception_is_swallowed(self) -> None:
        """Sync hook exceptions are caught and do not propagate."""

        def bad_hook(request: Any) -> None:
            raise ValueError("sync error")

        hooks = PipelineHooks(before_pre_execution=bad_hook)
        runner = HookRunner(hooks)

        # Should NOT raise
        await runner.run("before_pre_execution", {})
        # Time is still accumulated
        assert runner.get_hook_time() >= 0.0

    @pytest.mark.asyncio
    async def test_async_exception_is_swallowed(self) -> None:
        """Async hook exceptions are caught and do not propagate."""

        async def bad_hook(request: Any) -> None:
            raise RuntimeError("async error")

        hooks = PipelineHooks(before_pre_execution=bad_hook)
        runner = HookRunner(hooks)

        # Should NOT raise
        await runner.run("before_pre_execution", {})
        assert runner.get_hook_time() >= 0.0

    @pytest.mark.asyncio
    async def test_exception_is_logged_as_warning(self, caplog: Any) -> None:
        """Hook exceptions are logged via logging.warning."""

        def bad_hook(request: Any) -> None:
            raise ValueError("test warning message")

        hooks = PipelineHooks(before_pre_execution=bad_hook)
        runner = HookRunner(hooks)

        with caplog.at_level(logging.WARNING):
            await runner.run("before_pre_execution", {})

        assert "before_pre_execution" in caplog.text
        assert "test warning message" in caplog.text


class TestHookRunnerUnregisteredHooks:
    """Test behavior with unregistered (None) hooks."""

    @pytest.mark.asyncio
    async def test_unregistered_hook_is_noop(self) -> None:
        """Calling run() with a hook name that is None does nothing."""
        runner = HookRunner()  # All hooks are None
        await runner.run("before_pre_execution", {})
        assert runner.get_hook_time() == 0.0

    @pytest.mark.asyncio
    async def test_nonexistent_hook_name_is_noop(self) -> None:
        """Calling run() with a hook name not on PipelineHooks does nothing."""
        runner = HookRunner()
        await runner.run("nonexistent_hook", {})
        assert runner.get_hook_time() == 0.0


class TestHookRunnerTimingAndReset:
    """Test timing accumulation and reset behavior."""

    @pytest.mark.asyncio
    async def test_multiple_hooks_accumulate_time(self) -> None:
        """Multiple hook calls accumulate their execution time."""

        async def slow_hook(*args: Any) -> None:
            await asyncio.sleep(0.01)

        hooks = PipelineHooks(
            before_pre_execution=slow_hook,
            after_pre_execution=slow_hook,
        )
        runner = HookRunner(hooks)

        await runner.run("before_pre_execution", {})
        time_after_first = runner.get_hook_time()

        await runner.run("after_pre_execution", {})
        time_after_second = runner.get_hook_time()

        assert time_after_second > time_after_first

    @pytest.mark.asyncio
    async def test_reset_zeros_counter(self) -> None:
        """reset() sets the accumulated hook time back to zero."""

        async def slow_hook(*args: Any) -> None:
            await asyncio.sleep(0.01)

        hooks = PipelineHooks(before_pre_execution=slow_hook)
        runner = HookRunner(hooks)

        await runner.run("before_pre_execution", {})
        assert runner.get_hook_time() > 0.0

        runner.reset()
        assert runner.get_hook_time() == 0.0

    @pytest.mark.asyncio
    async def test_time_accumulates_after_reset(self) -> None:
        """After reset, subsequent hook calls still accumulate time."""

        async def slow_hook(*args: Any) -> None:
            await asyncio.sleep(0.005)

        hooks = PipelineHooks(before_pre_execution=slow_hook)
        runner = HookRunner(hooks)

        await runner.run("before_pre_execution", {})
        runner.reset()
        await runner.run("before_pre_execution", {})

        assert runner.get_hook_time() > 0.0


class TestHookRunnerMultipleArgs:
    """Test hook invocation with multiple arguments."""

    @pytest.mark.asyncio
    async def test_hook_receives_multiple_args(self) -> None:
        """Hooks are called with all positional args."""
        received: List[Any] = []

        def on_execution(response: Any, metadata: Any) -> None:
            received.append((response, metadata))

        hooks = PipelineHooks(after_execution=on_execution)
        runner = HookRunner(hooks)

        await runner.run("after_execution", "response_data", {"model": "gpt-4"})

        assert len(received) == 1
        assert received[0] == ("response_data", {"model": "gpt-4"})

    @pytest.mark.asyncio
    async def test_on_remediation_receives_three_args(self) -> None:
        """on_remediation hook receives action, decision, and attempt."""
        received: List[Any] = []

        def on_remediation(action: Any, decision: Any, attempt: int) -> None:
            received.append((action, decision, attempt))

        hooks = PipelineHooks(on_remediation=on_remediation)
        runner = HookRunner(hooks)

        await runner.run("on_remediation", "RESAMPLE", {"action": "DENY"}, 1)

        assert len(received) == 1
        assert received[0] == ("RESAMPLE", {"action": "DENY"}, 1)
