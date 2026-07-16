"""TealTiger → AgentOps governance event exporter.

Exports TealTiger governance decisions as AgentOps ActionEvents, enabling teams
to see governance enforcement in the AgentOps session timeline alongside their
agent telemetry.

Usage:
    import agentops
    from tealtiger.integrations.agentops import AgentOpsGovernanceReporter

    agentops.init(api_key="your-key")
    reporter = AgentOpsGovernanceReporter()

    # Use as on_decision callback
    client = observe(OpenAI(), on_decision=reporter.report)

    # Or manually report a decision
    reporter.report(decision)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from agentops import ActionEvent, ErrorEvent
    import agentops
except ImportError:
    raise ImportError(
        "agentops is required for this integration. "
        "Install it with: pip install agentops"
    )


class AgentOpsGovernanceReporter:
    """Export TealTiger governance decisions as AgentOps events.

    Each governance decision becomes an AgentOps ActionEvent (or ErrorEvent for
    denials) visible in the session timeline.

    Decision mapping:
    - ALLOW → ActionEvent with action_type="governance:allow"
    - DENY → ErrorEvent with error_type="governance:deny"
    - MONITOR → ActionEvent with action_type="governance:monitor"
    - REFER → ActionEvent with action_type="governance:refer"

    Args:
        session: An AgentOps session. If None, uses the default active session.
        include_metadata: Whether to include full governance metadata in events.
    """

    def __init__(
        self,
        session=None,
        include_metadata: bool = True,
    ):
        self._session = session
        self._include_metadata = include_metadata
        self._decisions: List[Dict[str, Any]] = []

    def report(self, decision: Dict[str, Any], **kwargs) -> None:
        """Report a governance decision as an AgentOps event.

        This method is designed to be used as the `on_decision` callback
        for TealTiger's observe() or TealEngine.

        Args:
            decision: A TealTiger GovernanceDecision dict containing at minimum:
                - action: "ALLOW", "DENY", "MONITOR", or "REFER"
                - correlation_id: UUID v4 for the decision
                - Optional: reason, reason_codes, risk_score, evaluation_time_ms,
                  agent_id, tool_slug, pii_detected, cost_tracked, etc.
        """
        action = decision.get("action", "ALLOW").upper()
        self._decisions.append(decision)

        # Build event params
        params = self._build_params(decision)

        if action == "DENY":
            self._report_deny(decision, params)
        else:
            self._report_action(decision, params, action)

    def _build_params(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Build event parameters from a governance decision."""
        params: Dict[str, Any] = {
            "governance_action": decision.get("action", "ALLOW"),
            "correlation_id": decision.get("correlation_id", ""),
            "agent_id": decision.get("agent_id", ""),
        }

        if self._include_metadata:
            params.update({
                "reason": decision.get("reason", ""),
                "reason_codes": decision.get("reason_codes", []),
                "risk_score": decision.get("risk_score", 0),
                "evaluation_time_ms": decision.get("evaluation_time_ms", 0),
                "mode": decision.get("mode", "OBSERVE"),
                "cost_tracked": decision.get("cost_tracked", 0),
                "cumulative_cost": decision.get("cumulative_cost", 0),
                "pii_count": len(decision.get("pii_detected", [])),
            })

            if "tool_slug" in decision:
                params["tool_slug"] = decision["tool_slug"]
            if "toolkit_slug" in decision:
                params["toolkit_slug"] = decision["toolkit_slug"]
            if "policy_digest" in decision:
                params["policy_digest"] = decision["policy_digest"]

        return params

    def _report_action(
        self, decision: Dict[str, Any], params: Dict[str, Any], action: str
    ) -> None:
        """Report an ALLOW/MONITOR/REFER decision as an ActionEvent."""
        action_type = f"governance:{action.lower()}"
        tool_slug = decision.get("tool_slug", "unknown")

        event = ActionEvent(
            action_type=action_type,
            params=params,
            returns=decision.get("reason", f"Governance {action}"),
        )

        session = self._session or agentops.get_session()
        if session:
            session.record(event)

    def _report_deny(
        self, decision: Dict[str, Any], params: Dict[str, Any]
    ) -> None:
        """Report a DENY decision as an ErrorEvent."""
        reason = decision.get("reason", "Governance DENY")
        reason_codes = decision.get("reason_codes", [])

        event = ErrorEvent(
            error_type="governance:deny",
            details=reason,
            params=params,
        )

        session = self._session or agentops.get_session()
        if session:
            session.record(event)

    def get_decisions(self) -> List[Dict[str, Any]]:
        """Return all recorded governance decisions."""
        return self._decisions.copy()

    @property
    def deny_count(self) -> int:
        """Count of DENY decisions reported."""
        return sum(1 for d in self._decisions if d.get("action", "").upper() == "DENY")

    @property
    def allow_count(self) -> int:
        """Count of ALLOW decisions reported."""
        return sum(1 for d in self._decisions if d.get("action", "").upper() == "ALLOW")
