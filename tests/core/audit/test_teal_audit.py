"""
Unit tests for TealAudit class
Tests audit logging, context propagation, and querying
"""

import pytest
from datetime import datetime, timedelta
from typing import Any, Dict, List

from tealtiger.core.audit import (
    AuditConfig,
    AuditEvent,
    AuditEventType,
    ConsoleOutput,
    CustomOutput,
    RedactionLevel,
    TealAudit,
)
from tealtiger.core.context import ContextManager, ExecutionContext
from tealtiger.core.engine.types import DecisionAction, PolicyMode, ReasonCode


class MockOutput:
    """Mock output for testing"""

    def __init__(self):
        self.events: List[Dict[str, Any]] = []

    def write(self, event: Dict[str, Any]) -> None:
        self.events.append(event)

    def close(self) -> None:
        pass


class TestAuditConfig:
    """Test AuditConfig model"""

    def test_audit_config_defaults(self):
        """Test AuditConfig with default values"""
        config = AuditConfig()

        assert config.input_redaction == RedactionLevel.HASH
        assert config.output_redaction == RedactionLevel.HASH
        assert config.debug_mode is False
        assert config.detect_pii is True
        assert config.custom_redaction is None

    def test_audit_config_custom(self):
        """Test AuditConfig with custom values"""
        config = AuditConfig(
            input_redaction=RedactionLevel.SIZE_ONLY,
            output_redaction=RedactionLevel.CATEGORY_ONLY,
            debug_mode=True,
            detect_pii=False,
        )

        assert config.input_redaction == RedactionLevel.SIZE_ONLY
        assert config.output_redaction == RedactionLevel.CATEGORY_ONLY
        assert config.debug_mode is True
        assert config.detect_pii is False


class TestConsoleOutput:
    """Test ConsoleOutput"""

    def test_console_output_write(self, capsys):
        """Test ConsoleOutput writes to stdout"""
        output = ConsoleOutput()
        event = {"test": "data"}
        output.write(event)

        captured = capsys.readouterr()
        assert "test" in captured.out
        assert "data" in captured.out


class TestCustomOutput:
    """Test CustomOutput"""

    def test_custom_output_handler(self):
        """Test CustomOutput calls handler"""
        events = []

        def handler(event: Dict[str, Any]) -> None:
            events.append(event)

        output = CustomOutput(handler)
        event = {"test": "data"}
        output.write(event)

        assert len(events) == 1
        assert events[0]["test"] == "data"


class TestTealAuditInit:
    """Test TealAudit initialization"""

    def test_init_minimal(self):
        """Test TealAudit initialization with minimal config"""
        output = MockOutput()
        audit = TealAudit(outputs=[output])

        assert len(audit.outputs) == 1
        assert audit.max_events == 10000
        assert audit.enable_storage is True
        assert audit.config.input_redaction == RedactionLevel.HASH
        assert audit.config.debug_mode is False

    def test_init_with_config(self):
        """Test TealAudit initialization with custom config"""
        output = MockOutput()
        config = AuditConfig(
            input_redaction=RedactionLevel.SIZE_ONLY,
            debug_mode=True,
        )
        audit = TealAudit(outputs=[output], config=config)

        assert audit.config.input_redaction == RedactionLevel.SIZE_ONLY
        assert audit.config.debug_mode is True

    def test_init_debug_mode_warning(self, capsys):
        """Test that debug mode logs a warning"""
        output = MockOutput()
        config = AuditConfig(debug_mode=True)
        audit = TealAudit(outputs=[output], config=config)

        captured = capsys.readouterr()
        assert "DEBUG MODE ENABLED" in captured.out
        assert "DANGEROUS" in captured.out

    def test_get_config(self):
        """Test getting audit configuration"""
        output = MockOutput()
        config = AuditConfig(input_redaction=RedactionLevel.FULL)
        audit = TealAudit(outputs=[output], config=config)

        retrieved_config = audit.get_config()
        assert retrieved_config.input_redaction == RedactionLevel.FULL


