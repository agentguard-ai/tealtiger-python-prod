"""Example: Export TealTiger governance decisions to Langfuse.

This example shows how governance decisions appear as spans in the Langfuse
trace viewer — inline with your LLM traces.

Requirements:
    pip install tealtiger langfuse

Set environment variables:
    LANGFUSE_PUBLIC_KEY=pk-...
    LANGFUSE_SECRET_KEY=sk-...
    LANGFUSE_HOST=https://cloud.langfuse.com  (or your self-hosted URL)
    OPENAI_API_KEY=sk-...
"""

import os
from langfuse import Langfuse
from tealtiger.integrations.langfuse import LangfuseGovernanceExporter

# --- Setup ---

langfuse = Langfuse()
exporter = LangfuseGovernanceExporter(langfuse)


# --- Example 1: Manual export of governance decisions ---

# Simulate an ALLOW decision
exporter.trace({
    "action": "ALLOW",
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
    "agent_id": "research-bot",
    "session_id": "session-001",
    "tool_slug": "GITHUB_GET_REPOS",
    "toolkit_slug": "github",
    "reason": "Policy allows: tool in allowlist",
    "reason_codes": ["POLICY_ALLOW"],
    "risk_score": 0,
    "evaluation_time_ms": 0.38,
    "mode": "ENFORCE",
    "pii_detected": [],
    "cost_tracked": 0.001,
    "cumulative_cost": 0.015,
    "timestamp_ms": 1720000000000,
})

# Simulate a DENY decision
exporter.trace({
    "action": "DENY",
    "correlation_id": "660e8400-e29b-41d4-a716-446655440001",
    "agent_id": "research-bot",
    "session_id": "session-001",
    "tool_slug": "GMAIL_SEND_EMAIL",
    "toolkit_slug": "gmail",
    "reason": "Tool 'GMAIL_SEND_EMAIL' not in allowlist for agent 'research-bot'",
    "reason_codes": ["TOOL_NOT_ALLOWED"],
    "risk_score": 0.9,
    "evaluation_time_ms": 0.52,
    "mode": "ENFORCE",
    "pii_detected": [],
    "cost_tracked": 0.0,
    "cumulative_cost": 0.015,
    "timestamp_ms": 1720000001000,
})

# Simulate a PII detection (monitor mode)
exporter.trace({
    "action": "MONITOR",
    "correlation_id": "770e8400-e29b-41d4-a716-446655440002",
    "agent_id": "research-bot",
    "session_id": "session-001",
    "tool_slug": "SLACK_SEND_MESSAGE",
    "toolkit_slug": "slack",
    "reason": "PII detected in arguments (monitor mode - not blocked)",
    "reason_codes": ["PII_DETECTED"],
    "risk_score": 0.6,
    "evaluation_time_ms": 1.1,
    "mode": "MONITOR",
    "pii_detected": [{"type": "email", "start": 12, "end": 30}],
    "cost_tracked": 0.002,
    "cumulative_cost": 0.017,
    "timestamp_ms": 1720000002000,
})

# Flush to ensure all events are sent
exporter.flush()

print("Governance decisions exported to Langfuse!")
print("Check your Langfuse dashboard to see the traces.")
print()
print("In the Langfuse UI you'll see:")
print("  - ALLOW decisions: DEFAULT level (grey)")
print("  - DENY decisions: ERROR level (red)")
print("  - MONITOR decisions: WARNING level (amber)")
print()
print("Each span shows: tool name, action, reason codes, risk score,")
print("evaluation time, PII findings, and cost tracking.")


# --- Example 2: Using with TealTiger observe() ---
# (Uncomment when running with a real OpenAI key)

# from tealtiger import observe
# from openai import OpenAI
#
# client = observe(
#     OpenAI(),
#     agent_id="my-agent",
#     on_decision=exporter.trace,  # Each decision → Langfuse span
# )
#
# # All governance decisions now appear in Langfuse traces
# response = client.chat.completions.create(
#     model="gpt-4o-mini",
#     messages=[{"role": "user", "content": "Hello!"}]
# )
