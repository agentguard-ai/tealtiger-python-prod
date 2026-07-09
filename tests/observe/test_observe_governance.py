"""
Unit tests for ObserveProxy governance integration (TEEC v2.1) — Python SDK.

Validates that observe() with governance=True produces v2.1 decisions,
governance=False preserves Phase 1 behavior, and error cases are handled.

Requirements: 8.1, 8.3, 8.4, 8.7
"""

import sys
import os
from unittest.mock import patch, MagicMock

# Ensure the src directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest

from tealtiger.observe import observe, SealConfigurationError
from tealtiger.observe.types import ProviderSignature, ToolCallInfo
from tealtiger.core.engine.v2_1.types import DecisionV21


# ---------------------------------------------------------------------------
# Mock Infrastructure
# ---------------------------------------------------------------------------


def _mock_usage_extractor(response):
    """Extract usage from mock response."""
    return {"inputTokens": 10, "outputTokens": 20, "totalTokens": 30}


def _mock_model_extractor(request, response):
    """Extract model name from request/response."""
    return "gpt-4o"


def _mock_tool_call_extractor(response):
    """Extract tool calls from response (empty)."""
    return []


def create_mock_provider_signature():
    """Create a mock ProviderSignature matching OpenAI pattern."""
    return ProviderSignature(
        provider="openai",
        intercept_methods=["chat.completions.create"],
        usage_extractor=_mock_usage_extractor,
        model_extractor=_mock_model_extractor,
        tool_call_extractor=_mock_tool_call_extractor,
    )


class MockCompletions:
    """Mock chat.completions namespace."""

    def create(self, **kwargs):
        return MagicMock(
            model="gpt-4o",
            choices=[MagicMock(message=MagicMock(content="Hello!"))],
            usage=MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )


class MockChat:
    """Mock chat namespace."""

    def __init__(self):
        self.completions = MockCompletions()


class MockOpenAIClient:
    """Mock OpenAI client for testing."""

    def __init__(self):
        self.chat = MockChat()
        self.base_url = "https://api.openai.com/v1"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("tealtiger.observe.observe.detect_provider")
class TestGovernanceEnabledProducesDecisions:
    """Test that governance=True produces v2.1 decisions after intercepted calls."""

    def test_governance_true_produces_v21_decisions(self, mock_detect):
        """governance=True produces DecisionV21 with all six v2.1 fields."""
        mock_detect.return_value = create_mock_provider_signature()
        client = MockOpenAIClient()

        proxy = observe(
            client,
            governance=True,
            governance_seal_secret="test-seal-secret",
            agent_id="test-agent-001",
            session_id="test-session-001",
        )

        # Make a call through the proxy
        proxy.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
        )

        decisions = proxy.get_decisions()
        assert len(decisions) == 1

        decision = decisions[0]

        # Verify all v2.1 fields are present
        assert decision.intent_ref is not None
        assert isinstance(decision.intent_ref, str)
        assert len(decision.intent_ref) == 64  # SHA-256 hex

        assert decision.receipt_ref is not None
        assert isinstance(decision.receipt_ref, str)
        assert len(decision.receipt_ref) == 64

        assert decision.seq == 1
        assert decision.running_count == 1

        assert decision.normalization_id is not None
        assert isinstance(decision.normalization_id, str)
        assert len(decision.normalization_id) == 64

        assert decision.governance_seal is not None
        assert isinstance(decision.governance_seal.hmac, str)
        assert len(decision.governance_seal.hmac) == 64
        assert isinstance(decision.governance_seal.timestamp, int)
        assert decision.governance_seal.agent_id == "test-agent-001"

        assert decision.teec_version == "2.1"

    def test_governance_true_populates_base_decision_fields(self, mock_detect):
        """governance=True also populates base fields (action, mode, etc.)."""
        mock_detect.return_value = create_mock_provider_signature()
        client = MockOpenAIClient()

        proxy = observe(
            client,
            governance=True,
            governance_seal_secret="secret-123",
            agent_id="agent-base-fields",
        )

        proxy.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Test"}],
        )

        decisions = proxy.get_decisions()
        decision = decisions[0]

        assert decision.action == "ALLOW"
        assert decision.reason_codes is not None
        assert decision.correlation_id != ""
        assert decision.module == "GovernanceEngineV21"