class TestTealAuditLog:
    """Test TealAudit.log() method"""

    def test_log_minimal_event(self):
        """Test logging minimal audit event"""
        output = MockOutput()
        audit = TealAudit(outputs=[output])

        event = AuditEvent(
            schema_version="1.0.0",
            event_type=AuditEventType.POLICY_EVALUATION,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="req-12345",
        )

        audit.log(event)

        assert len(output.events) == 1
        assert output.events[0]["correlation_id"] == "req-12345"
        assert output.events[0]["event_type"] == "policy.evaluation"

    def test_log_full_event(self):
        """Test logging full audit event"""
        output = MockOutput()
        audit = TealAudit(outputs=[output])

        event = AuditEvent(
            schema_version="1.0.0",
            event_type=AuditEventType.POLICY_EVALUATION,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="req-12345",
            trace_id="trace-67890",
            policy_id="tools.file_delete",
            mode=PolicyMode.ENFORCE,
            action=DecisionAction.DENY,
            reason_codes=[ReasonCode.TOOL_NOT_ALLOWED],
            risk_score=95.0,
        )

        audit.log(event)

        assert len(output.events) == 1
        logged = output.events[0]
        assert logged["correlation_id"] == "req-12345"
        assert logged["trace_id"] == "trace-67890"
        assert logged["policy_id"] == "tools.file_delete"
        assert logged["mode"] == "ENFORCE"
        assert logged["action"] == "DENY"
        assert logged["risk_score"] == 95.0

    def test_log_with_context(self):
        """Test logging with ExecutionContext"""
        output = MockOutput()
        audit = TealAudit(outputs=[output])

        from tealtiger.core.context.execution_context import ExecutionContextOptions

        context = ContextManager.create_context(
            ExecutionContextOptions(
                tenant_id="acme-corp",
                environment="production",
                application="customer-support",
            )
        )

        event = AuditEvent(
            schema_version="1.0.0",
            event_type=AuditEventType.GUARDRAIL_CHECK,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="temp-id",
        )

        audit.log(event, context=context)

        assert len(output.events) == 1
        logged = output.events[0]
        # Context should override correlation_id
        assert logged["correlation_id"] == context.correlation_id
        assert logged["metadata"]["tenant_id"] == "acme-corp"
        assert logged["metadata"]["environment"] == "production"
        assert logged["metadata"]["application"] == "customer-support"

    def test_log_storage_enabled(self):
        """Test that events are stored when storage is enabled"""
        output = MockOutput()
        audit = TealAudit(outputs=[output], enable_storage=True)

        event = AuditEvent(
            schema_version="1.0.0",
            event_type=AuditEventType.LLM_REQUEST,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="req-12345",
        )

        audit.log(event)

        assert audit.get_event_count() == 1
        assert audit.events[0].correlation_id == "req-12345"

    def test_log_storage_disabled(self):
        """Test that events are not stored when storage is disabled"""
        output = MockOutput()
        audit = TealAudit(outputs=[output], enable_storage=False)

        event = AuditEvent(
            schema_version="1.0.0",
            event_type=AuditEventType.LLM_REQUEST,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="req-12345",
        )

        audit.log(event)

        assert audit.get_event_count() == 0

    def test_log_max_events_limit(self):
        """Test that max_events limit is enforced"""
        output = MockOutput()
        audit = TealAudit(outputs=[output], max_events=5, enable_storage=True)

        # Log 10 events
        for i in range(10):
            event = AuditEvent(
                schema_version="1.0.0",
                event_type=AuditEventType.LLM_REQUEST,
                timestamp=datetime.utcnow().isoformat() + "Z",
                correlation_id=f"req-{i}",
            )
            audit.log(event)

        # Only last 5 should be stored
        assert audit.get_event_count() == 5
        assert audit.events[0].correlation_id == "req-5"
        assert audit.events[4].correlation_id == "req-9"

    def test_log_multiple_outputs(self):
        """Test logging to multiple outputs"""
        output1 = MockOutput()
        output2 = MockOutput()
        audit = TealAudit(outputs=[output1, output2])

        event = AuditEvent(
            schema_version="1.0.0",
            event_type=AuditEventType.POLICY_EVALUATION,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="req-12345",
        )

        audit.log(event)

        assert len(output1.events) == 1
        assert len(output2.events) == 1


