"""
Unit tests for TealAudit types module
Tests versioned AuditEvent schema and validation
"""

import pytest
from datetime import datetime

from tealtiger.core.audit.types import (
    AUDIT_SCHEMA_VERSION,
    AuditEventType,
    SafeContent,
    AuditComponentVersions,
    CostMetadata,
    AuditEvent,
    is_valid_audit_event_type,
    validate_audit_event,
    create_audit_event,
)
from tealtiger.core.engine.types import PolicyMode, DecisionAction, ReasonCode


class TestAuditEventType:
    """Test AuditEventType enum"""

    def test_all_event_types_defined(self):
        """Test that all expected event types are defined"""
        expected_types = [
            "policy.evaluation",
            "guardrail.check",
            "llm.request",
            "llm.response",
            "tool.execution",
            "circuit.state_change",
            "anomaly.detected",
            "cost.threshold_exceeded",
            "cost.evaluation",
            "cost.budget_exceeded",
        ]

        for event_type in expected_types:
            assert AuditEventType(event_type) is not None

    def test_is_valid_audit_event_type(self):
        """Test validation of audit event types"""
        assert is_valid_audit_event_type("policy.evaluation") is True
        assert is_valid_audit_event_type("guardrail.check") is True
        assert is_valid_audit_event_type("invalid.type") is False
        assert is_valid_audit_event_type(None) is False
        assert is_valid_audit_event_type(123) is False


class TestSafeContent:
    """Test SafeContent model"""

    def test_safe_content_with_hash(self):
        """Test SafeContent with hash"""
        safe = SafeContent(
            hash="sha256:abc123",
            size=1024,
            category="prompt",
        )

        assert safe.hash == "sha256:abc123"
        assert safe.size == 1024
        assert safe.category == "prompt"

    def test_safe_content_minimal(self):
        """Test SafeContent with minimal fields"""
        safe = SafeContent(size=512)

        assert safe.hash is None
        assert safe.size == 512
        assert safe.category is None


class TestAuditComponentVersions:
    """Test AuditComponentVersions model"""

    def test_component_versions_all_fields(self):
        """Test component versions with all fields"""
        versions = AuditComponentVersions(
            sdk="1.1.0",
            engine="1.1.0",
            guard="1.1.0",
            circuit="1.1.0",
            monitor="1.1.0",
        )

        assert versions.sdk == "1.1.0"
        assert versions.engine == "1.1.0"
        assert versions.guard == "1.1.0"
        assert versions.circuit == "1.1.0"
        assert versions.monitor == "1.1.0"

    def test_component_versions_partial(self):
        """Test component versions with partial fields"""
        versions = AuditComponentVersions(sdk="1.1.0", engine="1.1.0")

        assert versions.sdk == "1.1.0"
        assert versions.engine == "1.1.0"
        assert versions.guard is None


class TestCostMetadata:
    """Test CostMetadata model"""

    def test_cost_metadata_full(self):
        """Test cost metadata with all fields"""
        cost = CostMetadata(
            estimated=0.05,
            actual=0.048,
            currency="USD",
            budget_scope="session",
            budget_window="per_session",
            budget_limit=1.0,
            budget_remaining=0.952,
            risk_score=25.0,
            model="gpt-4",
            model_tier="premium",
        )

        assert cost.estimated == 0.05
        assert cost.actual == 0.048
        assert cost.currency == "USD"
        assert cost.budget_scope == "session"
        assert cost.budget_remaining == 0.952

    def test_cost_metadata_minimal(self):
        """Test cost metadata with minimal fields"""
        cost = CostMetadata(estimated=0.01)

        assert cost.estimated == 0.01
        assert cost.actual is None
        assert cost.currency == "USD"  # Default


