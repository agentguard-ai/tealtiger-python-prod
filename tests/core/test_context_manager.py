"""Unit tests for ContextManager and ExecutionContext.

Tests P0.3: Correlation IDs and Traceability
"""

import re
from datetime import datetime

import pytest

from tealtiger.core.context import (
    CONTEXT_HEADERS,
    ContextManager,
    ExecutionContext,
    ExecutionContextOptions,
    generate_correlation_id,
    generate_span_id,
    generate_trace_id,
    generate_uuid_v4,
    is_valid_correlation_id,
    is_valid_uuid_v4,
    validate_execution_context,
)


class TestUUIDGeneration:
    """Tests for UUID generation functions."""

    def test_generate_uuid_v4_format(self):
        """Test that generated UUID v4 has correct format."""
        uuid = generate_uuid_v4()
        assert is_valid_uuid_v4(uuid)
        assert len(uuid) == 36
        assert uuid.count("-") == 4

    def test_generate_uuid_v4_uniqueness(self):
        """Test that generated UUIDs are unique."""
        uuids = [generate_uuid_v4() for _ in range(100)]
        assert len(set(uuids)) == 100

    def test_generate_correlation_id(self):
        """Test correlation ID generation."""
        corr_id = generate_correlation_id()
        assert is_valid_uuid_v4(corr_id)
        assert is_valid_correlation_id(corr_id)

    def test_generate_span_id_format(self):
        """Test span ID generation format (16 hex chars)."""
        span_id = generate_span_id()
        assert len(span_id) == 16
        assert re.match(r"^[0-9a-f]{16}$", span_id)

    def test_generate_trace_id_format(self):
        """Test trace ID generation format (32 hex chars)."""
        trace_id = generate_trace_id()
        assert len(trace_id) == 32
        assert re.match(r"^[0-9a-f]{32}$", trace_id)


class TestExecutionContext:
    """Tests for ExecutionContext model."""

    def test_create_minimal_context(self):
        """Test creating context with only required fields."""
        context = ExecutionContext(correlation_id="test-123")
        assert context.correlation_id == "test-123"
        assert context.trace_id is None
        assert context.metadata == {}

    def test_create_full_context(self):
        """Test creating context with all fields."""
        context = ExecutionContext(
            correlation_id="test-123",
            trace_id="trace-456",
            workflow_id="workflow-789",
            run_id="run-abc",
            span_id="span-def",
            parent_span_id="parent-ghi",
            tenant_id="tenant-001",
            application="test-app",
            environment="production",
            agent_purpose="customer-support",
            session_id="session-xyz",
            user_id="user-123",
            created_at="2024-01-01T00:00:00Z",
            metadata={"key": "value"},
        )
        assert context.correlation_id == "test-123"
        assert context.trace_id == "trace-456"
        assert context.workflow_id == "workflow-789"
        assert context.run_id == "run-abc"
        assert context.span_id == "span-def"
        assert context.parent_span_id == "parent-ghi"
        assert context.tenant_id == "tenant-001"
        assert context.application == "test-app"
        assert context.environment == "production"
        assert context.agent_purpose == "customer-support"
        assert context.session_id == "session-xyz"
        assert context.user_id == "user-123"
        assert context.created_at == "2024-01-01T00:00:00Z"
        assert context.metadata == {"key": "value"}

    def test_validate_valid_context(self):
        """Test validation of valid context."""
        context = ExecutionContext(correlation_id="test-123")
        validate_execution_context(context)  # Should not raise

    def test_validate_empty_correlation_id(self):
        """Test validation fails for empty correlation ID."""
        context = ExecutionContext(correlation_id="")
        with pytest.raises(ValueError, match="non-empty correlation_id"):
            validate_execution_context(context)


