"""Tests for cross-agent policy federation."""

from tealtiger.core.engine import DecisionAction, PolicyFederation, TealEngine

PARENT_PAYLOAD = {
    "version": "1.0",
    "issuer": "parent-orchestrator",
    "subjectAgentId": "child-agent",
    "issuedAt": 1710000000000,
    "revision": 1,
    "parentCorrelationId": "parent-correlation-1",
    "traceChain": ["root-correlation-1"],
    "constraints": {
        "budget": {
            "remaining": 5,
            "daily": 8,
        },
        "toolAllowlist": ["search"],
        "dataClassification": "internal",
    },
}

CHILD_POLICY = {
    "tools": {
        "search": {"allowed": True},
        "file_delete": {"allowed": True},
    },
    "behavioral": {
        "costLimit": {"daily": 10},
        "rateLimit": {"requests": 100, "window": "1m"},
    },
    "content": {
        "dataClassification": {"maxLevel": "confidential"},
    },
}

CROSS_SDK_TOKEN_FIXTURE = (
    "ttfp.v1."
    "eyJjb25zdHJhaW50cyI6eyJidWRnZXQiOnsiZGFpbHkiOjgsInJlbWFpbmluZyI6NX0s"
    "ImRhdGFDbGFzc2lmaWNhdGlvbiI6ImludGVybmFsIiwidG9vbEFsbG93bGlzdCI6WyJzZWFyY2giXX0s"
    "Imlzc3VlZEF0IjoxNzEwMDAwMDAwMDAwLCJpc3N1ZXIiOiJwYXJlbnQtb3JjaGVzdHJhdG9yIiwicGFy"
    "ZW50Q29ycmVsYXRpb25JZCI6InBhcmVudC1jb3JyZWxhdGlvbi0xIiwicmV2aXNpb24iOjEsInN1Ympl"
    "Y3RBZ2VudElkIjoiY2hpbGQtYWdlbnQiLCJ0cmFjZUNoYWluIjpbInJvb3QtY29ycmVsYXRpb24tMSJd"
    "LCJ2ZXJzaW9uIjoiMS4wIn0."
    "D01L0Qu4RSTsa_YsRE1AYbJonefif-JBm3qtpRVeahU"
)


def test_merges_constraints_with_most_restrictive_wins() -> None:
    merged = PolicyFederation.merge_policies(CHILD_POLICY, PARENT_PAYLOAD)

    assert merged["tools"]["search"]["allowed"] is True
    assert merged["tools"]["file_delete"]["allowed"] is False
    assert merged["tools"]["*"]["allowed"] is False
    assert merged["behavioral"]["costLimit"]["daily"] == 5
    assert merged["content"]["dataClassification"]["maxLevel"] == "internal"


def test_child_engine_enforces_parent_constraints() -> None:
    engine = TealEngine(CHILD_POLICY, federation=PARENT_PAYLOAD)

    allowed = engine.evaluate_with_mode(
        {
            "agentId": "child-agent",
            "action": "tool.execute",
            "tool": "search",
            "cost": 4,
            "metadata": {"dataClassification": "internal"},
        }
    )
    assert allowed.action == DecisionAction.ALLOW

    blocked_tool = engine.evaluate_with_mode(
        {"agentId": "child-agent", "action": "tool.execute", "tool": "file_delete"}
    )
    assert blocked_tool.action == DecisionAction.DENY

    blocked_budget = engine.evaluate_with_mode(
        {"agentId": "child-agent", "action": "tool.execute", "tool": "search", "cost": 6}
    )
    assert blocked_budget.action == DecisionAction.DENY

    blocked_classification = engine.evaluate_with_mode(
        {
            "agentId": "child-agent",
            "action": "tool.execute",
            "tool": "search",
            "metadata": {"dataClassification": "confidential"},
        }
    )
    assert blocked_classification.action == DecisionAction.DENY


def test_async_tool_revocation_applies_on_next_evaluation() -> None:
    engine = TealEngine(CHILD_POLICY, federation=PARENT_PAYLOAD)

    assert (
        engine.evaluate_with_mode(
            {"agentId": "child-agent", "action": "tool.execute", "tool": "search"}
        ).action
        == DecisionAction.ALLOW
    )

    engine.apply_federated_constraints(
        PolicyFederation.apply_revocation(PARENT_PAYLOAD["constraints"], ["search"])
    )

    assert (
        engine.evaluate_with_mode(
            {"agentId": "child-agent", "action": "tool.execute", "tool": "search"}
        ).action
        == DecisionAction.DENY
    )


def test_signed_policy_token_round_trip() -> None:
    token = PolicyFederation.create_token(PARENT_PAYLOAD, "shared-secret")
    result = PolicyFederation.verify_token(token, "shared-secret", now_ms=1710000000001)

    assert token == CROSS_SDK_TOKEN_FIXTURE
    assert result.valid is True
    assert result.payload == PARENT_PAYLOAD
    assert PolicyFederation.verify_token(f"{token}x", "shared-secret").valid is False


def test_accepts_typescript_parent_token_fixture() -> None:
    result = PolicyFederation.verify_token(
        CROSS_SDK_TOKEN_FIXTURE,
        "shared-secret",
        now_ms=1710000000001,
    )

    assert result.valid is True
    assert result.payload == PARENT_PAYLOAD


def test_child_context_links_to_parent_correlation_chain() -> None:
    context = PolicyFederation.create_child_context(
        PARENT_PAYLOAD,
        child_correlation_id="child-correlation-1",
        trace_id="trace-1",
        span_id="span-1",
    )

    assert context.correlation_id == "child-correlation-1"
    assert context.trace_id == "trace-1"
    assert context.span_id == "span-1"
    assert context.metadata["parent_correlation_id"] == "parent-correlation-1"
    assert context.metadata["trace_chain"] == [
        "root-correlation-1",
        "parent-correlation-1",
    ]