class TestTealAuditPropagateContext:
    """Test TealAudit.propagate_context() method"""

    def test_propagate_context_basic(self):
        """Test basic context propagation"""
        output = MockOutput()
        audit = TealAudit(outputs=[output])

        context = ExecutionContext(
            correlation_id="ctx-12345",
            trace_id="trace-67890",
        )

        event = AuditEvent(
            schema_version="1.0.0",
            event_type=AuditEventType.POLICY_EVALUATION,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="original-id",
        )

        enriched = audit.propagate_context(event, context)

        assert enriched.correlation_id == "ctx-12345"
        assert enriched.trace_id == "trace-67890"

    def test_propagate_context_all_fields(self):
        """Test context propagation with all fields"""
        output = MockOutput()
        audit = TealAudit(outputs=[output])

        context = ExecutionContext(
            correlation_id="ctx-12345",
            trace_id="trace-67890",
            workflow_id="workflow-001",
            run_id="run-001",
            span_id="span-001",
            parent_span_id="span-000",
            tenant_id="acme-corp",
            environment="production",
            application="customer-support",
        )

        event = AuditEvent(
            schema_version="1.0.0",
            event_type=AuditEventType.GUARDRAIL_CHECK,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="original-id",
        )

        enriched = audit.propagate_context(event, context)

        assert enriched.correlation_id == "ctx-12345"
        assert enriched.trace_id == "trace-67890"
        assert enriched.workflow_id == "workflow-001"
        assert enriched.run_id == "run-001"
        assert enriched.span_id == "span-001"
        assert enriched.parent_span_id == "span-000"
        assert enriched.metadata["tenant_id"] == "acme-corp"
        assert enriched.metadata["environment"] == "production"
        assert enriched.metadata["application"] == "customer-support"

    def test_propagate_context_preserves_original(self):
        """Test that propagate_context doesn't mutate original event"""
        output = MockOutput()
        audit = TealAudit(outputs=[output])

        context = ExecutionContext(correlation_id="new-id")

        event = AuditEvent(
            schema_version="1.0.0",
            event_type=AuditEventType.POLICY_EVALUATION,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="original-id",
        )

        enriched = audit.propagate_context(event, context)

        # Original should be unchanged
        assert event.correlation_id == "original-id"
        # Enriched should have new ID
        assert enriched.correlation_id == "new-id"


class TestTealAuditQuery:
    """Test TealAudit.query() method"""

    def test_query_all_events(self):
        """Test querying all events without filter"""
        output = MockOutput()
        audit = TealAudit(outputs=[output], enable_storage=True)

        # Log multiple events
        for i in range(3):
            event = AuditEvent(
                schema_version="1.0.0",
                event_type=AuditEventType.POLICY_EVALUATION,
                timestamp=datetime.utcnow().isoformat() + "Z",
                correlation_id=f"req-{i}",
            )
            audit.log(event)

        events = audit.query()
        assert len(events) == 3

    def test_query_by_correlation_id(self):
        """Test querying by correlation_id"""
        output = MockOutput()
        audit = TealAudit(outputs=[output], enable_storage=True)

        # Log events with different correlation IDs
        for i in range(5):
            event = AuditEvent(
                schema_version="1.0.0",
                event_type=AuditEventType.POLICY_EVALUATION,
                timestamp=datetime.utcnow().isoformat() + "Z",
                correlation_id="req-target" if i == 2 else f"req-{i}",
            )
            audit.log(event)

        from tealtiger.core.audit.teal_audit import AuditFilter

        events = audit.query(AuditFilter(correlation_id="req-target"))
        assert len(events) == 1
        assert events[0].correlation_id == "req-target"

    def test_query_by_min_cost(self):
        """Test querying by minimum cost"""
        output = MockOutput()
        audit = TealAudit(outputs=[output], enable_storage=True)

        # Log events with different costs
        for i, cost in enumerate([0.01, 0.05, 0.10, 0.15]):
            event = AuditEvent(
                schema_version="1.0.0",
                event_type=AuditEventType.LLM_REQUEST,
                timestamp=datetime.utcnow().isoformat() + "Z",
                correlation_id=f"req-{i}",
                cost=cost,
            )
            audit.log(event)

        from tealtiger.core.audit.teal_audit import AuditFilter

        events = audit.query(AuditFilter(min_cost=0.08))
        assert len(events) == 2
        assert all(e.cost >= 0.08 for e in events)

    def test_query_by_agent_id(self):
        """Test querying by agent IDs"""
        output = MockOutput()
        audit = TealAudit(outputs=[output], enable_storage=True)

        # Log events with different agent IDs
        for i in range(5):
            event = AuditEvent(
                schema_version="1.0.0",
                event_type=AuditEventType.POLICY_EVALUATION,
                timestamp=datetime.utcnow().isoformat() + "Z",
                correlation_id=f"req-{i}",
                agent_id=f"agent-{i % 2}",
            )
            audit.log(event)

        from tealtiger.core.audit.teal_audit import AuditFilter

        events = audit.query(AuditFilter(agents=["agent-0"]))
        assert len(events) == 3
        assert all(e.agent_id == "agent-0" for e in events)

    def test_query_by_time_range(self):
        """Test querying by time range"""
        output = MockOutput()
        audit = TealAudit(outputs=[output], enable_storage=True)

        now = datetime.utcnow()
        start_time = now - timedelta(hours=1)
        end_time = now + timedelta(hours=1)

        # Log event within range
        event = AuditEvent(
            schema_version="1.0.0",
            event_type=AuditEventType.POLICY_EVALUATION,
            timestamp=now.isoformat() + "Z",
            correlation_id="req-in-range",
        )
        audit.log(event)

        from tealtiger.core.audit.teal_audit import AuditFilter

        events = audit.query(AuditFilter(start_time=start_time, end_time=end_time))
        assert len(events) == 1

    def test_query_storage_disabled_raises(self):
        """Test that query raises when storage is disabled"""
        output = MockOutput()
        audit = TealAudit(outputs=[output], enable_storage=False)

        with pytest.raises(ValueError, match="Storage is disabled"):
            audit.query()


