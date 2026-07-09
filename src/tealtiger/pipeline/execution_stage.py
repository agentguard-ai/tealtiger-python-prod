"""Multi-Stage Defense Pipeline — Execution Stage (Python SDK).

Delegates LLM provider calls to the ObserveProxy, which transparently
handles cost tracking, audit logging, PII scanning, and behavioral baseline.
Extracts response metadata (model, latency, usage, cost) and handles
provider errors gracefully.

Module: pipeline/execution_stage
Requirements: 11.2, 11.5, 11.6
"""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

from .types import ExecutionMetadata, ExecutionResult, PipelineRequest


@runtime_checkable
class ObserveProxy(Protocol):
    """Protocol for the ObserveProxy interface.

    The observe proxy wraps the underlying LLM provider client and
    transparently instruments calls with cost tracking, audit logging,
    PII scanning, and behavioral baseline construction.

    Implementations may support:
    - A generic ``call(payload)`` method for direct invocation
    - Attribute-based access (e.g., ``proxy.chat.completions.create(payload)``)
      via ``__getattr__`` chains
    - A ``get_cost()`` method returning accumulated cost data
    """

    async def call(self, payload: dict[str, Any]) -> Any:
        """Invoke the provider with the given payload."""
        ...

    def get_cost(self) -> dict[str, Any]:
        """Return the current cost accumulator state.

        Returns a dict with at least:
        - total_cost: float — accumulated USD cost
        - request_count: int — number of requests made
        """
        ...