class TestContextManager:
    """Tests for ContextManager utility class."""

    def test_create_context_auto_generates_correlation_id(self):
        """Test that create_context auto-generates correlation ID."""
        context = ContextManager.create_context()
        assert context.correlation_id
        assert is_valid_uuid_v4(context.correlation_id)
        assert context.created_at

    def test_create_context_with_provided_correlation_id(self):
        """Test create_context with provided correlation ID."""
        options = ExecutionContextOptions(correlation_id="custom-123")
        context = ContextManager.create_context(options)
        assert context.correlation_id == "custom-123"

    def test_create_context_with_all_options(self):
        """Test create_context with all options."""
        options = ExecutionContextOptions(
            correlation_id="test-123",
            trace_id="trace-456",
            workflow_id="workflow-789",
            run_id="run-abc",
            span_id="span-def",
            parent_span_id="parent-ghi",
            tenant_id="tenant-001",
            application="test-app",
            environment="staging",
            agent_purpose="data-analyst",
            session_id="session-xyz",
            user_id="user-456",
            metadata={"custom": "data"},
        )
        context = ContextManager.create_context(options)
        assert context.correlation_id == "test-123"
        assert context.trace_id == "trace-456"
        assert context.workflow_id == "workflow-789"
        assert context.run_id == "run-abc"
        assert context.span_id == "span-def"
        assert context.parent_span_id == "parent-ghi"
        assert context.tenant_id == "tenant-001"
        assert context.application == "test-app"
        assert context.environment == "staging"
        assert context.agent_purpose == "data-analyst"
        assert context.session_id == "session-xyz"
        assert context.user_id == "user-456"
        assert context.metadata == {"custom": "data"}

    def test_from_headers_extracts_all_fields(self):
        """Test from_headers extracts all context fields."""
        headers = {
            CONTEXT_HEADERS["CORRELATION_ID"]: "corr-123",
            CONTEXT_HEADERS["TRACE_ID"]: "trace-456",
            CONTEXT_HEADERS["WORKFLOW_ID"]: "workflow-789",
            CONTEXT_HEADERS["RUN_ID"]: "run-abc",
            CONTEXT_HEADERS["SPAN_ID"]: "span-def",
            CONTEXT_HEADERS["PARENT_SPAN_ID"]: "parent-ghi",
            CONTEXT_HEADERS["TENANT_ID"]: "tenant-001",
            CONTEXT_HEADERS["APPLICATION"]: "test-app",
            CONTEXT_HEADERS["ENVIRONMENT"]: "production",
            CONTEXT_HEADERS["AGENT_PURPOSE"]: "support",
            CONTEXT_HEADERS["SESSION_ID"]: "session-xyz",
            CONTEXT_HEADERS["USER_ID"]: "user-789",
        }
        context = ContextManager.from_headers(headers)
        assert context.correlation_id == "corr-123"
        assert context.trace_id == "trace-456"
        assert context.workflow_id == "workflow-789"
        assert context.run_id == "run-abc"
        assert context.span_id == "span-def"
        assert context.parent_span_id == "parent-ghi"
        assert context.tenant_id == "tenant-001"
        assert context.application == "test-app"
        assert context.environment == "production"
        assert context.agent_purpose == "support"
        assert context.session_id == "session-xyz"
        assert context.user_id == "user-789"

    def test_from_headers_case_insensitive(self):
        """Test from_headers is case-insensitive."""
        headers = {
            "X-CORRELATION-ID": "corr-123",
            "TRACEPARENT": "trace-456",
        }
        context = ContextManager.from_headers(headers)
        assert context.correlation_id == "corr-123"
        assert context.trace_id == "trace-456"

    def test_from_headers_auto_generates_missing_correlation_id(self):
        """Test from_headers auto-generates correlation ID if missing."""
        headers = {CONTEXT_HEADERS["TRACE_ID"]: "trace-456"}
        context = ContextManager.from_headers(headers)
        assert context.correlation_id
        assert is_valid_uuid_v4(context.correlation_id)
        assert context.trace_id == "trace-456"

    def test_to_headers_includes_all_fields(self):
        """Test to_headers includes all context fields."""
        context = ExecutionContext(
            correlation_id="corr-123",
            trace_id="trace-456",
            workflow_id="workflow-789",
            run_id="run-abc",
            span_id="span-def",
            parent_span_id="parent-ghi",
            tenant_id="tenant-001",
            application="test-app",
            environment="production",
            agent_purpose="support",
            session_id="session-xyz",
            user_id="user-789",
        )
        headers = ContextManager.to_headers(context)
        assert headers[CONTEXT_HEADERS["CORRELATION_ID"]] == "corr-123"
        assert headers[CONTEXT_HEADERS["TRACE_ID"]] == "trace-456"
        assert headers[CONTEXT_HEADERS["WORKFLOW_ID"]] == "workflow-789"
        assert headers[CONTEXT_HEADERS["RUN_ID"]] == "run-abc"
        assert headers[CONTEXT_HEADERS["SPAN_ID"]] == "span-def"
        assert headers[CONTEXT_HEADERS["PARENT_SPAN_ID"]] == "parent-ghi"
        assert headers[CONTEXT_HEADERS["TENANT_ID"]] == "tenant-001"
        assert headers[CONTEXT_HEADERS["APPLICATION"]] == "test-app"
        assert headers[CONTEXT_HEADERS["ENVIRONMENT"]] == "production"
        assert headers[CONTEXT_HEADERS["AGENT_PURPOSE"]] == "support"
        assert headers[CONTEXT_HEADERS["SESSION_ID"]] == "session-xyz"
        assert headers[CONTEXT_HEADERS["USER_ID"]] == "user-789"

    def test_to_headers_omits_none_fields(self):
        """Test to_headers omits None fields."""
        context = ExecutionContext(correlation_id="corr-123")
        headers = ContextManager.to_headers(context)
        assert CONTEXT_HEADERS["CORRELATION_ID"] in headers
        assert CONTEXT_HEADERS["TRACE_ID"] not in headers
        assert CONTEXT_HEADERS["WORKFLOW_ID"] not in headers

    def test_propagate_preserves_correlation_id(self):
        """Test propagate preserves correlation ID."""
        parent = ExecutionContext(correlation_id="corr-123")
        child = ContextManager.propagate(parent)
        assert child.correlation_id == "corr-123"

    def test_propagate_generates_new_span_id(self):
        """Test propagate generates new span ID."""
        parent = ExecutionContext(correlation_id="corr-123", span_id="span-parent")
        child = ContextManager.propagate(parent)
        assert child.span_id
        assert child.span_id != parent.span_id
        assert len(child.span_id) == 16

    def test_propagate_sets_parent_span_id(self):
        """Test propagate sets parent_span_id from parent's span_id."""
        parent = ExecutionContext(correlation_id="corr-123", span_id="span-parent")
        child = ContextManager.propagate(parent)
        assert child.parent_span_id == "span-parent"

    def test_propagate_preserves_optional_fields(self):
        """Test propagate preserves optional fields from parent."""
        parent = ExecutionContext(
            correlation_id="corr-123",
            workflow_id="workflow-789",
            run_id="run-abc",
            trace_id="trace-456",
            tenant_id="tenant-001",
            application="test-app",
            environment="production",
            agent_purpose="support",
            session_id="session-xyz",
            user_id="user-789",
            metadata={"key": "value"},
        )
        child = ContextManager.propagate(parent)
        assert child.workflow_id == "workflow-789"
        assert child.run_id == "run-abc"
        assert child.trace_id == "trace-456"
        assert child.tenant_id == "tenant-001"
        assert child.application == "test-app"
        assert child.environment == "production"
        assert child.agent_purpose == "support"
        assert child.session_id == "session-xyz"
        assert child.user_id == "user-789"
        assert child.metadata == {"key": "value"}

    def test_propagate_with_overrides(self):
        """Test propagate with option overrides."""
        parent = ExecutionContext(
            correlation_id="corr-123",
            tenant_id="tenant-001",
        )
        options = ExecutionContextOptions(
            tenant_id="tenant-002",
            application="new-app",
        )
        child = ContextManager.propagate(parent, options)
        assert child.correlation_id == "corr-123"
        assert child.tenant_id == "tenant-002"
        assert child.application == "new-app"

    def test_enrich_adds_metadata(self):
        """Test enrich adds metadata to context."""
        context = ExecutionContext(
            correlation_id="corr-123",
            metadata={"existing": "value"},
        )
        enriched = ContextManager.enrich(context, {"new": "data"})
        assert enriched.metadata == {"existing": "value", "new": "data"}

    def test_enrich_overwrites_existing_metadata(self):
        """Test enrich overwrites existing metadata keys."""
        context = ExecutionContext(
            correlation_id="corr-123",
            metadata={"key": "old"},
        )
        enriched = ContextManager.enrich(context, {"key": "new"})
        assert enriched.metadata == {"key": "new"}

    def test_is_valid_returns_true_for_valid_context(self):
        """Test is_valid returns True for valid context."""
        context = ExecutionContext(correlation_id="corr-123")
        assert ContextManager.is_valid(context) is True

    def test_is_valid_returns_false_for_invalid_context(self):
        """Test is_valid returns False for invalid context."""
        context = ExecutionContext(correlation_id="")
        assert ContextManager.is_valid(context) is False

    def test_extract_with_none_creates_new_context(self):
        """Test extract with None creates new context."""
        context = ContextManager.extract(None)
        assert context.correlation_id
        assert is_valid_uuid_v4(context.correlation_id)

    def test_extract_with_existing_context_returns_same(self):
        """Test extract with existing context validates and returns it."""
        original = ExecutionContext(correlation_id="corr-123")
        extracted = ContextManager.extract(original)
        assert extracted.correlation_id == "corr-123"

    def test_extract_with_headers_creates_from_headers(self):
        """Test extract with headers creates context from headers."""
        headers = {CONTEXT_HEADERS["CORRELATION_ID"]: "corr-123"}
        context = ContextManager.extract(headers)
        assert context.correlation_id == "corr-123"


class TestHeaderRoundTrip:
    """Tests for header conversion round-trip."""

    def test_to_headers_from_headers_round_trip(self):
        """Test converting context to headers and back preserves data."""
        original = ExecutionContext(
            correlation_id="corr-123",
            trace_id="trace-456",
            workflow_id="workflow-789",
            run_id="run-abc",
            span_id="span-def",
            tenant_id="tenant-001",
            application="test-app",
            environment="production",
        )
        headers = ContextManager.to_headers(original)
        restored = ContextManager.from_headers(headers)
        assert restored.correlation_id == original.correlation_id
        assert restored.trace_id == original.trace_id
        assert restored.workflow_id == original.workflow_id
        assert restored.run_id == original.run_id
        assert restored.span_id == original.span_id
        assert restored.tenant_id == original.tenant_id
        assert restored.application == original.application
        assert restored.environment == original.environment
