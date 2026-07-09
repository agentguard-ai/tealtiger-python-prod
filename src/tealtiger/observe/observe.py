"""
observe() — Zero-config instrumentation for LLM provider clients.

Wraps any supported provider client in a transparent proxy that adds:
- Cost tracking (per-request, per-session, per-agent)
- Audit logging (every request/response/error/tool call)
- Behavioral baseline (P50/P95/P99 from first N requests)
- PII detection (REPORT_ONLY — never blocks)
- Kill switch (freeze/unfreeze)

All instrumentation is in-process, deterministic, and adds <5ms overhead.

Usage:
    from tealtiger.observe import observe

    client = observe(OpenAI())
    # Use exactly like normal — all calls are now instrumented

Requirements: 8.1, 8.2, 8.3, 8.5
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import time
import uuid
from typing import Any, List, Optional

from .types import (
    BaselineResult,
    BaselineSample,
    ObserveCostSummary,
    ProviderSignature,
)
from .errors import FrozenAgentError
from .provider_detector import detect_provider
from .cost_accumulator import CostAccumulator
from .behavioral_baseline import BehavioralBaseline
from .pii_scanner import ObservePIIScanner
from .observe_audit import ObserveAuditLogger
from .freeze_registry import FreezeRegistry

from ..core.engine.v2_1.governance_engine import GovernanceEngineV21, GovernanceEngineV21Options
from ..core.engine.v2_1.types import DecisionV21
from ..core.engine.v2_1.errors import SealConfigurationError


# ---------------------------------------------------------------------------
# Telemetry accessor names — these are exposed as methods on the proxy
# ---------------------------------------------------------------------------

_TELEMETRY_ACCESSORS = frozenset({
    "get_cost",
    "get_agent_cost",
    "get_baseline",
    "get_agent_id",
    "get_session_id",
    "get_decisions",
})


# ---------------------------------------------------------------------------
# Simple namespace for passing usage data to CostAccumulator
# ---------------------------------------------------------------------------

class _UsageNamespace:
    """Lightweight object exposing input_tokens/output_tokens attributes.

    CostAccumulator.record_cost() uses duck-typed attribute access for
    usage data. This bridges the dict returned by provider extractors
    into the expected attribute-based interface.
    """

    __slots__ = ("input_tokens", "output_tokens")

    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


# ---------------------------------------------------------------------------
# _NamespaceProxy — wraps nested namespace objects (e.g. client.chat.completions)
# ---------------------------------------------------------------------------

class _NamespaceProxy:
    """Proxy for nested namespace objects on a provider client.

    Recursively wraps attribute access so that deeply nested intercept
    targets (e.g. ``client.chat.completions.create``) are correctly
    detected and instrumented.

    Args:
        namespace: The namespace object being proxied.
        observe_proxy: The owning ObserveProxy instance.
        path: Dot-separated path from root (e.g. ``"chat.completions"``).
    """

    __slots__ = ("_namespace", "_observe_proxy", "_path")

    def __init__(
        self,
        namespace: Any,
        observe_proxy: "ObserveProxy",
        path: str,
    ) -> None:
        object.__setattr__(self, "_namespace", namespace)
        object.__setattr__(self, "_observe_proxy", observe_proxy)
        object.__setattr__(self, "_path", path)

    def __getattr__(self, name: str) -> Any:
        namespace = object.__getattribute__(self, "_namespace")
        observe_proxy = object.__getattribute__(self, "_observe_proxy")
        path = object.__getattribute__(self, "_path")

        value = getattr(namespace, name)
        current_path = f"{path}.{name}"

        # If it's callable, check if it's an intercept target
        if callable(value):
            if observe_proxy._is_intercept_target(current_path) or observe_proxy._is_intercept_target(name):
                return observe_proxy._create_intercepted_method(value, name)
            # Non-intercepted callable — return bound to original namespace
            return value

        # If it's a non-None object (nested namespace), wrap recursively
        if value is not None and isinstance(value, object) and not isinstance(value, (str, int, float, bool, list, tuple)):
            return _NamespaceProxy(value, observe_proxy, current_path)

        return value

    def __repr__(self) -> str:
        path = object.__getattribute__(self, "_path")
        return f"<_NamespaceProxy path={path!r}>"


# ---------------------------------------------------------------------------
# ObserveProxy — main proxy class
# ---------------------------------------------------------------------------

class ObserveProxy:
    """Transparent instrumentation proxy wrapping a supported LLM provider client.

    Delegates all attribute access to the wrapped client while intercepting
    provider-specific API methods (e.g. ``chat.completions.create``) to run
    the 11-step instrumentation pipeline.

    Exposes telemetry accessors (``get_cost``, ``get_agent_cost``,
    ``get_baseline``, ``get_agent_id``, ``get_session_id``) as first-class
    methods on the proxy.

    This class should not be instantiated directly — use :func:`observe`.

    Args:
        client: The original provider client to wrap.
        provider_signature: Detected provider configuration.
        agent_id: Agent identifier.
        session_id: Session identifier.
        cost_accumulator: Cost tracking instance.
        baseline: Behavioral baseline instance.
        pii_scanner: PII scanner instance.
        audit_logger: Audit logger instance.
    """

    def __init__(
        self,
        client: Any,
        provider_signature: ProviderSignature,
        agent_id: str,
        session_id: str,
        cost_accumulator: CostAccumulator,
        baseline: BehavioralBaseline,
        pii_scanner: ObservePIIScanner,
        audit_logger: ObserveAuditLogger,
        governance: bool = False,
        governance_engine: Optional[GovernanceEngineV21] = None,
    ) -> None:
        # Store all state using object.__setattr__ to avoid triggering __getattr__
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_provider_signature", provider_signature)
        object.__setattr__(self, "_agent_id", agent_id)
        object.__setattr__(self, "_session_id", session_id)
        object.__setattr__(self, "_cost_accumulator", cost_accumulator)
        object.__setattr__(self, "_baseline", baseline)
        object.__setattr__(self, "_pii_scanner", pii_scanner)
        object.__setattr__(self, "_audit_logger", audit_logger)
        object.__setattr__(self, "_request_count", 0)
        object.__setattr__(self, "_baseline_complete_emitted", False)
        object.__setattr__(self, "_governance", governance)
        object.__setattr__(self, "_governance_engine", governance_engine)
        object.__setattr__(self, "_decisions", [])

    # ------------------------------------------------------------------
    # Telemetry accessors
    # ------------------------------------------------------------------

    def get_cost(self) -> ObserveCostSummary:
        """Get cumulative cost for the current session.

        Returns:
            ObserveCostSummary with total cost, request count, and breakdown.
        """
        return self._cost_accumulator.get_session_cost(self._session_id)

    def get_agent_cost(self) -> ObserveCostSummary:
        """Get cumulative cost for the agent (persists across sessions).

        Returns:
            ObserveCostSummary with total cost, request count, and breakdown.
        """
        return self._cost_accumulator.get_agent_cost(self._agent_id)

    def get_baseline(self) -> BaselineResult:
        """Get the behavioral baseline status and statistics.

        Returns:
            BaselineResult with completion status and computed percentiles.
        """
        return self._baseline.get_baseline()

    def get_agent_id(self) -> str:
        """Get the agent identifier for this proxy.

        Returns:
            The agent ID string (auto-generated UUID v4 or user-provided).
        """
        return self._agent_id

    def get_session_id(self) -> str:
        """Get the session identifier for this proxy.

        Returns:
            The session ID string (auto-generated UUID v4 or user-provided).
        """
        return self._session_id

    def get_decisions(self) -> List[DecisionV21]:
        """Get all TEEC v2.1 governance decisions produced by this proxy.

        Returns an empty list when governance mode is disabled.

        Returns:
            List of DecisionV21 objects produced by intercepted calls.
        """
        return list(object.__getattribute__(self, "_decisions"))

    # ------------------------------------------------------------------
    # __getattr__ — delegation with intercept logic
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the wrapped client with interception.

        Resolution order:
          1. If *name* is a telemetry accessor, return the bound method.
          2. Get the attribute from the wrapped client.
          3. If callable and in the intercept list, return instrumented wrapper.
          4. If a non-primitive object (namespace), return a _NamespaceProxy.
          5. Otherwise return the value as-is.

        Args:
            name: The attribute name being accessed.

        Returns:
            The resolved attribute, possibly wrapped for instrumentation.
        """
        # 1. Telemetry accessors
        if name in _TELEMETRY_ACCESSORS:
            return getattr(self, name)

        # 2. Get from wrapped client
        client = object.__getattribute__(self, "_client")
        value = getattr(client, name)

        # 3. Callable — check intercept
        if callable(value):
            if self._is_intercept_target(name):
                return self._create_intercepted_method(value, name)
            # Return non-intercepted callable bound to original client
            return value

        # 4. Non-primitive object — namespace proxy
        if value is not None and isinstance(value, object) and not isinstance(
            value, (str, int, float, bool, list, tuple)
        ):
            return _NamespaceProxy(value, self, name)

        # 5. Primitive — return as-is
        return value

    # ------------------------------------------------------------------
    # Intercept detection
    # ------------------------------------------------------------------

    def _is_intercept_target(self, method_path: str) -> bool:
        """Check if a method path matches any configured intercept method.

        Matches if the method_path equals an intercept method exactly, or
        if an intercept method ends with ``.{method_path}`` (allowing
        short names like ``"create"`` to match ``"chat.completions.create"``).

        Args:
            method_path: The dotted method path to check.

        Returns:
            True if this method should be intercepted.
        """
        provider_sig = object.__getattribute__(self, "_provider_signature")
        for m in provider_sig.intercept_methods:
            if m == method_path or m.endswith(f".{method_path}"):
                return True
        return False

    # ------------------------------------------------------------------
    # Instrumented method creation
    # ------------------------------------------------------------------

    def _create_intercepted_method(self, original_method: Any, method_name: str) -> Any:
        """Create an instrumented wrapper around a provider method.

        Implements the full 11-step instrumentation pipeline:
          1. Check FreezeRegistry — raise FrozenAgentError if frozen
          2. PII scan on request payload
          3. Log request audit event
          4. Forward to provider, measure latency
          5. Extract usage and compute cost
          6. PII scan on response payload
          7. Extract and log tool calls (arguments hashed with SHA-256)
          8. Feed BehavioralBaseline sample
          9. Check if baseline just completed, emit event
         10. Log response audit event
         11. Return original response unmodified

        On provider error: log error event, re-throw original exception.

        Detects whether the original method is a coroutine function and
        returns an async wrapper if so, otherwise a sync wrapper.

        Args:
            original_method: The original callable to wrap.
            method_name: Human-readable method name (for auditing).

        Returns:
            A wrapper function (sync or async) implementing the pipeline.
        """
        proxy = self

        if inspect.iscoroutinefunction(original_method):
            @functools.wraps(original_method)
            async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await proxy._run_pipeline_async(original_method, method_name, args, kwargs)
            return _async_wrapper
        else:
            @functools.wraps(original_method)
            def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                return proxy._run_pipeline_sync(original_method, method_name, args, kwargs)
            return _sync_wrapper

    # ------------------------------------------------------------------
    # 11-step pipeline — sync version
    # ------------------------------------------------------------------

    def _run_pipeline_sync(
        self,
        original_method: Any,
        method_name: str,
        args: tuple,
        kwargs: dict,
    ) -> Any:
        """Execute the 11-step instrumentation pipeline (synchronous).

        Args:
            original_method: The provider method to call.
            method_name: Method name for logging.
            args: Positional arguments for the method.
            kwargs: Keyword arguments for the method.

        Returns:
            The unmodified provider response.

        Raises:
            FrozenAgentError: If the agent is currently frozen.
            Exception: Re-raises any provider error after logging.
        """
        agent_id = object.__getattribute__(self, "_agent_id")
        session_id = object.__getattribute__(self, "_session_id")
        provider_sig = object.__getattribute__(self, "_provider_signature")
        cost_acc = object.__getattribute__(self, "_cost_accumulator")
        baseline = object.__getattribute__(self, "_baseline")
        pii_scanner = object.__getattribute__(self, "_pii_scanner")
        audit_logger = object.__getattribute__(self, "_audit_logger")

        request_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        registry = FreezeRegistry.get_instance()

        # Step 1: Check kill switch
        if registry.is_frozen(agent_id):
            is_wildcard = registry.is_wildcard_freeze()
            audit_logger.log_freeze_block(
                agent_id=agent_id,
                request_id=request_id,
                correlation_id=correlation_id,
                is_wildcard=is_wildcard,
            )
            raise FrozenAgentError(agent_id, is_wildcard)

        # Step 2: PII scan on request payload
        request_payload = args[0] if args else kwargs
        request_pii = pii_scanner.scan(request_payload, "request")

        # Step 3: Log request audit event
        model = provider_sig.model_extractor(request_payload, None)
        audit_logger.log_request(
            agent_id=agent_id,
            session_id=session_id,
            request_id=request_id,
            correlation_id=correlation_id,
            provider=provider_sig.provider,
            model=model,
        )

        # Step 4: Forward to provider, measure latency
        start_ns = time.perf_counter_ns()
        try:
            response = original_method(*args, **kwargs)
        except Exception as exc:
            # Log error, then re-throw unchanged
            audit_logger.log_error(
                request_id=request_id,
                correlation_id=correlation_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

        # Step 5: Extract usage and compute cost
        usage_dict = provider_sig.usage_extractor(response)
        resolved_model = provider_sig.model_extractor(request_payload, response)

        usage_obj: Any = None
        if usage_dict is not None:
            usage_obj = _UsageNamespace(
                input_tokens=usage_dict.get("inputTokens", 0),
                output_tokens=usage_dict.get("outputTokens", 0),
            )

        cost_result = cost_acc.record_cost(
            agent_id=agent_id,
            session_id=session_id,
            request_id=request_id,
            model=resolved_model,
            provider=provider_sig.provider,
            usage=usage_obj,
        )

        # Step 6: PII scan on response payload
        response_pii = pii_scanner.scan(response, "response")

        # Step 7: Extract and log tool calls
        tool_calls = provider_sig.tool_call_extractor(response)
        for tc in tool_calls:
            audit_logger.log_tool_call(
                request_id=request_id,
                correlation_id=correlation_id,
                tool_name=tc.tool_name,
                argument_count=tc.argument_count,
                arguments_hash=tc.arguments_hash,
            )

        # Step 8: Feed behavioral baseline
        baseline.add_sample(BaselineSample(
            latency_ms=latency_ms,
            input_tokens=usage_dict.get("inputTokens", 0) if usage_dict else 0,
            output_tokens=usage_dict.get("outputTokens", 0) if usage_dict else 0,
            cost_usd=cost_result.cost,
            tool_call_count=len(tool_calls),
        ))

        # Step 9: Check if baseline just completed
        baseline_complete_emitted = object.__getattribute__(self, "_baseline_complete_emitted")
        if baseline.is_complete() and not baseline_complete_emitted:
            object.__setattr__(self, "_baseline_complete_emitted", True)
            audit_logger.log_baseline_complete(agent_id, session_id)

        # Step 10: Log response audit event
        combined_pii = self._combine_pii(request_pii, response_pii)
        output_token_count = usage_dict.get("outputTokens", 0) if usage_dict else 0
        audit_logger.log_response(
            request_id=request_id,
            correlation_id=correlation_id,
            output_token_count=output_token_count,
            cost=cost_result.cost,
            latency_ms=latency_ms,
            pii_detections=combined_pii,
        )

        # Step 11: Return original response UNMODIFIED
        request_count = object.__getattribute__(self, "_request_count")
        object.__setattr__(self, "_request_count", request_count + 1)

        # Step 12: Governance decision production (if enabled)
        governance = object.__getattribute__(self, "_governance")
        if governance:
            governance_engine = object.__getattribute__(self, "_governance_engine")
            decisions_list = object.__getattribute__(self, "_decisions")
            governance_request = self._build_governance_request(request_payload, method_name)
            ctx = {"correlation_id": correlation_id, "agent_id": agent_id}
            # GovernanceEngineV21.evaluate is async — run synchronously
            decision = asyncio.run(governance_engine.evaluate(governance_request, ctx))
            decisions_list.append(decision)

        return response

    # ------------------------------------------------------------------
    # 11-step pipeline — async version
    # ------------------------------------------------------------------

    async def _run_pipeline_async(
        self,
        original_method: Any,
        method_name: str,
        args: tuple,
        kwargs: dict,
    ) -> Any:
        """Execute the 11-step instrumentation pipeline (asynchronous).

        Identical to :meth:`_run_pipeline_sync` except the provider call
        is awaited. All other steps are synchronous.

        Args:
            original_method: The async provider method to call.
            method_name: Method name for logging.
            args: Positional arguments for the method.
            kwargs: Keyword arguments for the method.

        Returns:
            The unmodified provider response.

        Raises:
            FrozenAgentError: If the agent is currently frozen.
            Exception: Re-raises any provider error after logging.
        """
        agent_id = object.__getattribute__(self, "_agent_id")
        session_id = object.__getattribute__(self, "_session_id")
        provider_sig = object.__getattribute__(self, "_provider_signature")
        cost_acc = object.__getattribute__(self, "_cost_accumulator")
        baseline = object.__getattribute__(self, "_baseline")
        pii_scanner = object.__getattribute__(self, "_pii_scanner")
        audit_logger = object.__getattribute__(self, "_audit_logger")

        request_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        registry = FreezeRegistry.get_instance()

        # Step 1: Check kill switch
        if registry.is_frozen(agent_id):
            is_wildcard = registry.is_wildcard_freeze()
            audit_logger.log_freeze_block(
                agent_id=agent_id,
                request_id=request_id,
                correlation_id=correlation_id,
                is_wildcard=is_wildcard,
            )
            raise FrozenAgentError(agent_id, is_wildcard)

        # Step 2: PII scan on request payload
        request_payload = args[0] if args else kwargs
        request_pii = pii_scanner.scan(request_payload, "request")

        # Step 3: Log request audit event
        model = provider_sig.model_extractor(request_payload, None)
        audit_logger.log_request(
            agent_id=agent_id,
            session_id=session_id,
            request_id=request_id,
            correlation_id=correlation_id,
            provider=provider_sig.provider,
            model=model,
        )

        # Step 4: Forward to provider, measure latency (AWAIT)
        start_ns = time.perf_counter_ns()
        try:
            response = await original_method(*args, **kwargs)
        except Exception as exc:
            # Log error, then re-throw unchanged
            audit_logger.log_error(
                request_id=request_id,
                correlation_id=correlation_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

        # Step 5: Extract usage and compute cost
        usage_dict = provider_sig.usage_extractor(response)
        resolved_model = provider_sig.model_extractor(request_payload, response)

        usage_obj: Any = None
        if usage_dict is not None:
            usage_obj = _UsageNamespace(
                input_tokens=usage_dict.get("inputTokens", 0),
                output_tokens=usage_dict.get("outputTokens", 0),
            )

        cost_result = cost_acc.record_cost(
            agent_id=agent_id,
            session_id=session_id,
            request_id=request_id,
            model=resolved_model,
            provider=provider_sig.provider,
            usage=usage_obj,
        )

        # Step 6: PII scan on response payload
        response_pii = pii_scanner.scan(response, "response")

        # Step 7: Extract and log tool calls
        tool_calls = provider_sig.tool_call_extractor(response)
        for tc in tool_calls:
            audit_logger.log_tool_call(
                request_id=request_id,
                correlation_id=correlation_id,
                tool_name=tc.tool_name,
                argument_count=tc.argument_count,
                arguments_hash=tc.arguments_hash,
            )

        # Step 8: Feed behavioral baseline
        baseline.add_sample(BaselineSample(
            latency_ms=latency_ms,
            input_tokens=usage_dict.get("inputTokens", 0) if usage_dict else 0,
            output_tokens=usage_dict.get("outputTokens", 0) if usage_dict else 0,
            cost_usd=cost_result.cost,
            tool_call_count=len(tool_calls),
        ))

        # Step 9: Check if baseline just completed
        baseline_complete_emitted = object.__getattribute__(self, "_baseline_complete_emitted")
        if baseline.is_complete() and not baseline_complete_emitted:
            object.__setattr__(self, "_baseline_complete_emitted", True)
            audit_logger.log_baseline_complete(agent_id, session_id)

        # Step 10: Log response audit event
        combined_pii = self._combine_pii(request_pii, response_pii)
        output_token_count = usage_dict.get("outputTokens", 0) if usage_dict else 0
        audit_logger.log_response(
            request_id=request_id,
            correlation_id=correlation_id,
            output_token_count=output_token_count,
            cost=cost_result.cost,
            latency_ms=latency_ms,
            pii_detections=combined_pii,
        )

        # Step 11: Return original response UNMODIFIED
        request_count = object.__getattribute__(self, "_request_count")
        object.__setattr__(self, "_request_count", request_count + 1)

        # Step 12: Governance decision production (if enabled)
        governance = object.__getattribute__(self, "_governance")
        if governance:
            governance_engine = object.__getattribute__(self, "_governance_engine")
            decisions_list = object.__getattribute__(self, "_decisions")
            governance_request = self._build_governance_request(request_payload, method_name)
            ctx = {"correlation_id": correlation_id, "agent_id": agent_id}
            decision = await governance_engine.evaluate(governance_request, ctx)
            decisions_list.append(decision)

        return response

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _combine_pii(request_pii: Any, response_pii: Any) -> Any:
        """Combine request and response PII detections into a single summary.

        Args:
            request_pii: PII detection result from request scan (or None).
            response_pii: PII detection result from response scan (or None).

        Returns:
            Combined dict with count, types, and phase — or None if no PII.
        """
        if request_pii is None and response_pii is None:
            return None

        req_count = request_pii.count if request_pii else 0
        resp_count = response_pii.count if response_pii else 0
        req_types = request_pii.types if request_pii else []
        resp_types = response_pii.types if response_pii else []

        # De-duplicate types
        all_types = list(dict.fromkeys(req_types + resp_types))

        return {
            "count": req_count + resp_count,
            "types": all_types,
            "phase": "response" if response_pii else "request",
        }

    @staticmethod
    def _build_governance_request(request_payload: Any, method_name: str) -> dict:
        """Build a governance request dict from the raw request payload.

        Converts the request payload into a dict suitable for the
        GovernanceEngineV21 evaluation pipeline.

        Args:
            request_payload: The original request payload (may be dict, object, or other).
            method_name: The intercepted method name.

        Returns:
            A dict representing the request for governance evaluation.
        """
        if isinstance(request_payload, dict):
            return {**request_payload, "_method": method_name}
        # For non-dict payloads, wrap them
        return {"payload": str(request_payload), "_method": method_name}

    def __repr__(self) -> str:
        """Return a developer-friendly representation of the proxy."""
        agent_id = object.__getattribute__(self, "_agent_id")
        provider_sig = object.__getattribute__(self, "_provider_signature")
        return (
            f"<ObserveProxy provider={provider_sig.provider!r} "
            f"agent_id={agent_id!r}>"
        )


# ---------------------------------------------------------------------------
# observe() — public entry point
# ---------------------------------------------------------------------------

def observe(
    client: Any,
    *,
    agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
    baseline_window: int = 100,
    governance: bool = False,
    governance_seal_secret: Optional[str] = None,
) -> ObserveProxy:
    """Wrap a supported LLM provider client with zero-config instrumentation.

    Returns a drop-in proxy that is API-compatible with the original client.
    All calls are transparently instrumented with cost tracking, audit
    logging, behavioral baseline computation, PII detection, and kill
    switch support.

    When governance=True, also produces TEEC v2.1 governance decisions
    for each intercepted call, accessible via get_decisions().

    Args:
        client: A supported LLM provider client instance (e.g. ``OpenAI()``,
            ``Anthropic()``, ``GenerativeModel(...)``).
        agent_id: Optional agent identifier. Auto-generated UUID v4 if omitted.
        session_id: Optional session identifier. Auto-generated UUID v4 if omitted.
        baseline_window: Number of requests for baseline computation.
            Default: 100.
        governance: When True, enable TEEC v2.1 governance decision production.
        governance_seal_secret: Seal secret for HMAC computation.
            Required when governance=True.

    Returns:
        An :class:`ObserveProxy` that wraps the client with instrumentation.

    Raises:
        UnsupportedProviderError: If the client does not match any of the
            12 supported providers.
        SealConfigurationError: If governance=True but governance_seal_secret
            is not provided.

    Example::

        from tealtiger.observe import observe
        from openai import OpenAI

        # Zero-config: one line to instrument
        client = observe(OpenAI())

        # Use exactly like the original client
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
        )

        # Access telemetry
        print(client.get_cost())      # ObserveCostSummary(...)
        print(client.get_baseline())  # BaselineResult(is_complete=False, ...)

        # With governance enabled:
        client = observe(OpenAI(), governance=True, governance_seal_secret="my-secret")
        response = client.chat.completions.create(...)
        decisions = client.get_decisions()  # List[DecisionV21]
    """
    # 1. Detect provider
    provider_signature = detect_provider(client)

    # 2. Validate governance configuration
    if governance and not governance_seal_secret:
        raise SealConfigurationError(
            "ObserveProxy requires governance_seal_secret when governance=True."
        )

    # 3. Auto-generate IDs if not provided
    resolved_agent_id = agent_id if agent_id is not None else str(uuid.uuid4())
    resolved_session_id = session_id if session_id is not None else str(uuid.uuid4())

    # 4. Create all instrumentation components
    cost_accumulator = CostAccumulator()
    baseline = BehavioralBaseline(window_size=baseline_window)
    pii_scanner = ObservePIIScanner()
    audit_logger = ObserveAuditLogger()

    # 5. Create governance engine if governance is enabled
    governance_engine: Optional[GovernanceEngineV21] = None
    if governance:
        governance_engine = GovernanceEngineV21(GovernanceEngineV21Options(
            seal_secret=governance_seal_secret,
            agent_id=resolved_agent_id,
        ))

    # 6. Return the instrumented proxy
    return ObserveProxy(
        client=client,
        provider_signature=provider_signature,
        agent_id=resolved_agent_id,
        session_id=resolved_session_id,
        cost_accumulator=cost_accumulator,
        baseline=baseline,
        pii_scanner=pii_scanner,
        audit_logger=audit_logger,
        governance=governance,
        governance_engine=governance_engine,
    )
