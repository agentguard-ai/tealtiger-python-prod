"""HookRunner — Non-blocking lifecycle hook execution with error isolation.

Executes pipeline lifecycle hooks safely: exceptions are logged but never
propagated, and hook execution time is measured and accumulated separately
from stage evaluation time.

Module: pipeline/hook_runner
Requirements: 11.2, 11.5, 11.6
"""

from __future__ import annotations

import inspect
import logging
import time
from typing import Any, Optional

from .types import PipelineHooks

logger = logging.getLogger(__name__)


class HookRunner:
    """Non-blocking lifecycle hook executor with exception isolation.

    Accepts an optional ``PipelineHooks`` dataclass at construction.
    Hook execution is measured and accumulated, and any exception thrown
    by a hook is logged via :func:`logging.warning` but never propagated
    to the caller.

    This ensures hooks can observe pipeline behavior without interfering
    with governance outcomes (Property 10: Hook Non-Interference).

    Example::

        hooks = PipelineHooks(
            before_pre_execution=lambda req: print(f"Request: {req}"),
        )
        runner = HookRunner(hooks)
        await runner.run("before_pre_execution", request)
        print(f"Hook overhead: {runner.get_hook_time()}ms")
    """

    def __init__(self, hooks: Optional[PipelineHooks] = None) -> None:
        """Initialize the HookRunner.

        Args:
            hooks: Optional PipelineHooks dataclass containing lifecycle
                   callback functions. If None, all hooks are treated as
                   unregistered (no-ops).
        """
        self._hooks: PipelineHooks = hooks if hooks is not None else PipelineHooks()
        self._total_hook_time: float = 0.0

    async def run(self, hook_name: str, *args: Any) -> None:
        """Run a named hook safely with exception isolation.

        Looks up the hook by name on the PipelineHooks dataclass. If the hook
        is not registered (None), returns immediately. If the hook is a
        coroutine function, it is awaited; if synchronous, it is called
        directly. All exceptions are caught, logged, and swallowed.

        Execution time is measured using :func:`time.perf_counter` and
        accumulated in the internal counter.

        Args:
            hook_name: The attribute name of the hook on PipelineHooks
                       (e.g., ``"before_pre_execution"``).
            *args: Arguments to pass to the hook function.
        """
        hook = getattr(self._hooks, hook_name, None)
        if hook is None:
            return

        start = time.perf_counter()
        try:
            if inspect.iscoroutinefunction(hook):
                await hook(*args)
            else:
                hook(*args)
        except Exception as exc:
            # Hooks are non-blocking and non-fatal — log and continue
            # (Requirement 10.5: hook exceptions are logged but never propagated)
            logger.warning(
                '[HookRunner] Hook "%s" threw an error: %s',
                hook_name,
                str(exc),
            )
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self._total_hook_time += elapsed_ms

    def get_hook_time(self) -> float:
        """Return the total accumulated hook execution time in milliseconds.

        Returns:
            Total hook time in milliseconds across all hook invocations
            since construction or the last :meth:`reset` call.
        """
        return self._total_hook_time

    def reset(self) -> None:
        """Reset the accumulated hook time counter to zero.

        Useful for reusing the HookRunner across multiple pipeline executions.
        """
        self._total_hook_time = 0.0
