"""Example: Export TealTiger governance decisions to AgentOps.

Governance decisions appear in the AgentOps session timeline alongside
your agent's LLM calls, tool invocations, and errors.

Requirements:
    pip install tealtiger agentops

Set environment variables:
    AGENTOPS_API_KEY=your-key
    OPENAI_API_KEY=sk-...
"""

import agentops
from tealtiger.integrations.agentops import AgentOpsGovernanceReporter

# Initialize AgentOps
agentops.init()

# Create the governance reporter
reporter = AgentOpsGovernanceReporter()

# --- Simulate governance decisions ---

# Tool call allowed
reporter.report({
    "action": "ALLOW",
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
    "agent_id": "research-bot",
    "tool_slug": "GITHUB_GET_REPOS",
    "toolkit_slug": "github",
    "reason": "Tool in allowlist",
    "reason_codes": ["POLICY_ALLOW"],
    "risk_score": 0,
    "evaluation_time_ms": 0.38,
    "mode": "ENFORCE",
    "cost_tracked": 0.001,
    "cumulative_cost": 0.015,
    "pii_detected": [],
})

# Tool call denied (appears as error in AgentOps timeline)
reporter.report({
    "action": "DENY",
    "correlation_id": "660e8400-e29b-41d4-a716-446655440001",
    "agent_id": "research-bot",
    "tool_slug": "GMAIL_SEND_EMAIL",
    "toolkit_slug": "gmail",
    "reason": "Tool 'GMAIL_SEND_EMAIL' not in allowlist for agent 'research-bot'",
    "reason_codes": ["TOOL_NOT_ALLOWED"],
    "risk_score": 0.9,
    "evaluation_time_ms": 0.52,
    "mode": "ENFORCE",
    "cost_tracked": 0.0,
    "cumulative_cost": 0.015,
    "pii_detected": [],
})

# PII detected (monitor mode — logged but not blocked)
reporter.report({
    "action": "MONITOR",
    "correlation_id": "770e8400-e29b-41d4-a716-446655440002",
    "agent_id": "research-bot",
    "tool_slug": "SLACK_SEND_MESSAGE",
    "toolkit_slug": "slack",
    "reason": "PII detected (monitor mode)",
    "reason_codes": ["PII_DETECTED"],
    "risk_score": 0.6,
    "evaluation_time_ms": 1.1,
    "mode": "MONITOR",
    "cost_tracked": 0.002,
    "cumulative_cost": 0.017,
    "pii_detected": [{"type": "email", "start": 12, "end": 30}],
})

# End session
agentops.end_session("Success")

print(f"Reported {reporter.allow_count} allows, {reporter.deny_count} denials")
print("Check your AgentOps dashboard to see governance events in the session timeline.")
print()
print("In AgentOps you'll see:")
print("  - ALLOW: ActionEvent (governance:allow)")
print("  - DENY: ErrorEvent (governance:deny) — highlighted in red")
print("  - MONITOR: ActionEvent (governance:monitor)")


# --- Using with TealTiger observe() ---
# (Uncomment when running with real keys)

# from tealtiger import observe
# from openai import OpenAI
#
# client = observe(
#     OpenAI(),
#     agent_id="my-agent",
#     on_decision=reporter.report,
# )
#
# response = client.chat.completions.create(
#     model="gpt-4o-mini",
#     messages=[{"role": "user", "content": "Hello!"}]
# )