class TestAuditEvent:
    """Test AuditEvent model"""

    def test_audit_event_minimal(self):
        """Test audit event with minimal required fields"""
        event = AuditEvent(
            schema_version=AUDIT_SCHEMA_VERSION,
            event_type=AuditEventType.POLICY_EVALUATION,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="req-12345",
        )

        assert event.schema_version == AUDIT_SCHEMA_VERSION
        assert event.event_type == AuditEventType.POLICY_EVALUATION
        assert event.correlation_id == "req-12345"
        assert event.trace_id is None

    def test_audit_event_full(self):
        """Test audit event with all fields"""
        event = AuditEvent(
            schema_version=AUDIT_SCHEMA_VERSION,
            event_type=AuditEventType.POLICY_EVALUATION,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="req-12345",
            trace_id="trace-67890",
            workflow_id="workflow-001",
            run_id="run-001",
            span_id="span-001",
            parent_span_id="span-000",
            policy_id="tools.file_delete",
            policy_version="1.0.0",
            mode=PolicyMode.ENFORCE,
            action=DecisionAction.DENY,
            reason_codes=[ReasonCode.TOOL_NOT_ALLOWED],
            risk_score=95.0,
            agent_id="agent-001",
            provider="openai",
            model="gpt-4",
            cost=0.05,
            duration=150.0,
            safe_inputs=SafeContent(hash="sha256:abc", size=1024),
            safe_outputs=SafeContent(hash="sha256:def", size=2048),
            component_versions=AuditComponentVersions(sdk="1.1.0", engine="1.1.0"),
            metadata={"tenant_id": "acme-corp"},
        )

        assert event.correlation_id == "req-12345"
        assert event.trace_id == "trace-67890"
        assert event.workflow_id == "workflow-001"
        assert event.run_id == "run-001"
        assert event.span_id == "span-001"
        assert event.parent_span_id == "span-000"
        assert event.policy_id == "tools.file_delete"
        assert event.mode == PolicyMode.ENFORCE
        assert event.action == DecisionAction.DENY
        assert event.risk_score == 95.0
        assert event.metadata["tenant_id"] == "acme-corp"

    def test_audit_event_invalid_timestamp(self):
        """Test audit event with invalid timestamp format"""
        with pytest.raises(ValueError, match="Invalid ISO 8601 timestamp"):
            AuditEvent(
                schema_version=AUDIT_SCHEMA_VERSION,
                event_type=AuditEventType.POLICY_EVALUATION,
                timestamp="invalid-timestamp",
                correlation_id="req-12345",
            )

    def test_audit_event_empty_correlation_id(self):
        """Test audit event with empty correlation_id"""
        with pytest.raises(ValueError, match="correlation_id must be non-empty"):
            AuditEvent(
                schema_version=AUDIT_SCHEMA_VERSION,
                event_type=AuditEventType.POLICY_EVALUATION,
                timestamp=datetime.utcnow().isoformat() + "Z",
                correlation_id="",
            )

    def test_audit_event_with_cost_metadata(self):
        """Test audit event with cost metadata"""
        event = AuditEvent(
            schema_version=AUDIT_SCHEMA_VERSION,
            event_type=AuditEventType.COST_EVALUATION,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="req-12345",
            metadata={
                "cost": {
                    "estimated": 0.05,
                    "actual": 0.048,
                    "currency": "USD",
                    "budget_scope": "session",
                }
            },
        )

        assert event.metadata["cost"]["estimated"] == 0.05
        assert event.metadata["cost"]["actual"] == 0.048
        assert event.metadata["cost"]["budget_scope"] == "session"


class TestValidateAuditEvent:
    """Test validate_audit_event function"""

    def test_validate_valid_event(self):
        """Test validation of valid audit event"""
        event = AuditEvent(
            schema_version=AUDIT_SCHEMA_VERSION,
            event_type=AuditEventType.POLICY_EVALUATION,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="req-12345",
        )

        # Should not raise
        validate_audit_event(event)

    def test_validate_none_event(self):
        """Test validation of None event"""
        with pytest.raises(ValueError, match="AuditEvent is required"):
            validate_audit_event(None)


class TestCreateAuditEvent:
    """Test create_audit_event function"""

    def test_create_minimal_event(self):
        """Test creating minimal audit event"""
        event = create_audit_event(
            event_type=AuditEventType.POLICY_EVALUATION,
            correlation_id="req-12345",
        )

        assert event.schema_version == AUDIT_SCHEMA_VERSION
        assert event.event_type == AuditEventType.POLICY_EVALUATION
        assert event.correlation_id == "req-12345"
        assert event.timestamp is not None

    def test_create_event_with_kwargs(self):
        """Test creating audit event with additional fields"""
        event = create_audit_event(
            event_type=AuditEventType.GUARDRAIL_CHECK,
            correlation_id="req-67890",
            policy_id="pii.detection",
            action=DecisionAction.REDACT,
            risk_score=75.0,
        )

        assert event.event_type == AuditEventType.GUARDRAIL_CHECK
        assert event.correlation_id == "req-67890"
        assert event.policy_id == "pii.detection"
        assert event.action == DecisionAction.REDACT
        assert event.risk_score == 75.0

    def test_create_event_auto_timestamp(self):
        """Test that create_audit_event auto-generates timestamp"""
        event = create_audit_event(
            event_type=AuditEventType.LLM_REQUEST,
            correlation_id="req-99999",
        )

        # Timestamp should be in ISO 8601 format
        assert "T" in event.timestamp
        assert event.timestamp.endswith("Z")
