"""
Comprehensive unit tests for tealtiger.observe module.

Tests cover:
- observe() with mock OpenAI/Anthropic clients
- Sync/async proxy delegation
- Freeze/unfreeze and wildcard freeze
- Provider detection for all 12 providers
- UnsupportedProviderError
- Cost tracking
- Behavioral baseline
- PII scanning
- Audit event structural parity
- Error propagation

Requirements: 8.1–8.6
"""

import sys
import os
import asyncio
import uuid

# Ensure the src directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from tealtiger.observe import (
    observe,
    freeze,
    unfreeze,
    UnsupportedProviderError,
    FrozenAgentError,
)
from tealtiger.observe.freeze_registry import FreezeRegistry
from tealtiger.observe.observe import ObserveProxy
from tealtiger.observe.pii_scanner import ObservePIIScanner
from tealtiger.observe.behavioral_baseline import BehavioralBaseline
from tealtiger.observe.types import BaselineSample


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_freeze_registry():
    """Reset FreezeRegistry singleton between tests to avoid state leakage."""
    FreezeRegistry.get_instance()._reset()
    yield
    FreezeRegistry.get_instance()._reset()


# ---------------------------------------------------------------------------
# Mock Client Infrastructure
# ---------------------------------------------------------------------------


class MockUsage:
    """Mock usage object matching OpenAI response.usage schema."""

    def __init__(self, prompt_tokens=10, completion_tokens=20, total_tokens=30):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class MockMessage:
    """Mock message in a chat completion choice."""

    def __init__(self, content="Hello!", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class MockChoice:
    """Mock choice in a chat completion response."""

    def __init__(self, message=None):
        self.message = message or MockMessage()


class MockOpenAIResponse:
    """Mock OpenAI chat completion response."""

    def __init__(self, model="gpt-4o", usage=None, choices=None):
        self.model = model
        self.usage = usage or MockUsage()
        self.choices = choices or [MockChoice()]


class MockCompletions:
    """Mock chat.completions namespace."""

    def create(self, **kwargs):
        return MockOpenAIResponse()


class MockChat:
    """Mock chat namespace."""

    def __init__(self):
        self.completions = MockCompletions()


class MockOpenAI:
    """Mock OpenAI client matching detection heuristics."""

    def __init__(self, base_url="https://api.openai.com/v1"):
        self.chat = MockChat()
        self.base_url = base_url


class MockAnthropicUsage:
    """Mock Anthropic usage object."""

    def __init__(self, input_tokens=15, output_tokens=25):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class MockAnthropicResponse:
    """Mock Anthropic messages.create response."""

    def __init__(self):
        self.model = "claude-3-sonnet-20240229"
        self.usage = MockAnthropicUsage()
        self.content = []
        self.stop_reason = "end_turn"


class MockMessages:
    """Mock Anthropic messages namespace."""

    def create(self, **kwargs):
        return MockAnthropicResponse()


class MockAnthropic:
    """Mock Anthropic client matching detection heuristics."""

    def __init__(self):
        self.messages = MockMessages()
        self.base_url = "https://api.anthropic.com"


class MockAsyncCompletions:
    """Mock async chat.completions namespace."""

    async def create(self, **kwargs):
        return MockOpenAIResponse()


class MockAsyncChat:
    """Mock async chat namespace."""

    def __init__(self):
        self.completions = MockAsyncCompletions()


class MockAsyncOpenAI:
    """Mock async OpenAI client."""

    def __init__(self):
        self.chat = MockAsyncChat()
        self.base_url = "https://api.openai.com/v1"


# ---------------------------------------------------------------------------
# 1. observe() with mock OpenAI client
# ---------------------------------------------------------------------------


class TestObserveOpenAI:
    """Tests for observe() wrapping a mock OpenAI client."""

    def test_observe_openai_mock_returns_response(self):
        """observe() proxy returns the original response object unchanged."""
        client = observe(MockOpenAI(), agent_id="test-agent")
        response = client.chat.completions.create(model="gpt-4o", messages=[])
        assert isinstance(response, MockOpenAIResponse)
        assert response.model == "gpt-4o"

    def test_observe_openai_creates_proxy(self):
        """observe() returns an ObserveProxy instance."""
        client = observe(MockOpenAI())
        assert isinstance(client, ObserveProxy)

    def test_observe_openai_cost_tracked_after_request(self):
        """After one request, cost summary reflects one request."""
        client = observe(MockOpenAI(), agent_id="cost-agent")
        client.chat.completions.create(model="gpt-4o", messages=[])
        cost = client.get_cost()
        assert cost.request_count == 1
        assert cost.total_cost > 0

    def test_observe_openai_agent_id_auto_generated(self):
        """If no agent_id given, a UUID v4 is auto-generated."""
        client = observe(MockOpenAI())
        agent_id = client.get_agent_id()
        # Should be a valid UUID v4
        parsed = uuid.UUID(agent_id, version=4)
        assert str(parsed) == agent_id

    def test_observe_openai_custom_agent_id(self):
        """User-supplied agent_id is preserved."""
        client = observe(MockOpenAI(), agent_id="my-agent-123")
        assert client.get_agent_id() == "my-agent-123"


# ---------------------------------------------------------------------------
# 2. observe() with mock Anthropic client
# ---------------------------------------------------------------------------


class TestObserveAnthropic:
    """Tests for observe() wrapping a mock Anthropic client."""

    def test_observe_anthropic_detects_provider(self):
        """observe() correctly detects Anthropic provider."""
        client = observe(MockAnthropic(), agent_id="anth-agent")
        # Proxy repr includes provider
        assert "anthropic" in repr(client)

    def test_observe_anthropic_returns_response(self):
        """observe() proxy returns the Anthropic response unchanged."""
        client = observe(MockAnthropic(), agent_id="anth-agent")
        response = client.messages.create(model="claude-3-sonnet", messages=[])
        assert isinstance(response, MockAnthropicResponse)
        assert response.model == "claude-3-sonnet-20240229"


# ---------------------------------------------------------------------------
# 3. Sync proxy delegation
# ---------------------------------------------------------------------------


class TestSyncProxyDelegation:
    """Verify non-intercepted methods pass through transparently."""

    def test_non_intercepted_attribute_passes_through(self):
        """Accessing base_url on proxy returns the client's base_url."""
        mock = MockOpenAI()
        client = observe(mock, agent_id="delegate-agent")
        assert client.base_url == "https://api.openai.com/v1"

    def test_repr_includes_provider_and_agent(self):
        """Proxy repr includes provider name and agent ID."""
        client = observe(MockOpenAI(), agent_id="repr-agent")
        r = repr(client)
        assert "openai" in r
        assert "repr-agent" in r


# ---------------------------------------------------------------------------
# 4. Async proxy delegation
# ---------------------------------------------------------------------------


class TestAsyncProxyDelegation:
    """Verify async methods are correctly detected and awaited."""

    def test_async_method_returns_response(self):
        """Async create method is properly awaited and returns response."""
        client = observe(MockAsyncOpenAI(), agent_id="async-agent")

        async def _run():
            return await client.chat.completions.create(
                model="gpt-4o", messages=[]
            )

        response = asyncio.run(_run())
        assert isinstance(response, MockOpenAIResponse)
        assert response.model == "gpt-4o"

    def test_async_method_tracks_cost(self):
        """Async requests are tracked in cost accumulator."""
        client = observe(MockAsyncOpenAI(), agent_id="async-cost-agent")

        async def _run():
            await client.chat.completions.create(model="gpt-4o", messages=[])

        asyncio.run(_run())
        cost = client.get_cost()
        assert cost.request_count == 1


# ---------------------------------------------------------------------------
# 5. Freeze / Unfreeze
# ---------------------------------------------------------------------------


class TestFreezeUnfreeze:
    """Verify FrozenAgentError is raised when frozen, unfreeze restores."""

    def test_freeze_blocks_request(self):
        """Frozen agent raises FrozenAgentError on request attempt."""
        client = observe(MockOpenAI(), agent_id="freeze-agent")
        freeze("freeze-agent")
        with pytest.raises(FrozenAgentError) as exc_info:
            client.chat.completions.create(model="gpt-4o", messages=[])
        assert exc_info.value.agent_id == "freeze-agent"
        assert exc_info.value.is_wildcard is False

    def test_unfreeze_restores_operation(self):
        """After unfreeze, requests succeed again."""
        client = observe(MockOpenAI(), agent_id="unfreeze-agent")
        freeze("unfreeze-agent")
        unfreeze("unfreeze-agent")
        # Should succeed without raising
        response = client.chat.completions.create(model="gpt-4o", messages=[])
        assert isinstance(response, MockOpenAIResponse)

    def test_freeze_idempotent(self):
        """Calling freeze multiple times is the same as calling once."""
        freeze("idem-agent")
        freeze("idem-agent")
        freeze("idem-agent")
        assert FreezeRegistry.get_instance().is_frozen("idem-agent") is True

    def test_unfreeze_noop_if_not_frozen(self):
        """Unfreeze on a non-frozen agent is a no-op (no error)."""
        unfreeze("never-frozen-agent")  # Should not raise


# ---------------------------------------------------------------------------
# 6. Wildcard freeze
# ---------------------------------------------------------------------------


class TestWildcardFreeze:
    """Verify freeze('*') blocks all agents."""

    def test_wildcard_freeze_blocks_all_agents(self):
        """freeze('*') blocks any agent."""
        client_a = observe(MockOpenAI(), agent_id="agent-a")
        client_b = observe(MockOpenAI(), agent_id="agent-b")
        freeze("*")

        with pytest.raises(FrozenAgentError) as exc_a:
            client_a.chat.completions.create(model="gpt-4o", messages=[])
        assert exc_a.value.is_wildcard is True

        with pytest.raises(FrozenAgentError) as exc_b:
            client_b.chat.completions.create(model="gpt-4o", messages=[])
        assert exc_b.value.is_wildcard is True

    def test_wildcard_unfreeze_restores_all(self):
        """unfreeze('*') removes the wildcard block."""
        client = observe(MockOpenAI(), agent_id="wild-agent")
        freeze("*")
        unfreeze("*")
        response = client.chat.completions.create(model="gpt-4o", messages=[])
        assert isinstance(response, MockOpenAIResponse)


# ---------------------------------------------------------------------------
# 7. Provider detection — all 12 providers
# ---------------------------------------------------------------------------


class TestProviderDetection:
    """Verify all 12 providers detected correctly with minimal mocks."""

    def test_detect_openai(self):
        """OpenAI detected from chat.completions + openai URL."""
        client = observe(MockOpenAI(), agent_id="p-openai")
        assert "openai" in repr(client)

    def test_detect_anthropic(self):
        """Anthropic detected from messages attribute."""
        client = observe(MockAnthropic(), agent_id="p-anthropic")
        assert "anthropic" in repr(client)

    def test_detect_azure_openai(self):
        """Azure OpenAI detected from chat.completions + azure in URL."""
        mock = MockOpenAI(base_url="https://myresource.openai.azure.com/")
        client = observe(mock, agent_id="p-azure")
        assert "azure-openai" in repr(client)

    def test_detect_deepseek(self):
        """DeepSeek detected from chat.completions + deepseek in URL."""
        mock = MockOpenAI(base_url="https://api.deepseek.com/v1")
        client = observe(mock, agent_id="p-deepseek")
        assert "deepseek" in repr(client)

    def test_detect_groq(self):
        """Groq detected from chat.completions + groq in URL."""
        mock = MockOpenAI(base_url="https://api.groq.com/openai/v1")
        client = observe(mock, agent_id="p-groq")
        assert "groq" in repr(client)

    def test_detect_xai(self):
        """xAI detected from chat.completions + x.ai in URL."""
        mock = MockOpenAI(base_url="https://api.x.ai/v1")
        client = observe(mock, agent_id="p-xai")
        assert "xai" in repr(client)

    def test_detect_together(self):
        """Together detected from chat.completions + together in URL."""
        mock = MockOpenAI(base_url="https://api.together.xyz/v1")
        client = observe(mock, agent_id="p-together")
        assert "together" in repr(client)

    def test_detect_gemini(self):
        """Gemini detected from generate_content method."""

        class MockGemini:
            base_url = ""

            def generate_content(self, **kwargs):
                return None

        client = observe(MockGemini(), agent_id="p-gemini")
        assert "gemini" in repr(client)

    def test_detect_bedrock(self):
        """Bedrock detected from invoke_model method."""

        class MockBedrock:
            base_url = ""

            def invoke_model(self, **kwargs):
                return None

        client = observe(MockBedrock(), agent_id="p-bedrock")
        assert "bedrock" in repr(client)

    def test_detect_cohere(self):
        """Cohere detected from chat + generate methods."""

        class MockCohere:
            base_url = ""

            def chat(self, **kwargs):
                return None

            def generate(self, **kwargs):
                return None

        client = observe(MockCohere(), agent_id="p-cohere")
        assert "cohere" in repr(client)

    def test_detect_mistral(self):
        """Mistral detected from chat method + class name."""

        class MistralClient:
            base_url = ""

            def chat(self, **kwargs):
                return None

        client = observe(MistralClient(), agent_id="p-mistral")
        assert "mistral" in repr(client)

    def test_detect_hf_tgi(self):
        """HF-TGI detected from text_generation method."""

        class MockHFTGI:
            base_url = ""

            def text_generation(self, **kwargs):
                return None

        client = observe(MockHFTGI(), agent_id="p-hf")
        assert "hf-tgi" in repr(client)


# ---------------------------------------------------------------------------
# 8. UnsupportedProviderError
# ---------------------------------------------------------------------------


class TestUnsupportedProvider:
    """Verify error thrown for unsupported clients."""

    def test_unsupported_provider_raises(self):
        """A plain object with no provider traits raises UnsupportedProviderError."""

        class RandomClient:
            pass

        with pytest.raises(UnsupportedProviderError) as exc_info:
            observe(RandomClient())
        assert "RandomClient" in str(exc_info.value)
        assert exc_info.value.client_type == "RandomClient"

    def test_unsupported_provider_message_lists_supported(self):
        """Error message lists the supported providers."""

        class BadClient:
            pass

        with pytest.raises(UnsupportedProviderError) as exc_info:
            observe(BadClient())
        msg = str(exc_info.value)
        assert "OpenAI" in msg
        assert "Anthropic" in msg
        assert "Gemini" in msg


# ---------------------------------------------------------------------------
# 9. Cost tracking
# ---------------------------------------------------------------------------


class TestCostTracking:
    """Verify per-request cost calculation, session/agent totals."""

    def test_cost_increases_with_requests(self):
        """Each request increases the running cost total."""
        client = observe(MockOpenAI(), agent_id="cost-track")
        client.chat.completions.create(model="gpt-4o", messages=[])
        cost_after_one = client.get_cost().total_cost

        client.chat.completions.create(model="gpt-4o", messages=[])
        cost_after_two = client.get_cost().total_cost

        assert cost_after_two > cost_after_one

    def test_cost_breakdown_has_input_and_output(self):
        """Cost breakdown separates input and output costs."""
        client = observe(MockOpenAI(), agent_id="breakdown-agent")
        client.chat.completions.create(model="gpt-4o", messages=[])
        cost = client.get_cost()
        assert cost.breakdown.input_cost > 0
        assert cost.breakdown.output_cost > 0

    def test_agent_cost_equals_session_cost_single_session(self):
        """With one session, agent cost equals session cost."""
        client = observe(MockOpenAI(), agent_id="single-session")
        client.chat.completions.create(model="gpt-4o", messages=[])
        session_cost = client.get_cost()
        agent_cost = client.get_agent_cost()
        assert abs(session_cost.total_cost - agent_cost.total_cost) < 1e-10

    def test_cost_request_count_accurate(self):
        """Request count increments correctly."""
        client = observe(MockOpenAI(), agent_id="count-agent")
        for _ in range(5):
            client.chat.completions.create(model="gpt-4o", messages=[])
        assert client.get_cost().request_count == 5


# ---------------------------------------------------------------------------
# 10. Behavioral Baseline
# ---------------------------------------------------------------------------


class TestBehavioralBaseline:
    """Verify window completion, percentile computation, immutability."""

    def test_baseline_incomplete_before_window(self):
        """Baseline is not complete until window_size requests."""
        client = observe(MockOpenAI(), agent_id="bl-agent", baseline_window=5)
        for _ in range(4):
            client.chat.completions.create(model="gpt-4o", messages=[])
        baseline = client.get_baseline()
        assert baseline.is_complete is False
        assert baseline.sample_count == 4

    def test_baseline_completes_at_window_size(self):
        """Baseline completes exactly at window_size requests."""
        client = observe(MockOpenAI(), agent_id="bl-complete", baseline_window=3)
        for _ in range(3):
            client.chat.completions.create(model="gpt-4o", messages=[])
        baseline = client.get_baseline()
        assert baseline.is_complete is True
        assert baseline.sample_count == 3
        assert baseline.stats is not None

    def test_baseline_has_percentile_stats(self):
        """Completed baseline has P50/P95/P99 stats for all metrics."""
        client = observe(MockOpenAI(), agent_id="bl-stats", baseline_window=3)
        for _ in range(3):
            client.chat.completions.create(model="gpt-4o", messages=[])
        stats = client.get_baseline().stats
        assert stats is not None
        assert stats.latency_ms.p50 >= 0
        assert stats.latency_ms.p95 >= stats.latency_ms.p50
        assert stats.cost_usd.p50 >= 0

    def test_baseline_immutable_after_completion(self):
        """After completion, additional samples do not change stats."""
        bl = BehavioralBaseline(window_size=2)
        bl.add_sample(BaselineSample(latency_ms=10.0, input_tokens=5,
                                     output_tokens=10, cost_usd=0.01,
                                     tool_call_count=0))
        bl.add_sample(BaselineSample(latency_ms=20.0, input_tokens=15,
                                     output_tokens=20, cost_usd=0.02,
                                     tool_call_count=1))
        stats_before = bl.get_baseline().stats

        # Add more — should be no-op
        bl.add_sample(BaselineSample(latency_ms=100.0, input_tokens=100,
                                     output_tokens=200, cost_usd=1.0,
                                     tool_call_count=5))
        stats_after = bl.get_baseline().stats

        assert stats_before == stats_after
        assert bl.get_baseline().sample_count == 2


# ---------------------------------------------------------------------------
# 11. PII Scanning
# ---------------------------------------------------------------------------


class TestPIIScanning:
    """Verify email, phone, SSN, credit card detection; never throws."""

    def test_pii_detects_email(self):
        """Scanner detects email addresses."""
        scanner = ObservePIIScanner()
        result = scanner.scan("Contact me at user@example.com", "request")
        assert result is not None
        assert "email" in result.types
        assert result.count >= 1

    def test_pii_detects_phone(self):
        """Scanner detects phone numbers."""
        scanner = ObservePIIScanner()
        result = scanner.scan("Call 555-123-4567 now", "request")
        assert result is not None
        assert "phone" in result.types

    def test_pii_detects_ssn(self):
        """Scanner detects Social Security Numbers."""
        scanner = ObservePIIScanner()
        result = scanner.scan("SSN: 123-45-6789", "request")
        assert result is not None
        assert "ssn" in result.types

    def test_pii_detects_credit_card(self):
        """Scanner detects credit card numbers."""
        scanner = ObservePIIScanner()
        result = scanner.scan("Card: 4111 1111 1111 1111", "request")
        assert result is not None
        assert "credit_card" in result.types

    def test_pii_returns_none_for_clean_text(self):
        """Scanner returns None when no PII found."""
        scanner = ObservePIIScanner()
        result = scanner.scan("Hello, how are you?", "request")
        assert result is None

    def test_pii_never_throws_on_bad_input(self):
        """Scanner never raises exceptions — returns None on error."""
        scanner = ObservePIIScanner()
        # None input
        result = scanner.scan(None, "request")
        assert result is None

        # Complex nested object
        result = scanner.scan({"nested": {"deep": object()}}, "request")
        # Should not raise — either None or a valid result
        assert result is None or hasattr(result, "count")

    def test_pii_detects_multiple_types(self):
        """Scanner detects multiple PII types in one payload."""
        scanner = ObservePIIScanner()
        text = "Email: foo@bar.com, SSN: 111-22-3333, Phone: 555-444-3333"
        result = scanner.scan(text, "response")
        assert result is not None
        assert result.count >= 3
        assert "email" in result.types
        assert "ssn" in result.types
        assert "phone" in result.types


# ---------------------------------------------------------------------------
# 12. Audit event structural parity
# ---------------------------------------------------------------------------


class TestAuditEvents:
    """Verify audit event types emitted during observe() lifecycle."""

    def test_audit_emits_request_and_response_events(self):
        """A successful request emits observe.request and observe.response."""
        client = observe(MockOpenAI(), agent_id="audit-agent")
        client.chat.completions.create(model="gpt-4o", messages=[])

        # Access internal audit logger via proxy internals
        audit_logger = object.__getattribute__(client, "_audit_logger")
        events = audit_logger.get_events()
        event_types = [e.type for e in events]

        assert "observe.request" in event_types
        assert "observe.response" in event_types

    def test_audit_emits_error_event_on_exception(self):
        """Provider errors emit observe.error before re-raising."""

        class FailingCompletions:
            def create(self, **kwargs):
                raise RuntimeError("API timeout")

        class FailingChat:
            completions = FailingCompletions()

        class FailingOpenAI:
            chat = FailingChat()
            base_url = "https://api.openai.com/v1"

        client = observe(FailingOpenAI(), agent_id="error-audit-agent")
        with pytest.raises(RuntimeError):
            client.chat.completions.create(model="gpt-4o", messages=[])

        audit_logger = object.__getattribute__(client, "_audit_logger")
        event_types = [e.type for e in audit_logger.get_events()]
        assert "observe.error" in event_types

    def test_audit_emits_tool_call_event(self):
        """Tool calls in response emit observe.tool_call events."""

        class MockFunction:
            name = "get_weather"
            arguments = '{"location": "Seattle"}'

        class MockToolCall:
            function = MockFunction()

        class ToolMessage(MockMessage):
            def __init__(self):
                super().__init__(tool_calls=[MockToolCall()])

        class ToolChoice(MockChoice):
            def __init__(self):
                super().__init__(message=ToolMessage())

        class ToolResponse(MockOpenAIResponse):
            def __init__(self):
                super().__init__(choices=[ToolChoice()])

        class ToolCompletions:
            def create(self, **kwargs):
                return ToolResponse()

        class ToolChat:
            completions = ToolCompletions()

        class ToolOpenAI:
            chat = ToolChat()
            base_url = "https://api.openai.com/v1"

        client = observe(ToolOpenAI(), agent_id="tool-audit-agent")
        client.chat.completions.create(model="gpt-4o", messages=[])

        audit_logger = object.__getattribute__(client, "_audit_logger")
        event_types = [e.type for e in audit_logger.get_events()]
        assert "observe.tool_call" in event_types

        # Verify tool call data
        tool_events = [e for e in audit_logger.get_events()
                       if e.type == "observe.tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0].data["tool_name"] == "get_weather"
        assert tool_events[0].data["argument_count"] == 1
        assert tool_events[0].data["arguments_hash"].startswith("sha256:")

    def test_audit_emits_freeze_block_event(self):
        """Frozen agent emits observe.freeze_block before raising."""
        client = observe(MockOpenAI(), agent_id="freeze-audit-agent")
        freeze("freeze-audit-agent")

        with pytest.raises(FrozenAgentError):
            client.chat.completions.create(model="gpt-4o", messages=[])

        audit_logger = object.__getattribute__(client, "_audit_logger")
        event_types = [e.type for e in audit_logger.get_events()]
        assert "observe.freeze_block" in event_types

    def test_audit_emits_baseline_complete_event(self):
        """Baseline completion emits observe.baseline_complete once."""
        client = observe(MockOpenAI(), agent_id="bl-audit",
                         baseline_window=2)
        client.chat.completions.create(model="gpt-4o", messages=[])
        client.chat.completions.create(model="gpt-4o", messages=[])

        audit_logger = object.__getattribute__(client, "_audit_logger")
        event_types = [e.type for e in audit_logger.get_events()]
        assert "observe.baseline_complete" in event_types
        # Should only emit once even with more requests
        client.chat.completions.create(model="gpt-4o", messages=[])
        bl_events = [e for e in audit_logger.get_events()
                     if e.type == "observe.baseline_complete"]
        assert len(bl_events) == 1


# ---------------------------------------------------------------------------
# 13. Error propagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    """Verify provider errors are re-thrown after logging."""

    def test_provider_error_rethrown_unchanged(self):
        """The original exception type and message are preserved."""

        class APIError(Exception):
            pass

        class ErrorCompletions:
            def create(self, **kwargs):
                raise APIError("Rate limit exceeded")

        class ErrorChat:
            completions = ErrorCompletions()

        class ErrorOpenAI:
            chat = ErrorChat()
            base_url = "https://api.openai.com/v1"

        client = observe(ErrorOpenAI(), agent_id="error-agent")
        with pytest.raises(APIError, match="Rate limit exceeded"):
            client.chat.completions.create(model="gpt-4o", messages=[])

    def test_provider_error_still_logged(self):
        """Error event is logged even when exception propagates."""

        class TimeoutError(Exception):
            pass

        class TimeoutCompletions:
            def create(self, **kwargs):
                raise TimeoutError("Connection timed out")

        class TimeoutChat:
            completions = TimeoutCompletions()

        class TimeoutOpenAI:
            chat = TimeoutChat()
            base_url = "https://api.openai.com/v1"

        client = observe(TimeoutOpenAI(), agent_id="timeout-agent")
        with pytest.raises(TimeoutError):
            client.chat.completions.create(model="gpt-4o", messages=[])

        audit_logger = object.__getattribute__(client, "_audit_logger")
        error_events = [e for e in audit_logger.get_events()
                        if e.type == "observe.error"]
        assert len(error_events) == 1
        assert error_events[0].data["error_type"] == "TimeoutError"
        assert "timed out" in error_events[0].data["error_message"]

    def test_async_provider_error_rethrown(self):
        """Async provider errors are also re-thrown after logging."""

        class AsyncAPIError(Exception):
            pass

        class AsyncErrorCompletions:
            async def create(self, **kwargs):
                raise AsyncAPIError("Async failure")

        class AsyncErrorChat:
            completions = AsyncErrorCompletions()

        class AsyncErrorOpenAI:
            chat = AsyncErrorChat()
            base_url = "https://api.openai.com/v1"

        client = observe(AsyncErrorOpenAI(), agent_id="async-error-agent")

        async def _run():
            await client.chat.completions.create(model="gpt-4o", messages=[])

        with pytest.raises(AsyncAPIError, match="Async failure"):
            asyncio.run(_run())

        audit_logger = object.__getattribute__(client, "_audit_logger")
        error_events = [e for e in audit_logger.get_events()
                        if e.type == "observe.error"]
        assert len(error_events) == 1
