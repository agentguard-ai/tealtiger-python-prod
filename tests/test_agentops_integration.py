"""Tests for TealTiger → AgentOps governance event export."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_agentops():
    """Mock agentops module."""
    mock = MagicMock()
    mock_session = MagicMock()
    mock.get_session.return_value = mock_session
    return mock, mock_session


@pytest.fixture
def reporter(mock_agentops):
    """Create an AgentOpsGovernanceReporter with mocked agentops."""
    mock, mock_session = mock_agentops
    with patch.dict("sys.modules", {
        "agentops": mock,
    }):
        # Re-import to pick up the mock
        from tealtiger.integrations.agentops import AgentOpsGovernanceReporter
        return AgentOpsGovernanceReporter(session=mock_session)


def test_allow_decision_creates_action_event(reporter, mock_agentops):
    """ALLOW decisions should create ActionEvents."""
    _, mock_session = mock_agentops

    decision = {
        "action": "ALLOW",
        "correlation_id": "test-123",
        "agent_id": "coder",
        "tool_slug": "GITHUB_GET_REPOS",
        "reason": "Policy allows",
        "reason_codes": ["POLICY_ALLOW"],
        "risk_score": 0,
        "evaluation_time_ms": 0.42,
    }

    reporter.report(decision)

    mock_session.record.assert_called_once()
    assert reporter.allow_count == 1
    assert reporter.deny_count == 0


def test_deny_decision_creates_error_event(reporter, mock_agentops):
    """DENY decisions should create ErrorEvents."""
    _, mock_session = mock_agentops

    decision = {
        "action": "DENY",
        "correlation_id": "test-456",
        "agent_id": "coder",
        "tool_slug": "GMAIL_SEND_EMAIL",
        "reason": "Tool not in allowlist",
        "reason_codes": ["TOOL_NOT_ALLOWED"],
        "risk_score": 0.9,
    }

    reporter.report(decision)

    mock_session.record.assert_called_once()
    assert reporter.deny_count == 1
    assert reporter.allow_count == 0


def test_decisions_are_tracked(reporter, mock_agentops):
    """All reported decisions should be stored."""
    reporter.report({"action": "ALLOW", "correlation_id": "1"})
    reporter.report({"action": "DENY", "correlation_id": "2"})
    reporter.report({"action": "MONITOR", "correlation_id": "3"})

    decisions = reporter.get_decisions()
    assert len(decisions) == 3
    assert decisions[0]["action"] == "ALLOW"
    assert decisions[1]["action"] == "DENY"
    assert decisions[2]["action"] == "MONITOR"


def test_metadata_included_in_params(reporter, mock_agentops):
    """Event params should include governance metadata."""
    _, mock_session = mock_agentops

    decision = {
        "action": "ALLOW",
        "correlation_id": "meta-test",
        "agent_id": "researcher",
        "tool_slug": "SEARCH_DB",
        "toolkit_slug": "database",
        "risk_score": 0.3,
        "evaluation_time_ms": 1.5,
        "cost_tracked": 0.002,
        "cumulative_cost": 0.15,
        "pii_detected": [{"type": "email"}],
        "policy_digest": "sha256:xyz",
    }

    reporter.report(decision)
    mock_session.record.assert_called_once()
