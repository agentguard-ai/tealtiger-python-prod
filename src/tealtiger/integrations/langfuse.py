"""TealTiger → Langfuse governance trace exporter.

Exports TealTiger governance decisions as Langfuse spans, enabling teams to see
governance enforcement inline with their LLM traces in the Langfuse UI.

Usage:
    from langfuse import Langfuse
    from tealtiger.integrations.langfuse import LangfuseGovernanceExporter

    langfuse = Langfuse()
    exporter = LangfuseGovernanceExporter(langfuse)

    # Use as on_decision callback
    client = observe(OpenAI(), on_decision=exporter.trace)

    # Or manually export a decision
    exporter.trace(decision)
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

try:
    from langfuse import Langfuse
    from langfuse.client import StatefulSpanClient, StatefulTraceClient
except ImportError:
    raise ImportError(
        "langfuse is required for this integration. "
        "Install it with: pip install langfuse"
    )


class LangfuseGovernanceExporter:
    """Export TealTiger governance decisions as Langfuse spans.

    Each governance decision becomes a Langfuse span with:
    - name: "tealtiger.governance"
    - metadata: {action, reason_codes, risk_score, evaluation_time_ms, policy_digest, ...}
    - level: ERROR (deny), WARNING (monitor), DEFAULT (allow)
    - input: tool/action being governed
    - output: governance decision result

    Args:
        langfuse: An initialized Langfuse client instance.
        trace_name: Name for the parent trace (default: "tealtiger-governance").
        span_name: Name for individual governance spans (default: "tealtiger.governance").
        flush_on_trace: Whether to flush after each trace call (default: False).
    """

    def __init__(
        self,
        langfuse: "Langfuse",
        trace_name: str = "tealtiger-governance",
        span_name: str = "tealtiger.governance",
        flush_on_trace: bool = False,
    ):
        self._langfuse = langfuse
        self._trace_name = trace_name
        self._span_name = span_name
        self._flush_on_trace = flush_on_trace
        self._active_traces: Dict[str, Any] = {}

    def _action_to_level(self, action: str) -> str:
        """Map governance action to Langfuse span level."""
        action_upper = action.upper() if action else "ALLOW"
        if action_upper == "DENY":
            return "ERROR"
        elif action_upper in ("MONITOR", "REFER"):
            return "WARNING"
        else:
            return "DEFAULT"

    def _get_or_create_trace(
        self, session_id: Optional[str] = None, agent_id: Optional[str] = None
    ) -> Any:
        """Get existing trace for a session or create a new one."""
        trace_key = session_id or agent_id or "default"

        if trace_key not in self._active_traces:
            trace = self._langfuse.trace(
                name=self._trace_name,
                session_id=session_id,
                user_id=agent_id,
                metadata={
                    "source": "tealtiger",
                    "agent_id": agent_id,
                },
            )
            self._active_traces[trace_key] = trace

        return self._active_traces[trace_key]

    def trace(self, decision: Dict[str, Any], **kwargs) -> None:
        """Export a governance decision as a Langfuse span.

        This method is designed to be used as the `on_decision` callback
        for TealTiger's observe() or TealEngine.

        Args:
            decision: A TealTiger GovernanceDecision dict containing at minimum:
                - action: "ALLOW", "DENY", "MONITOR", or "REFER"
                - correlation_id: UUID v4 for the decision
                - Optional: reason, reason_codes, risk_score, evaluation_time_ms,
                  agent_id, session_id, tool_slug, pii_detected, cost_tracked, etc.
        """
        action = decision.get("action", "ALLOW")
        correlation_id = decision.get("correlation_id", "")
        agent_id = decision.get("agent_id")
        session_id = decision.get("session_id")

        # Get or create parent trace
        trace = self._get_or_create_trace(
            session_id=session_id, agent_id=agent_id
        )

        # Build span metadata
        metadata = {
            "action": action,
            "reason_codes": decision.get("reason_codes", []),
            "risk_score": decision.get("risk_score", 0),
            "evaluation_time_ms": decision.get("evaluation_time_ms", 0),
            "mode": decision.get("mode", "OBSERVE"),
            "pii_detected": decision.get("pii_detected", []),
            "cost_tracked": decision.get("cost_tracked", 0),
            "cumulative_cost": decision.get("cumulative_cost", 0),
        }

        # Add policy digest if present
        if "policy_digest" in decision:
            metadata["policy_digest"] = decision["policy_digest"]
        if "policy_ref" in decision:
            metadata["policy_ref"] = decision["policy_ref"]

        # Build input context
        input_data = {}
        if "tool_slug" in decision:
            input_data["tool"] = decision["tool_slug"]
        if "toolkit_slug" in decision:
            input_data["toolkit"] = decision["toolkit_slug"]
        if "intent_ref" in decision:
            input_data["intent"] = decision["intent_ref"]

        # Build output
        output_data = {
            "action": action,
            "reason": decision.get("reason", ""),
            "reason_codes": decision.get("reason_codes", []),
        }

        # Determine span level
        level = self._action_to_level(action)

        # Calculate timestamps
        timestamp_ms = decision.get("timestamp_ms")
        start_time = None
        end_time = None
        if timestamp_ms:
            eval_time_ms = decision.get("evaluation_time_ms", 0)
            # Start time is timestamp minus evaluation time
            start_time = (timestamp_ms - eval_time_ms) / 1000.0
            end_time = timestamp_ms / 1000.0

        # Create the span
        span = trace.span(
            name=self._span_name,
            span_id=correlation_id or None,
            input=input_data if input_data else None,
            output=output_data,
            level=level,
            metadata=metadata,
            status_message=decision.get("reason", ""),
        )

        # End the span
        span.end()

        if self._flush_on_trace:
            self._langfuse.flush()

    def flush(self) -> None:
        """Flush all pending Langfuse events."""
        self._langfuse.flush()

    def shutdown(self) -> None:
        """Flush and shutdown the Langfuse client."""
        self._langfuse.flush()
        self._langfuse.shutdown()
