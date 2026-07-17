"""Tests for TealTiger → Phoenix (Arize) governance span export.

Uses direct module import to avoid loading the full tealtiger package
(which has heavy provider dependencies that slow down test execution).
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch
from contextlib import contextmanager

# Add src to path for direct module import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _make_mock_tracer():
    """Create a mock OTel tracer with proper context manager support."""
    tracer = MagicMock()
    mock_span = MagicMock()

    @contextmanager
    def _span_cm(*args, **kwargs):
        yield mock_span

    tracer.start_as_current_span = MagicMock(side_effect=_span_cm)
    return tracer, mock_span


def _get_exporter_class(tracer):
    """Import and return PhoenixGovernanceSpanExporter with mocked tracer."""
    with patch("opentelemetry.trace.get_tracer", return_value=tracer):
        # Import directly from the module file to skip tealtiger __init__
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "phoenix_mod",
            os.path.join(
                os.path.dirname(__file__),
                "..", "src", "tealtiger", "integrations", "phoenix.py",
            ),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.PhoenixGovernanceSpanExporter


class TestAllowDecisions:
    def test_allow_creates_ok_span(self):
        """ALLOW decisions should create spans with OK status."""
        tracer, mock_span = _make_mock_tracer()
        cls = _get_exporter_class(tracer)

        with patch("opentelemetry.trace.get_tracer", return_value=tracer):
            exporter = cls()

        decision = {
            "action": "ALLOW",
            "correlation_id": "test-allow-123",
            "agent_id": "research-agent",
            "tool_name": "google_search",
            "reason_codes": ["POLICY_ALLOW"],
            "risk_score": 0,
            "evaluation_time_ms": 0.3,
            "mode": "ENFORCE",
        }

        exporter.export(decision)

        tracer.start_as_current_span.assert_called_once()
        from opentelemetry.trace import StatusCode
        mock_span.set_status.assert_called_with(StatusCode.OK)
        mock_span.set_attribute.assert_any_call("tealtiger.governance.action", "ALLOW")
        mock_span.set_attribute.assert_any_call("tealtiger.governance.mode", "ENFORCE")
        mock_span.set_attribute.assert_any_call("tealtiger.governance.tool_name", "google_search")

    def test_skip_allow_when_record_allows_false(self):
        """When record_allows=False, ALLOW decisions should not create spans."""
        tracer, _ = _make_mock_tracer()
        cls = _get_exporter_class(tracer)

        with patch("opentelemetry.trace.get_tracer", return_value=tracer):
            exporter = cls(record_allows=False)

        exporter.export({"action": "ALLOW", "correlation_id": "skip-me"})
        tracer.start_as_current_span.assert_not_called()


class TestDenyDecisions:
    def test_deny_creates_error_span(self):
        """DENY decisions should create spans with ERROR status."""
        tracer, mock_span = _make_mock_tracer()
        cls = _get_exporter_class(tracer)

        with patch("opentelemetry.trace.get_tracer", return_value=tracer):
            exporter = cls()

        decision = {
            "action": "DENY",
            "correlation_id": "test-deny-456",
            "agent_id": "coder",
            "tool_name": "send_email",
            "reason_codes": ["PII_DETECTED:ssn", "PII_DETECTED:email"],
            "risk_score": 90,
            "evaluation_time_ms": 0.8,
            "mode": "ENFORCE",
        }

        exporter.export(decision)

        from opentelemetry.trace import StatusCode
        mock_span.set_status.assert_called_with(
            StatusCode.ERROR, "PII_DETECTED:ssn, PII_DETECTED:email"
        )
        mock_span.add_event.assert_called_once()
        event_name = mock_span.add_event.call_args[0][0]
        assert event_name == "governance.denied"

    def test_deny_recorded_when_record_allows_false(self):
        """DENY decisions still recorded even when record_allows=False."""
        tracer, _ = _make_mock_tracer()
        cls = _get_exporter_class(tracer)

        with patch("opentelemetry.trace.get_tracer", return_value=tracer):
            exporter = cls(record_allows=False)

        exporter.export({"action": "DENY", "correlation_id": "r", "reason_codes": ["X"]})
        tracer.start_as_current_span.assert_called_once()


class TestMonitorDecisions:
    def test_monitor_creates_unset_span(self):
        """MONITOR decisions should create spans with UNSET status."""
        tracer, mock_span = _make_mock_tracer()
        cls = _get_exporter_class(tracer)

        with patch("opentelemetry.trace.get_tracer", return_value=tracer):
            exporter = cls()

        decision = {
            "action": "MONITOR",
            "correlation_id": "test-monitor",
            "reason_codes": ["COST_WARNING"],
            "risk_score": 50,
            "mode": "MONITOR",
        }

        exporter.export(decision)

        from opentelemetry.trace import StatusCode
        mock_span.set_status.assert_called_with(StatusCode.UNSET)


class TestAttributes:
    def test_cost_tracking_attributes(self):
        """Cost tracking attributes included when include_cost=True."""
        tracer, mock_span = _make_mock_tracer()
        cls = _get_exporter_class(tracer)

        with patch("opentelemetry.trace.get_tracer", return_value=tracer):
            exporter = cls(include_cost=True)

        exporter.export({
            "action": "ALLOW",
            "correlation_id": "cost-test",
            "cost_tracked": 0.005,
            "cumulative_cost": 1.50,
        })

        mock_span.set_attribute.assert_any_call("tealtiger.governance.cost_tracked", 0.005)
        mock_span.set_attribute.assert_any_call("tealtiger.governance.cumulative_cost", 1.50)

    def test_cost_excluded_when_disabled(self):
        """Cost attributes not set when include_cost=False."""
        tracer, mock_span = _make_mock_tracer()
        cls = _get_exporter_class(tracer)

        with patch("opentelemetry.trace.get_tracer", return_value=tracer):
            exporter = cls(include_cost=False)

        exporter.export({
            "action": "ALLOW",
            "correlation_id": "no-cost",
            "cost_tracked": 0.01,
            "cumulative_cost": 2.0,
        })

        attr_names = [c[0][0] for c in mock_span.set_attribute.call_args_list]
        assert "tealtiger.governance.cost_tracked" not in attr_names
        assert "tealtiger.governance.cumulative_cost" not in attr_names

    def test_policy_digest_attribute(self):
        """Policy digest recorded when present."""
        tracer, mock_span = _make_mock_tracer()
        cls = _get_exporter_class(tracer)

        with patch("opentelemetry.trace.get_tracer", return_value=tracer):
            exporter = cls()

        exporter.export({
            "action": "DENY",
            "correlation_id": "policy-test",
            "reason_codes": ["TOOL_NOT_ALLOWED"],
            "policy_digest": "sha256:abc123def456",
        })

        mock_span.set_attribute.assert_any_call(
            "tealtiger.governance.policy_digest", "sha256:abc123def456"
        )

    def test_pii_detected_attribute(self):
        """PII detection details included as span attribute."""
        tracer, mock_span = _make_mock_tracer()
        cls = _get_exporter_class(tracer)

        with patch("opentelemetry.trace.get_tracer", return_value=tracer):
            exporter = cls()

        exporter.export({
            "action": "DENY",
            "correlation_id": "pii-test",
            "reason_codes": ["PII_DETECTED"],
            "pii_detected": ["ssn", "credit_card"],
        })

        mock_span.set_attribute.assert_any_call(
            "tealtiger.governance.pii_detected", ["ssn", "credit_card"]
        )

    def test_span_kind_is_internal(self):
        """Governance spans should use INTERNAL span kind."""
        tracer, _ = _make_mock_tracer()
        cls = _get_exporter_class(tracer)

        with patch("opentelemetry.trace.get_tracer", return_value=tracer):
            exporter = cls()

        exporter.export({"action": "ALLOW", "correlation_id": "kind-test"})

        from opentelemetry.trace import SpanKind
        call_kwargs = tracer.start_as_current_span.call_args[1]
        assert call_kwargs["kind"] == SpanKind.INTERNAL


class TestBatchAndCounters:
    def test_export_batch(self):
        """export_batch should process all decisions."""
        tracer, _ = _make_mock_tracer()
        cls = _get_exporter_class(tracer)

        with patch("opentelemetry.trace.get_tracer", return_value=tracer):
            exporter = cls()

        decisions = [
            {"action": "ALLOW", "correlation_id": "b1"},
            {"action": "DENY", "correlation_id": "b2", "reason_codes": ["FROZEN"]},
            {"action": "ALLOW", "correlation_id": "b3"},
        ]

        exporter.export_batch(decisions)

        assert tracer.start_as_current_span.call_count == 3
        assert exporter.decision_count == 3
        assert exporter.deny_count == 1

    def test_decision_counter(self):
        """Decision and deny counters track correctly."""
        tracer, _ = _make_mock_tracer()
        cls = _get_exporter_class(tracer)

        with patch("opentelemetry.trace.get_tracer", return_value=tracer):
            exporter = cls()

        exporter.export({"action": "ALLOW", "correlation_id": "c1"})
        exporter.export({"action": "DENY", "correlation_id": "c2", "reason_codes": ["X"]})
        exporter.export({"action": "DENY", "correlation_id": "c3", "reason_codes": ["Y"]})
        exporter.export({"action": "ALLOW", "correlation_id": "c4"})

        assert exporter.decision_count == 4
        assert exporter.deny_count == 2

    def test_reset_counters(self):
        """reset_counters zeros out all counters."""
        tracer, _ = _make_mock_tracer()
        cls = _get_exporter_class(tracer)

        with patch("opentelemetry.trace.get_tracer", return_value=tracer):
            exporter = cls()

        exporter.export({"action": "DENY", "correlation_id": "r1", "reason_codes": ["Z"]})
        exporter.export({"action": "ALLOW", "correlation_id": "r2"})

        exporter.reset_counters()

        assert exporter.decision_count == 0
        assert exporter.deny_count == 0

    def test_custom_span_name(self):
        """Custom span names used when configured."""
        tracer, _ = _make_mock_tracer()
        cls = _get_exporter_class(tracer)

        with patch("opentelemetry.trace.get_tracer", return_value=tracer):
            exporter = cls(span_name="custom.governance.span")

        exporter.export({"action": "ALLOW", "correlation_id": "name-test"})

        call_kwargs = tracer.start_as_current_span.call_args[1]
        assert call_kwargs["name"] == "custom.governance.span"