class TestTealAuditExport:
    """Test TealAudit.export() method"""

    def test_export_json(self):
        """Test exporting events to JSON"""
        output = MockOutput()
        audit = TealAudit(outputs=[output], enable_storage=True)

        event = AuditEvent(
            schema_version="1.0.0",
            event_type=AuditEventType.POLICY_EVALUATION,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="req-12345",
        )
        audit.log(event)

        json_export = audit.export(format="json")
        assert "req-12345" in json_export
        assert "policy.evaluation" in json_export

    def test_export_csv(self):
        """Test exporting events to CSV"""
        output = MockOutput()
        audit = TealAudit(outputs=[output], enable_storage=True)

        event = AuditEvent(
            schema_version="1.0.0",
            event_type=AuditEventType.POLICY_EVALUATION,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="req-12345",
        )
        audit.log(event)

        csv_export = audit.export(format="csv")
        assert "schema_version" in csv_export  # Header
        assert "req-12345" in csv_export

    def test_export_invalid_format(self):
        """Test exporting with invalid format"""
        output = MockOutput()
        audit = TealAudit(outputs=[output], enable_storage=True)

        with pytest.raises(ValueError, match="Unsupported export format"):
            audit.export(format="xml")


class TestTealAuditUtilities:
    """Test TealAudit utility methods"""

    def test_clear(self):
        """Test clearing stored events"""
        output = MockOutput()
        audit = TealAudit(outputs=[output], enable_storage=True)

        # Log events
        for i in range(3):
            event = AuditEvent(
                schema_version="1.0.0",
                event_type=AuditEventType.POLICY_EVALUATION,
                timestamp=datetime.utcnow().isoformat() + "Z",
                correlation_id=f"req-{i}",
            )
            audit.log(event)

        assert audit.get_event_count() == 3

        audit.clear()
        assert audit.get_event_count() == 0

    def test_get_event_count(self):
        """Test getting event count"""
        output = MockOutput()
        audit = TealAudit(outputs=[output], enable_storage=True)

        assert audit.get_event_count() == 0

        event = AuditEvent(
            schema_version="1.0.0",
            event_type=AuditEventType.POLICY_EVALUATION,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id="req-12345",
        )
        audit.log(event)

        assert audit.get_event_count() == 1

    def test_close(self):
        """Test closing outputs"""
        output = MockOutput()
        audit = TealAudit(outputs=[output])

        # Should not raise
        audit.close()
