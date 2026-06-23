"""Tests for TealAudit.to_json() dashboard export method."""

import json
from datetime import datetime

import pytest

from tealtiger.core.audit import (
    AuditEvent,
    AuditEventType,
    ConsoleOutput,
    TealAudit,
)
from tealtiger.core.engine.types import DecisionAction, ReasonCode


class TestTealAuditToJson:
    """Tests for the to_json() dashboard export method."""

    def _create_audit(self):
        """Create a TealAudit instance with a mock output."""
        return TealAudit(
            outputs=[ConsoleOutput()],
            max_events=1000,
            enable_storage=True,
        )

    def _make_event(self, **kwargs):
        """Helper to create an AuditEvent with defaults."""
        defaults = {
            "schema_version": "1.0.0",
            "event_type": AuditEventType.POLICY_EVALUATION,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "correlation_id": "test-correlation",
        }
        defaults.update(kwargs)
        return AuditEvent(**defaults)

    def test_to_json_empty(self):
        """Test to_json returns empty array when no events."""
        audit = self._create_audit()
        result = json.loads(audit.to_json())
        assert result == []

    def test_to_json_single_allow(self):
        """Test to_json with a single ALLOW decision."""
        audit = self._create_audit()
        event = self._make_event(
            correlation_id="d-4a8b2c1f",
            action=DecisionAction.ALLOW,
            agent_id="research-agent",
            risk_score=0,
        )
        audit.log(event)

        result = json.loads(audit.to_json())
        assert len(result) == 1
        assert result[0]["decision_id"] == "d-4a8b2c1f"
        assert result[0]["action"] == "allow"
        assert result[0]["agent_id"] == "research-agent"
        assert result[0]["risk_score"] == 0
        assert result[0]["reason_codes"] == []

    def test_to_json_single_deny(self):
        """Test to_json with a single DENY decision."""
        audit = self._create_audit()
        event = self._make_event(
            event_type=AuditEventType.TOOL_EXECUTION,
            correlation_id="d-4a8b2c1f",
            action=DecisionAction.DENY,
            agent_id="research-agent",
            risk_score=80,
            reason_codes=[ReasonCode.TOOL_NOT_ALLOWED],
            duration=2.1,
        )
        audit.log(event)

        result = json.loads(audit.to_json())
        assert len(result) == 1
        assert result[0]["decision_id"] == "d-4a8b2c1f"
        assert result[0]["action"] == "deny"
        assert result[0]["tool_name"] == "tool.execution"
        assert result[0]["reason_codes"] == ["TOOL_NOT_ALLOWED"]
        assert result[0]["risk_score"] == 80
        assert result[0]["evaluation_time_ms"] == 2.1

    def test_to_json_multiple_decisions(self):
        """Test to_json with multiple decisions."""
        audit = self._create_audit()

        for i in range(3):
            event = self._make_event(
                correlation_id=f"correlation-{i}",
                action=DecisionAction.ALLOW if i % 2 == 0 else DecisionAction.DENY,
                agent_id=f"agent-{i}",
                risk_score=i * 30,
            )
            audit.log(event)

        result = json.loads(audit.to_json())
        assert len(result) == 3
        assert result[0]["action"] == "allow"
        assert result[1]["action"] == "deny"
        assert result[2]["action"] == "allow"

    def test_to_json_output_schema(self):
        """Test that to_json output contains all required fields."""
        audit = self._create_audit()
        event = self._make_event(
            correlation_id="test-id",
            action=DecisionAction.ALLOW,
            agent_id="test-agent",
            timestamp="2026-06-16T14:30:00Z",
        )
        audit.log(event)

        result = json.loads(audit.to_json())
        required_fields = [
            "decision_id",
            "timestamp",
            "agent_id",
            "action",
            "tool_name",
            "reason_codes",
            "risk_score",
            "evaluation_time_ms",
        ]
        for field in required_fields:
            assert field in result[0], f"Missing required field: {field}"

    def test_to_json_reason_codes_list(self):
        """Test that reason_codes is always a list of strings."""
        audit = self._create_audit()
        event = self._make_event(
            correlation_id="test-id",
            action=DecisionAction.DENY,
            reason_codes=[
                ReasonCode.PII_DETECTED,
                ReasonCode.PROMPT_INJECTION_DETECTED,
            ],
        )
        audit.log(event)

        result = json.loads(audit.to_json())
        assert isinstance(result[0]["reason_codes"], list)
        assert result[0]["reason_codes"] == ["PII_DETECTED", "PROMPT_INJECTION_DETECTED"]

    def test_to_json_risk_score_is_int(self):
        """Test that risk_score is converted to int."""
        audit = self._create_audit()
        event = self._make_event(
            correlation_id="test-id",
            action=DecisionAction.ALLOW,
            risk_score=42.7,  # float should be converted to int
        )
        audit.log(event)

        result = json.loads(audit.to_json())
        assert isinstance(result[0]["risk_score"], int)
        assert result[0]["risk_score"] == 42

    def test_to_json_risk_score_none(self):
        """Test that None risk_score stays None."""
        audit = self._create_audit()
        event = self._make_event(
            correlation_id="test-id",
            action=DecisionAction.ALLOW,
            risk_score=None,
        )
        audit.log(event)

        result = json.loads(audit.to_json())
        assert result[0]["risk_score"] is None

    def test_to_json_output_is_valid_json(self):
        """Test that to_json always returns valid JSON."""
        audit = self._create_audit()

        # Log various event types
        for event_type in AuditEventType:
            event = self._make_event(
                event_type=event_type,
                correlation_id=f"test-{event_type.value}",
                action=DecisionAction.ALLOW,
                agent_id="test-agent",
            )
            audit.log(event)

        # Should not raise and should be parseable
        result = json.loads(audit.to_json())
        assert len(result) == len(AuditEventType)
