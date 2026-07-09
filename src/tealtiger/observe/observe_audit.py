"""
ObserveAuditLogger — writes structured audit events for observe() mode.

Integrates with the existing TealAudit system. All events use HASH
redaction by default (security-by-default posture).

Events are written synchronously within the request lifecycle so no
events are lost on process exit. If the output target is unavailable,
logs to stderr and continues (never blocks the request).

This is the Python port of observe-audit.ts from the TypeScript SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import sys


@dataclass
class AuditEvent:
    """A structured audit event emitted by the observe() instrumentation layer.

    Attributes:
        type: Event type identifier (e.g. 'observe.request', 'observe.response').
        timestamp: ISO 8601 UTC timestamp of when the event was created.
        correlation_id: Correlation ID linking related events across a request lifecycle.
        agent_id: Optional agent identifier.
        session_id: Optional session identifier.
        request_id: Optional per-request identifier.
        provider: Optional LLM provider name (e.g. 'openai', 'anthropic').
        model: Optional model name (e.g. 'gpt-4', 'claude-3-opus').
        data: Optional dictionary of event-specific payload data.
    """

    type: str
    timestamp: str
    correlation_id: str
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class ObserveAuditLogger:
    """Simple in-memory audit store for observe() mode.

    In production, this delegates to TealAudit's configured output.
    Provides structured audit logging for request/response lifecycle,
    tool calls, freeze blocks, and baseline completion events.
    """

    def __init__(self) -> None:
        """Initialize the audit logger with an empty event store."""
        self._events: List[AuditEvent] = []

    def _emit(self, event: AuditEvent) -> None:
        """Append an audit event to the internal store.

        If appending fails for any reason, logs to stderr and continues
        without raising — audit failures must never block the request path.

        Args:
            event: The AuditEvent to record.
        """
        try:
            self._events.append(event)
        except Exception:
            print(
                f"[TealTiger] Audit write failed, continuing: {event.type}",
                file=sys.stderr,
            )

    def _now(self) -> str:
        """Return the current UTC time as an ISO 8601 string.

        Returns:
            ISO 8601 formatted timestamp string.
        """
        return datetime.now(timezone.utc).isoformat()

    def log_request(
        self,
        *,
        agent_id: str,
        session_id: str,
        request_id: str,
        correlation_id: str,
        provider: str,
        model: str,
    ) -> None:
        """Log a request event. Called before forwarding to the provider.

        Args:
            agent_id: The agent identifier.
            session_id: The session identifier.
            request_id: The unique request identifier.
            correlation_id: Correlation ID for tracing.
            provider: LLM provider name.
            model: Model name being called.
        """
        self._emit(
            AuditEvent(
                type="observe.request",
                timestamp=self._now(),
                correlation_id=correlation_id,
                agent_id=agent_id,
                session_id=session_id,
                request_id=request_id,
                provider=provider,
                model=model,
                data={"redaction": "HASH"},
            )
        )

    def log_response(
        self,
        *,
        request_id: str,
        correlation_id: str,
        output_token_count: int,
        cost: float,
        latency_ms: float,
        pii_detections: Optional[Dict[str, Any]],
    ) -> None:
        """Log a response event. Called after receiving the provider response.

        Args:
            request_id: The unique request identifier.
            correlation_id: Correlation ID for tracing.
            output_token_count: Number of output tokens in the response.
            cost: Computed cost in USD for this request.
            latency_ms: End-to-end latency in milliseconds.
            pii_detections: PII detection summary or None if no PII found.
        """
        self._emit(
            AuditEvent(
                type="observe.response",
                timestamp=self._now(),
                correlation_id=correlation_id,
                request_id=request_id,
                data={
                    "output_token_count": output_token_count,
                    "cost": cost,
                    "latency_ms": latency_ms,
                    "pii_detections": pii_detections,
                    "redaction": "HASH",
                },
            )
        )

    def log_error(
        self,
        *,
        request_id: str,
        correlation_id: str,
        error_type: str,
        error_message: str,
    ) -> None:
        """Log an error event when the provider throws.

        Args:
            request_id: The unique request identifier.
            correlation_id: Correlation ID for tracing.
            error_type: Classification of the error (e.g. 'timeout', 'rate_limit').
            error_message: Human-readable error description.
        """
        self._emit(
            AuditEvent(
                type="observe.error",
                timestamp=self._now(),
                correlation_id=correlation_id,
                request_id=request_id,
                data={
                    "error_type": error_type,
                    "error_message": error_message,
                },
            )
        )

    def log_tool_call(
        self,
        *,
        request_id: str,
        correlation_id: str,
        tool_name: str,
        argument_count: int,
        arguments_hash: str,
    ) -> None:
        """Log a tool call detected in the model response.

        Args:
            request_id: The unique request identifier.
            correlation_id: Correlation ID for tracing.
            tool_name: Name of the tool being invoked.
            argument_count: Number of arguments passed to the tool.
            arguments_hash: SHA-256 hash of the serialized arguments.
        """
        self._emit(
            AuditEvent(
                type="observe.tool_call",
                timestamp=self._now(),
                correlation_id=correlation_id,
                request_id=request_id,
                data={
                    "tool_name": tool_name,
                    "argument_count": argument_count,
                    "arguments_hash": arguments_hash,
                },
            )
        )

    def log_freeze_block(
        self,
        *,
        agent_id: str,
        request_id: str,
        correlation_id: str,
        is_wildcard: bool,
    ) -> None:
        """Log a freeze-block event.

        Args:
            agent_id: The agent identifier that triggered the freeze.
            request_id: The unique request identifier.
            correlation_id: Correlation ID for tracing.
            is_wildcard: Whether this is a wildcard freeze (blocks all tools).
        """
        self._emit(
            AuditEvent(
                type="observe.freeze_block",
                timestamp=self._now(),
                correlation_id=correlation_id,
                agent_id=agent_id,
                request_id=request_id,
                data={
                    "is_wildcard": is_wildcard,
                },
            )
        )

    def log_baseline_complete(self, agent_id: str, session_id: str) -> None:
        """Log baseline completion event.

        Called when the behavioral baseline window has been fully populated
        and statistics have been computed.

        Args:
            agent_id: The agent identifier whose baseline is complete.
            session_id: The session identifier.
        """
        self._emit(
            AuditEvent(
                type="observe.baseline_complete",
                timestamp=self._now(),
                correlation_id=f"baseline-{agent_id}",
                agent_id=agent_id,
                session_id=session_id,
            )
        )

    def get_events(self) -> List[AuditEvent]:
        """Get all logged events (for testing and reporting).

        Returns:
            List of all AuditEvent instances recorded by this logger.
        """
        return self._events

    def get_event_count(self) -> int:
        """Get event count (for audit completeness checks).

        Returns:
            The number of events currently stored.
        """
        return len(self._events)
