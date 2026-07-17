"""TealTiger governance callbacks for Google Agent Development Kit (ADK).

Provides before_tool_callback and after_tool_callback hooks that enforce
governance policies (PII detection, tool allowlisting, cost budgets, kill switch)
before tools execute in Google ADK agents.

Usage:
    from google.adk import Agent
    from tealtiger.integrations.google_adk import TealTigerCallback

    governance = TealTigerCallback(
        policies=[
            {"type": "pii_block", "categories": ["ssn", "credit_card"]},
            {"type": "cost_limit", "max_per_session": 5.00},
        ],
        mode="ENFORCE",
    )

    agent = Agent(
        model="gemini-2.0-flash",
        tools=[search_tool, code_tool],
        before_tool_callback=governance.before_tool,
        after_tool_callback=governance.after_tool,
    )
"""

from __future__ import annotations

import re
import uuid
import time
from typing import Any, Dict, List

# PII patterns
_PII_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone": re.compile(r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
}

# Secret patterns
_SECRET_PATTERNS = [
    re.compile(r"\b(sk-[a-zA-Z0-9]{20,})\b"),
    re.compile(r"\b(ghp_[a-zA-Z0-9]{36,})\b"),
    re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
]


class TealTigerCallback:
    """Governance callback for Google ADK agents.

    Evaluates governance policies before tool execution and records
    audit entries after execution completes.

    Args:
        policies: List of governance policy dicts.
        mode: "OBSERVE", "MONITOR", or "ENFORCE".
        agent_id: Agent identifier for audit correlation.
        on_decision: Optional callback invoked with each governance decision.
    """

    def __init__(
        self,
        policies: List[Dict[str, Any]] = None,
        mode: str = "OBSERVE",
        agent_id: str = None,
        on_decision=None,
    ):
        self.policies = policies or []
        self.mode = mode.upper()
        self.agent_id = agent_id or f"adk-agent-{str(uuid.uuid4())[:8]}"
        self.on_decision = on_decision
        self._decisions: List[Dict[str, Any]] = []
        self._cumulative_cost: float = 0.0
        self._frozen: bool = False

    def before_tool(self, callback_context, tool, args, tool_context=None):
        """Before-tool callback for Google ADK.

        Evaluates governance policies before tool execution.
        Returns a dict to block execution (ADK pattern), or None to allow.

        Args:
            callback_context: ADK callback context.
            tool: The tool being called.
            args: Tool arguments dict.
            tool_context: Optional tool context.

        Returns:
            None to allow execution, or a dict with 'content' key to block.
        """
        start_time = time.perf_counter()
        tool_name = getattr(tool, "name", str(tool)) if not isinstance(tool, str) else tool
        correlation_id = str(uuid.uuid4())

        # Evaluate policies
        action = "ALLOW"
        reason_codes = []
        risk_score = 0

        # Check freeze
        if self._frozen:
            action = "DENY"
            reason_codes.append("AGENT_FROZEN")
            risk_score = 100

        # Tool allowlist
        if action == "ALLOW":
            for policy in self.policies:
                if policy.get("type") == "tool_allowlist":
                    allowed = policy.get("allowed", [])
                    if not any(
                        tool_name == p or (p.endswith("*") and tool_name.startswith(p[:-1]))
                        for p in allowed
                    ):
                        action = "DENY"
                        reason_codes.append("TOOL_NOT_ALLOWED")
                        risk_score = max(risk_score, 80)
                        break

        # PII detection
        if action == "ALLOW":
            args_text = str(args)
            for policy in self.policies:
                if policy.get("type") == "pii_block":
                    categories = policy.get("categories", list(_PII_PATTERNS.keys()))
                    for cat in categories:
                        pattern = _PII_PATTERNS.get(cat)
                        if pattern and pattern.search(args_text):
                            action = "DENY"
                            reason_codes.append(f"PII_DETECTED:{cat}")
                            risk_score = max(risk_score, 90)
                    if action == "DENY":
                        break

        # Secret detection
        if action == "ALLOW":
            args_text = str(args)
            for policy in self.policies:
                if policy.get("type") == "secret_detection":
                    if any(p.search(args_text) for p in _SECRET_PATTERNS):
                        action = "DENY"
                        reason_codes.append("SECRET_DETECTED")
                        risk_score = max(risk_score, 95)
                        break

        # Cost limit
        if action == "ALLOW":
            for policy in self.policies:
                if policy.get("type") == "cost_limit":
                    limit = policy.get("max_per_session", float("inf"))
                    if self._cumulative_cost >= limit:
                        action = "DENY"
                        reason_codes.append("BUDGET_EXCEEDED")
                        risk_score = max(risk_score, 70)
                        break

        eval_time = (time.perf_counter() - start_time) * 1000

        # Record decision
        decision = {
            "correlation_id": correlation_id,
            "timestamp_ms": time.time() * 1000,
            "action": action,
            "mode": self.mode,
            "tool_name": tool_name,
            "agent_id": self.agent_id,
            "reason_codes": reason_codes or (["POLICY_ALLOW"] if action == "ALLOW" else []),
            "risk_score": risk_score,
            "evaluation_time_ms": eval_time,
            "cost_tracked": 0.002 if action == "ALLOW" else 0.0,
            "cumulative_cost": self._cumulative_cost,
        }
        self._decisions.append(decision)

        if self.on_decision:
            self.on_decision(decision)

        # Track cost for allowed actions
        if action == "ALLOW":
            self._cumulative_cost += 0.002

        # Mode-based behavior
        if self.mode == "ENFORCE" and action == "DENY":
            # Return a dict to block execution (ADK pattern)
            reason = ", ".join(reason_codes)
            return {
                "content": f"[GOVERNANCE DENIED] Tool '{tool_name}' blocked. Reason: {reason}. Decision ID: {correlation_id}"
            }

        # OBSERVE and MONITOR modes: allow through
        return None

    def after_tool(self, callback_context, tool, args, tool_context=None, result=None):
        """After-tool callback for audit trail.

        Records the tool execution result in the governance audit.

        Args:
            callback_context: ADK callback context.
            tool: The tool that was called.
            args: Tool arguments dict.
            tool_context: Optional tool context.
            result: Tool execution result.

        Returns:
            None (never blocks after execution).
        """
        # Update the last decision with execution outcome
        if self._decisions:
            self._decisions[-1]["execution_outcome"] = "executed"

        return None

    def freeze(self):
        """Freeze this agent — blocks all tool calls."""
        self._frozen = True

    def unfreeze(self):
        """Unfreeze this agent — restores normal governance."""
        self._frozen = False

    @property
    def decisions(self) -> List[Dict[str, Any]]:
        """All governance decisions made."""
        return self._decisions

    @property
    def deny_count(self) -> int:
        """Count of denied tool calls."""
        return sum(1 for d in self._decisions if d["action"] == "DENY")

    @property
    def total_cost(self) -> float:
        """Cumulative cost tracked."""
        return self._cumulative_cost