@patch("tealtiger.observe.observe.detect_provider")
class TestGovernanceDisabledPreservesPhase1:
    """Test that governance=False returns empty get_decisions() list."""

    def test_governance_not_set_returns_empty_decisions(self, mock_detect):
        """When governance is not set, get_decisions() returns empty list."""
        mock_detect.return_value = create_mock_provider_signature()
        client = MockOpenAIClient()

        proxy = observe(
            client,
            agent_id="test-agent-no-gov",
            session_id="test-session-no-gov",
        )

        proxy.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
        )

        decisions = proxy.get_decisions()
        assert decisions == []

    def test_governance_false_returns_empty_decisions(self, mock_detect):
        """When governance=False explicitly, get_decisions() returns empty list."""
        mock_detect.return_value = create_mock_provider_signature()
        client = MockOpenAIClient()

        proxy = observe(
            client,
            governance=False,
            agent_id="test-agent-false-gov",
        )

        proxy.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
        )

        decisions = proxy.get_decisions()
        assert decisions == []

    def test_governance_disabled_still_forwards_calls(self, mock_detect):
        """With governance=False, calls still forward to the provider."""
        mock_detect.return_value = create_mock_provider_signature()
        client = MockOpenAIClient()

        proxy = observe(
            client,
            governance=False,
            agent_id="test-agent-forward",
        )

        response = proxy.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
        )

        # Response should be valid (not None)
        assert response is not None


@patch("tealtiger.observe.observe.detect_provider")
class TestMissingSealSecretRaisesError:
    """Test error handling for missing seal_secret."""

    def test_governance_true_no_seal_secret_raises_seal_configuration_error(
        self, mock_detect
    ):
        """SealConfigurationError raised when governance=True but no seal_secret."""
        mock_detect.return_value = create_mock_provider_signature()
        client = MockOpenAIClient()

        with pytest.raises(SealConfigurationError):
            observe(
                client,
                governance=True,
                # governance_seal_secret intentionally omitted
            )

    def test_seal_configuration_error_has_descriptive_message(self, mock_detect):
        """SealConfigurationError message mentions seal_secret requirement."""
        mock_detect.return_value = create_mock_provider_signature()
        client = MockOpenAIClient()

        with pytest.raises(SealConfigurationError, match="seal_secret is required"):
            observe(
                client,
                governance=True,
            )

    def test_error_raised_at_initialization_not_at_first_call(self, mock_detect):
        """Error is raised during observe() init, not at the first call."""
        mock_detect.return_value = create_mock_provider_signature()
        client = MockOpenAIClient()

        # The error is raised synchronously during observe() initialization
        raised = False
        try:
            observe(client, governance=True)
        except SealConfigurationError:
            raised = True

        assert raised is True


@patch("tealtiger.observe.observe.detect_provider")
class TestMultipleCallsProduceSequentialDecisions:
    """Test that multiple calls produce sequential decisions with incrementing seq and running_count."""

    def test_sequential_seq_values(self, mock_detect):
        """Three calls produce decisions with seq values 1, 2, 3."""
        mock_detect.return_value = create_mock_provider_signature()
        client = MockOpenAIClient()

        proxy = observe(
            client,
            governance=True,
            governance_seal_secret="sequential-test-secret",
            agent_id="seq-agent",
        )

        proxy.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "First"}]
        )
        proxy.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "Second"}]
        )
        proxy.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "Third"}]
        )

        decisions = proxy.get_decisions()
        assert len(decisions) == 3

        assert decisions[0].seq == 1
        assert decisions[1].seq == 2
        assert decisions[2].seq == 3

    def test_sequential_running_count_values(self, mock_detect):
        """Three calls produce decisions with running_count values 1, 2, 3."""
        mock_detect.return_value = create_mock_provider_signature()
        client = MockOpenAIClient()

        proxy = observe(
            client,
            governance=True,
            governance_seal_secret="running-count-test-secret",
            agent_id="rc-agent",
        )

        proxy.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "A"}]
        )
        proxy.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "B"}]
        )
        proxy.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "C"}]
        )

        decisions = proxy.get_decisions()
        assert len(decisions) == 3

        assert decisions[0].running_count == 1
        assert decisions[1].running_count == 2
        assert decisions[2].running_count == 3

    def test_receipt_refs_are_unique_and_valid_sha256(self, mock_detect):
        """Multiple calls produce unique receipt_refs that are valid SHA-256 hex strings."""
        mock_detect.return_value = create_mock_provider_signature()
        client = MockOpenAIClient()

        proxy = observe(
            client,
            governance=True,
            governance_seal_secret="chain-test-secret",
            agent_id="chain-agent",
        )

        proxy.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "One"}]
        )
        proxy.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "Two"}]
        )
        proxy.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "Three"}]
        )

        decisions = proxy.get_decisions()
        assert len(decisions) == 3

        receipt_refs = [d.receipt_ref for d in decisions]
        unique_refs = set(receipt_refs)
        assert len(unique_refs) == 3

        # All receipt_refs should be valid SHA-256 hex strings (64 hex chars)
        import re

        hex_pattern = re.compile(r"^[0-9a-f]{64}$")
        for ref in receipt_refs:
            assert hex_pattern.match(ref), f"receipt_ref {ref!r} is not valid SHA-256 hex"