class ExecutionStage:
    """Forwards requests to the LLM provider through the ObserveProxy.

    The ExecutionStage does NOT produce its own StageDecision —
    instrumentation data is recorded by the ObserveProxy's existing
    audit and cost systems.

    The proxy is a transparent wrapper over the original provider client,
    so calling methods on it (e.g., ``proxy.chat.completions.create(payload)``)
    triggers the same instrumentation as observe() mode.

    Args:
        observe_proxy: An object implementing the ObserveProxy protocol,
            or any object with a ``call(payload)`` method or attribute-based
            access to provider methods.
    """

    def __init__(self, observe_proxy: Any) -> None:
        self._observe_proxy = observe_proxy

    async def execute(self, request: PipelineRequest) -> ExecutionResult:
        """Forward request to LLM provider via ObserveProxy.

        Returns the raw provider response and extracted metadata on success,
        or error details on failure.

        The method uses the request payload to determine how to call the
        provider:
        - If payload contains a ``_call`` field, it's used as the method path
          (e.g., ``"chat.completions.create"``) for dynamic dispatch.
        - Otherwise, falls back to the proxy's ``call()`` method if available,
          or resolves ``chat.completions.create`` via attribute access.

        Args:
            request: The pipeline request containing the LLM payload.

        Returns:
            An ExecutionResult with success status, response, metadata,
            and error details (if any).
        """
        start_time = time.perf_counter()

        try:
            # Snapshot cost before the call
            cost_before = self._get_cost_snapshot()

            # Invoke the provider through the proxy
            response = await self._invoke_provider(request.payload)

            latency_ms = (time.perf_counter() - start_time) * 1000.0

            # Extract metadata from response and cost accumulator
            metadata = self._extract_metadata(response, latency_ms, cost_before)

            return ExecutionResult(
                success=True,
                response=response,
                metadata=metadata,
            )

        except Exception as exc:
            return ExecutionResult(
                success=False,
                response=None,
                metadata=None,
                error={
                    "message": str(exc) if str(exc) else type(exc).__name__,
                    "code": getattr(exc, "code", None)
                    or getattr(exc, "status", None)
                    or getattr(exc, "status_code", None)
                    or "",
                },
            )

    async def _invoke_provider(self, payload: dict[str, Any]) -> Any:
        """Invoke the LLM provider through the ObserveProxy.

        Supports multiple dispatch modes:
        1. Explicit method path via ``payload["_call"]``
           (e.g., ``"chat.completions.create"``)
        2. A generic ``call(payload)`` method on the proxy
        3. Default attribute resolution: ``proxy.chat.completions.create``

        The ObserveProxy intercepts these calls transparently, applying
        cost tracking, audit logging, PII scanning, and behavioral
        baseline instrumentation.

        Args:
            payload: The raw request payload for the LLM provider.

        Returns:
            The raw provider response.

        Raises:
            RuntimeError: If no callable method can be resolved on the proxy.
        """
        # Extract the method path (if specified) and clean call args
        method_path: str | None = payload.get("_call")  # type: ignore[assignment]
        call_args = {k: v for k, v in payload.items() if k != "_call"} if method_path else payload

        # Mode 1: Explicit method path — resolve via getattr chain
        if method_path:
            method = self._resolve_method(self._observe_proxy, method_path)
            if callable(method):
                result = method(call_args)
                # Support both sync and async callables
                if _is_awaitable(result):
                    return await result
                return result

        # Mode 2: Generic call() method on the proxy
        if hasattr(self._observe_proxy, "call") and callable(self._observe_proxy.call):
            result = self._observe_proxy.call(call_args if method_path else payload)
            if _is_awaitable(result):
                return await result
            return result

        # Mode 3: Default path — chat.completions.create
        default_path = "chat.completions.create"
        method = self._resolve_method(self._observe_proxy, default_path)
        if callable(method):
            result = method(payload)
            if _is_awaitable(result):
                return await result
            return result

        raise RuntimeError(
            f"Unable to resolve provider method on ObserveProxy. "
            f"Tried: {method_path or default_path}, call(). "
            f"Ensure the proxy exposes a callable interface."
        )

    def _resolve_method(self, obj: Any, path: str) -> Any:
        """Resolve a dotted method path on an object.

        For example, ``"chat.completions.create"`` resolves to
        ``obj.chat.completions.create``.

        Args:
            obj: The root object to resolve from.
            path: A dot-separated method path.

        Returns:
            The resolved attribute, or None if resolution fails.
        """
        current = obj
        for part in path.split("."):
            if current is None:
                return None
            try:
                current = getattr(current, part)
            except AttributeError:
                # Try dict-style access as fallback
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None
        return current

    def _get_cost_snapshot(self) -> dict[str, Any]:
        """Get the current cost accumulator snapshot from the proxy.

        Returns a default dict if the proxy doesn't expose cost tracking.
        """
        if hasattr(self._observe_proxy, "get_cost") and callable(
            self._observe_proxy.get_cost
        ):
            try:
                return self._observe_proxy.get_cost()
            except Exception:
                pass
        return {"total_cost": 0.0, "request_count": 0}

    def _extract_metadata(
        self,
        response: Any,
        latency_ms: float,
        cost_before: dict[str, Any],
    ) -> ExecutionMetadata:
        """Extract execution metadata from the provider response and cost data.

        Attempts to read standard OpenAI-compatible fields from the response:
        - model: ``response.model`` or ``response["model"]``
        - usage: ``response.usage.{prompt_tokens, completion_tokens, total_tokens}``
        - cost: computed from the cost accumulator delta

        Args:
            response: The raw provider response.
            latency_ms: The measured call latency in milliseconds.
            cost_before: Cost accumulator snapshot taken before the call.

        Returns:
            An ExecutionMetadata dataclass with extracted values.
        """
        model = self._get_attr_or_key(response, "model", "unknown")
        usage = self._extract_usage(response)

        # Compute cost delta from the proxy's cost accumulator
        cost_after = self._get_cost_snapshot()
        cost_usd = max(
            0.0,
            cost_after.get("total_cost", 0.0) - cost_before.get("total_cost", 0.0),
        )

        return ExecutionMetadata(
            model=model,
            latency_ms=latency_ms,
            usage=usage,
            cost_usd=cost_usd,
        )

    def _extract_usage(self, response: Any) -> dict[str, int]:
        """Extract token usage from the provider response.

        Handles the OpenAI-compatible format (prompt_tokens/completion_tokens)
        and falls back to input_tokens/output_tokens for Anthropic-style responses.

        Args:
            response: The raw provider response.

        Returns:
            A dict with input_tokens, output_tokens, and total_tokens.
        """
        response_usage = self._get_attr_or_key(response, "usage", None)
        if response_usage is None:
            return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        # OpenAI: prompt_tokens / completion_tokens
        # Anthropic: input_tokens / output_tokens
        input_tokens: int = (
            self._get_attr_or_key(response_usage, "prompt_tokens", None)
            or self._get_attr_or_key(response_usage, "input_tokens", None)
            or 0
        )
        output_tokens: int = (
            self._get_attr_or_key(response_usage, "completion_tokens", None)
            or self._get_attr_or_key(response_usage, "output_tokens", None)
            or 0
        )
        total_tokens: int = (
            self._get_attr_or_key(response_usage, "total_tokens", None)
            or (input_tokens + output_tokens)
        )

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }

    @staticmethod
    def _get_attr_or_key(obj: Any, key: str, default: Any = None) -> Any:
        """Get a value from an object by attribute or dict key.

        Supports both object-style (``obj.key``) and dict-style
        (``obj["key"]``) access patterns.

        Args:
            obj: The source object.
            key: The attribute/key name.
            default: Fallback value if not found.

        Returns:
            The resolved value or the default.
        """
        if obj is None:
            return default
        # Try attribute access first
        val = getattr(obj, key, None)
        if val is not None:
            return val
        # Try dict-style access
        if isinstance(obj, dict):
            return obj.get(key, default)
        return default


def _is_awaitable(obj: Any) -> bool:
    """Check if an object is awaitable (coroutine or has __await__)."""
    import asyncio

    return asyncio.iscoroutine(obj) or hasattr(obj, "__await__")
