"""Tests for TealTiger → Langfuse governance trace export."""

import pytest
from unittest.mock import MagicMock, patch, call


@pytest.fixture
def mock_langfuse():
    """Create a mock Langfuse client."""
    langfuse = MagicMock()
    mock_trace = MagicMock()
    mock_span = MagicMock()
    langfuse.trace.return_value = mock_trace
    mock_trace.span.return_value = mock_span
    return langfuse


@pytest.fixture
def exporter(mock_langfuse):
    """Create a LangfuseGovernanceExporter with mocked client."""
    with patch.dict("sys.modules", {"langfuse": MagicMock(), "langfuse.client": MagicMock()}):
        from tealtiger.integrations.langfuse import LangfuseGovernanceExporter
        return LangfuseGovernanceExporter(mock_langfuse)


def test_allow_decision_creates_default_level_span(exporter, mock_langfuse):
    """ALLOW decisions should create spans with DEFAULT level."""
    decision = {
        "action": "ALLOW",
        "correlation_id": "test-123",
        "agent_id": "coder",
        "session_id": "session-1",
        "reason": "Policy allows",
        "reason_codes": ["POLICY_ALLOW"],
        "risk_score": 0,
        "evaluation_time_ms": 0.42,
        "mode": "ENFORCE",
    }

    exporter.trace(decision)

    mock_langfuse.trace.assert_called_once()
    trace = mock_langfuse.trace.return_value
    trace.span.assert_called_once()

    span_kwargs = trace.span.call_args[1]
    assert span_kwargs["level"] == "DEFAULT"
    assert span_kwargs["name"] == "tealtiger.governance"


def test_deny_decision_creates_error_level_span(exporter, mock_langfuse):
    """DENY decisions should create spans with ERROR level."""
    decision = {
        "action": "DENY",
        "correlation_id": "test-456",
        "agent_id": "coder",
        "reason": "Tool not in allowlist",
        "reason_codes": ["TOOL_NOT_ALLOWED"],
        "risk_score": 0.8,
        "evaluation_time_ms": 1.2,
        "tool_slug": "GMAIL_SEND_EMAIL",
        "toolkit_slug": "gmail",
    }

    exporter.trace(decision)

    trace = mock_langfuse.trace.return_value
    span_kwargs = trace.span.call_args[1]
    assert span_kwargs["level"] == "ERROR"
    assert span_kwargs["input"]["tool"] == "GMAIL_SEND_EMAIL"
    assert span_kwargs["output"]["action"] == "DENY"


def test_monitor_decision_creates_warning_level_span(exporter, mock_langfuse):
    """MONITOR decisions should create spans with WARNING level."""
    decision = {
        "action": "MONITOR",
        "correlation_id": "test-789",
        "reason": "PII detected but not blocked",
        "reason_codes": ["PII_DETECTED"],
        "pii_detected": [{"type": "email", "start": 5, "end": 20}],
    }

    exporter.trace(decision)

    trace = mock_langfuse.trace.return_value
    span_kwargs = trace.span.call_args[1]
    assert span_kwargs["level"] == "WARNING"
    assert span_kwargs["metadata"]["pii_detected"] == [{"type": "email", "start": 5, "end": 20}]


def test_metadata_includes_governance_fields(exporter, mock_langfuse):
    """Span metadata should include all governance-relevant fields."""
    decision = {
        "action": "ALLOW",
        "correlation_id": "test-meta",
        "risk_score": 0.3,
        "evaluation_time_ms": 2.1,
        "mode": "ENFORCE",
        "cost_tracked": 0.005,
        "cumulative_cost": 1.23,
        "policy_digest": "sha256:abc123",
    }

    exporter.trace(decision)

    trace = mock_langfuse.trace.return_value
    metadata = trace.span.call_args[1]["metadata"]
    assert metadata["risk_score"] == 0.3
    assert metadata["evaluation_time_ms"] == 2.1
    assert metadata["mode"] == "ENFORCE"
    assert metadata["cost_tracked"] == 0.005
    assert metadata["cumulative_cost"] == 1.23
    assert metadata["policy_digest"] == "sha256:abc123"


def test_same_session_reuses_trace(exporter, mock_langfuse):
    """Multiple decisions in the same session should reuse the same trace."""
    decision1 = {"action": "ALLOW", "session_id": "session-x", "correlation_id": "1"}
    decision2 = {"action": "DENY", "session_id": "session-x", "correlation_id": "2"}

    exporter.trace(decision1)
    exporter.trace(decision2)

    # Should only create one trace for the session
    assert mock_langfuse.trace.call_count == 1


def test_flush_on_trace_option(mock_langfuse):
    """When flush_on_trace=True, flush after each trace call."""
    with patch.dict("sys.modules", {"langfuse": MagicMock(), "langfuse.client": MagicMock()}):
        from tealtiger.integrations.langfuse import LangfuseGovernanceExporter
        exporter = LangfuseGovernanceExporter(mock_langfuse, flush_on_trace=True)

    decision = {"action": "ALLOW", "correlation_id": "flush-test"}
    exporter.trace(decision)

    mock_langfuse.flush.assert_called_once()
