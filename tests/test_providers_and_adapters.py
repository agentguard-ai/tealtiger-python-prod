"""Tests for TealTiger v1.3 — New Providers and Platform Adapters (Python SDK).

Covers:
- Each provider has chat_completion method and pricing constants
- Bedrock adapter translates events correctly
- AgentCore plugin hooks into pre/post lifecycle
- Azure middleware evaluates tool calls
- Cross-platform equivalence (same engine → same decisions)

Requirements: 12.1, 13.8, 14.14
"""

from __future__ import annotations

import asyncio
import pytest

from tealtiger.core.engine.v1_3 import (
    DecisionV13,
    GovernanceRequest,
    TealEngineV13,
    TealEngineV13Options,
)
from tealtiger.clients.new_providers import (
    GROQ_PRICING,
    DEEPSEEK_PRICING,
    TOGETHER_PRICING,
    XAI_PRICING,
    HF_TGI_PRICING,
    ProviderConfig,
    TealGroq,
    TealDeepSeek,
    TealTogether,
    TealXai,
    TealHfTgi,
)
from tealtiger.adapters import (
    BedrockGuardrailAdapter,
    AgentCorePlugin,
    AzureAgentMiddleware,
    PlatformDecision,
)
from tealtiger.adapters.bedrock import (
    BedrockGuardrailEvent,
    BedrockAdapterConfig,
)
from tealtiger.adapters.agentcore import (
    AgentCoreAction,
    AgentCoreAdapterConfig,
)
from tealtiger.adapters.azure import (
    AzureToolCall,
    AzureAgentContext,
    AzureAdapterConfig,
)


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def engine() -> TealEngineV13:
    """Create a basic TealEngineV13 instance for testing."""
    return TealEngineV13(TealEngineV13Options())


# ── Provider Tests ────────────────────────────────────────────────

class TestProviderPricingConstants:
    """Test that each provider has correct pricing constants."""

    def test_groq_pricing_has_models(self):
        assert len(GROQ_PRICING) >= 5
        assert "llama-3.3-70b-versatile" in GROQ_PRICING
        for model, pricing in GROQ_PRICING.items():
            assert "input" in pricing
            assert "output" in pricing
            assert pricing["input"] > 0
            assert pricing["output"] > 0

    def test_deepseek_pricing_has_models(self):
        assert len(DEEPSEEK_PRICING) >= 3
        assert "deepseek-chat" in DEEPSEEK_PRICING
        assert "deepseek-reasoner" in DEEPSEEK_PRICING
        for model, pricing in DEEPSEEK_PRICING.items():
            assert "input" in pricing
            assert "output" in pricing
            assert pricing["input"] > 0
            assert pricing["output"] > 0

    def test_together_pricing_has_models(self):
        assert len(TOGETHER_PRICING) >= 5
        assert "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo" in TOGETHER_PRICING
        for model, pricing in TOGETHER_PRICING.items():
            assert "input" in pricing
            assert "output" in pricing
            assert pricing["input"] > 0
            assert pricing["output"] > 0

    def test_xai_pricing_has_models(self):
        assert len(XAI_PRICING) >= 4
        assert "grok-3" in XAI_PRICING
        assert "grok-3-mini" in XAI_PRICING
        for model, pricing in XAI_PRICING.items():
            assert "input" in pricing
            assert "output" in pricing
            assert pricing["input"] > 0
            assert pricing["output"] > 0

    def test_hf_tgi_pricing_has_models(self):
        assert len(HF_TGI_PRICING) >= 5
        assert "meta-llama/Meta-Llama-3.1-70B-Instruct" in HF_TGI_PRICING
        for model, pricing in HF_TGI_PRICING.items():
            assert "input" in pricing
            assert "output" in pricing
            assert pricing["input"] > 0
            assert pricing["output"] > 0


class TestProviderChatCompletion:
    """Test that each provider has a working chat_completion method."""

    @pytest.mark.asyncio
    async def test_groq_chat_completion(self):
        client = TealGroq(ProviderConfig(api_key="test-key"))
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Hello"}]
        )
        assert "choices" in response
        assert response["choices"][0]["message"]["role"] == "assistant"
        assert "usage" in response
        assert response["model"] == "llama-3.3-70b-versatile"

    @pytest.mark.asyncio
    async def test_deepseek_chat_completion(self):
        client = TealDeepSeek(ProviderConfig(api_key="test-key"))
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Hello"}]
        )
        assert "choices" in response
        assert response["model"] == "deepseek-chat"

    @pytest.mark.asyncio
    async def test_together_chat_completion(self):
        client = TealTogether(ProviderConfig(api_key="test-key"))
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Hello"}]
        )
        assert "choices" in response
        assert response["model"] == "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"

    @pytest.mark.asyncio
    async def test_xai_chat_completion(self):
        client = TealXai(ProviderConfig(api_key="test-key"))
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Hello"}]
        )
        assert "choices" in response
        assert response["model"] == "grok-3"

    @pytest.mark.asyncio
    async def test_hf_tgi_chat_completion(self):
        client = TealHfTgi(ProviderConfig(api_key=""))
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Hello"}]
        )
        assert "choices" in response
        assert response["model"] == "meta-llama/Meta-Llama-3.1-8B-Instruct"

    @pytest.mark.asyncio
    async def test_provider_with_custom_model(self):
        client = TealGroq(ProviderConfig(
            api_key="test-key",
            model="mixtral-8x7b-32768",
        ))
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Hello"}]
        )
        assert response["model"] == "mixtral-8x7b-32768"

    @pytest.mark.asyncio
    async def test_provider_model_override_in_call(self):
        client = TealGroq(ProviderConfig(api_key="test-key"))
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
            model="llama-3.1-8b-instant",
        )
        assert response["model"] == "llama-3.1-8b-instant"


class TestProviderGetConfig:
    """Test that each provider returns its configuration."""

    def test_groq_get_config(self):
        client = TealGroq(ProviderConfig(api_key="test-key"))
        config = client.get_config()
        assert config["provider"] == "groq"
        assert config["api_key"] == "***"
        assert config["base_url"] == "https://api.groq.com/openai/v1"
        assert config["model"] == "llama-3.3-70b-versatile"

    def test_deepseek_get_config(self):
        client = TealDeepSeek(ProviderConfig(api_key="test-key"))
        config = client.get_config()
        assert config["provider"] == "deepseek"
        assert config["base_url"] == "https://api.deepseek.com/v1"

    def test_together_get_config(self):
        client = TealTogether(ProviderConfig(api_key="test-key"))
        config = client.get_config()
        assert config["provider"] == "together"
        assert config["base_url"] == "https://api.together.xyz/v1"

    def test_xai_get_config(self):
        client = TealXai(ProviderConfig(api_key="test-key"))
        config = client.get_config()
        assert config["provider"] == "xai"
        assert config["base_url"] == "https://api.x.ai/v1"

    def test_hf_tgi_get_config(self):
        client = TealHfTgi(ProviderConfig(api_key=""))
        config = client.get_config()
        assert config["provider"] == "hf-tgi"
        assert config["base_url"] == "http://localhost:8080"


# ── Bedrock Adapter Tests ─────────────────────────────────────────

class TestBedrockAdapter:
    """Test Bedrock guardrail adapter translates events correctly."""

    @pytest.mark.asyncio
    async def test_evaluate_guardrail_allow(self, engine: TealEngineV13):
        adapter = BedrockGuardrailAdapter()
        await adapter.initialize(engine)

        event = BedrockGuardrailEvent(
            source="ORCHESTRATION",
            input_text="What is the weather?",
            agent={"name": "test-agent", "id": "agent-1", "alias": "v1", "version": "1.0"},
        )
        response = await adapter.evaluate_guardrail(event)
        assert response.action == "ALLOW"
        assert response.metadata is not None
        assert response.metadata["evaluated_by"] == "tealtiger"

    @pytest.mark.asyncio
    async def test_evaluate_guardrail_with_action_group(self, engine: TealEngineV13):
        adapter = BedrockGuardrailAdapter()
        await adapter.initialize(engine)

        event = BedrockGuardrailEvent(
            source="ORCHESTRATION",
            input_text="Search for documents",
            action_group={
                "name": "search_tool",
                "apiPath": "/search",
                "httpMethod": "GET",
            },
        )
        response = await adapter.evaluate_guardrail(event)
        assert response.action == "ALLOW"

    @pytest.mark.asyncio
    async def test_evaluate_guardrail_knowledge_base(self, engine: TealEngineV13):
        adapter = BedrockGuardrailAdapter()
        await adapter.initialize(engine)

        event = BedrockGuardrailEvent(
            source="KNOWLEDGE_BASE_RESPONSE_GENERATION",
            input_text="RAG response content",
            knowledge_base={"id": "kb-123", "query": "test query"},
        )
        response = await adapter.evaluate_guardrail(event)
        assert response.action == "ALLOW"

    @pytest.mark.asyncio
    async def test_evaluate_generic_interface(self, engine: TealEngineV13):
        adapter = BedrockGuardrailAdapter()
        await adapter.initialize(engine)

        event = BedrockGuardrailEvent(
            source="PRE_PROCESSING",
            input_text="Hello world",
        )
        decision = await adapter.evaluate(event)
        assert isinstance(decision, PlatformDecision)
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_adapter_not_initialized_raises(self):
        adapter = BedrockGuardrailAdapter()
        event = BedrockGuardrailEvent(input_text="test")
        with pytest.raises(RuntimeError, match="not initialized"):
            await adapter.evaluate_guardrail(event)

    def test_platform_property(self):
        adapter = BedrockGuardrailAdapter()
        assert adapter.platform == "bedrock"


# ── AgentCore Plugin Tests ────────────────────────────────────────

class TestAgentCorePlugin:
    """Test AgentCore plugin hooks into pre/post lifecycle."""

    @pytest.mark.asyncio
    async def test_pre_action_tool_call(self, engine: TealEngineV13):
        plugin = AgentCorePlugin()
        await plugin.initialize(engine)

        action = AgentCoreAction(
            action_id="act-1",
            type="tool_call",
            agent_id="agent-1",
            tool_name="search",
            content="search query",
        )
        decision = await plugin.pre_action(action)
        assert decision.allowed is True
        assert decision.action == "proceed"
        assert decision.correlation_id is not None

    @pytest.mark.asyncio
    async def test_pre_action_memory_write(self, engine: TealEngineV13):
        plugin = AgentCorePlugin()
        await plugin.initialize(engine)

        action = AgentCoreAction(
            action_id="act-2",
            type="memory_write",
            agent_id="agent-1",
            memory_scope="session",
            content="remember this",
        )
        decision = await plugin.pre_action(action)
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_pre_action_skips_non_evaluated_types(self, engine: TealEngineV13):
        plugin = AgentCorePlugin()
        await plugin.initialize(engine)

        action = AgentCoreAction(
            action_id="act-3",
            type="planning",
            agent_id="agent-1",
            content="planning step",
        )
        decision = await plugin.pre_action(action)
        # planning is not in default evaluate_action_types
        assert decision.allowed is True
        assert decision.action == "proceed"

    @pytest.mark.asyncio
    async def test_post_action_records_audit(self, engine: TealEngineV13):
        plugin = AgentCorePlugin()
        await plugin.initialize(engine)

        action = AgentCoreAction(
            action_id="act-4",
            type="tool_call",
            agent_id="agent-1",
            tool_name="database_query",
        )
        result = {"rows": 5}
        await plugin.post_action(action, result)

        records = plugin.get_post_action_records()
        assert len(records) == 1
        assert records[0].action.action_id == "act-4"
        assert records[0].result == {"rows": 5}
        assert records[0].correlation_id != ""
        assert records[0].timestamp > 0

    @pytest.mark.asyncio
    async def test_post_action_disabled(self, engine: TealEngineV13):
        config = AgentCoreAdapterConfig(enable_post_action_audit=False)
        plugin = AgentCorePlugin(config)
        await plugin.initialize(engine)

        action = AgentCoreAction(
            action_id="act-5",
            type="tool_call",
            agent_id="agent-1",
        )
        await plugin.post_action(action, None)
        assert len(plugin.get_post_action_records()) == 0

    @pytest.mark.asyncio
    async def test_clear_post_action_records(self, engine: TealEngineV13):
        plugin = AgentCorePlugin()
        await plugin.initialize(engine)

        action = AgentCoreAction(
            action_id="act-6",
            type="tool_call",
            agent_id="agent-1",
        )
        await plugin.post_action(action, None)
        assert len(plugin.get_post_action_records()) == 1

        plugin.clear_post_action_records()
        assert len(plugin.get_post_action_records()) == 0

    @pytest.mark.asyncio
    async def test_evaluate_generic_interface(self, engine: TealEngineV13):
        plugin = AgentCorePlugin()
        await plugin.initialize(engine)

        action = AgentCoreAction(
            action_id="act-7",
            type="tool_call",
            agent_id="agent-1",
            tool_name="search",
        )
        decision = await plugin.evaluate(action)
        assert isinstance(decision, PlatformDecision)
        assert decision.allowed is True

    def test_platform_property(self):
        plugin = AgentCorePlugin()
        assert plugin.platform == "agentcore"


# ── Azure Middleware Tests ────────────────────────────────────────

class TestAzureMiddleware:
    """Test Azure middleware evaluates tool calls."""

    @pytest.mark.asyncio
    async def test_evaluate_tool_call(self, engine: TealEngineV13):
        middleware = AzureAgentMiddleware()
        await middleware.initialize(engine)

        tool_call = AzureToolCall(
            id="call-1",
            function_name="get_weather",
            function_arguments='{"location": "Seattle"}',
        )
        context = AzureAgentContext(
            deployment_name="my-agent",
            thread_id="thread-1",
            model="gpt-4",
        )
        result = await middleware.evaluate_tool_call(tool_call, context)
        assert result.allowed is True
        assert result.action == "allow"
        assert result.correlation_id is not None

    @pytest.mark.asyncio
    async def test_evaluate_tool_call_with_telemetry(self, engine: TealEngineV13):
        middleware = AzureAgentMiddleware(AzureAdapterConfig(enable_telemetry=True))
        await middleware.initialize(engine)

        tool_call = AzureToolCall(
            id="call-2",
            function_name="database_query",
            function_arguments='{"sql": "SELECT * FROM users"}',
        )
        result = await middleware.evaluate_tool_call(tool_call)
        assert result.telemetry is not None
        assert "custom_dimensions" in result.telemetry
        assert result.telemetry["custom_dimensions"]["tealtiger.tool.name"] == "database_query"
        assert result.telemetry["operation_name"] == "TealTiger.Governance.EvaluateToolCall"

    @pytest.mark.asyncio
    async def test_evaluate_tool_call_no_telemetry(self, engine: TealEngineV13):
        middleware = AzureAgentMiddleware(AzureAdapterConfig(enable_telemetry=False))
        await middleware.initialize(engine)

        tool_call = AzureToolCall(
            id="call-3",
            function_name="search",
            function_arguments="{}",
        )
        result = await middleware.evaluate_tool_call(tool_call)
        assert result.telemetry is None

    @pytest.mark.asyncio
    async def test_evaluate_tool_call_invalid_json_arguments(self, engine: TealEngineV13):
        middleware = AzureAgentMiddleware()
        await middleware.initialize(engine)

        tool_call = AzureToolCall(
            id="call-4",
            function_name="raw_tool",
            function_arguments="not valid json",
        )
        # Should not raise — handles invalid JSON gracefully
        result = await middleware.evaluate_tool_call(tool_call)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_evaluate_generic_interface(self, engine: TealEngineV13):
        middleware = AzureAgentMiddleware()
        await middleware.initialize(engine)

        request = {
            "tool_call": AzureToolCall(
                id="call-5",
                function_name="test_tool",
                function_arguments="{}",
            ),
            "context": AzureAgentContext(deployment_name="test"),
        }
        decision = await middleware.evaluate(request)
        assert isinstance(decision, PlatformDecision)
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_adapter_not_initialized_raises(self):
        middleware = AzureAgentMiddleware()
        tool_call = AzureToolCall(
            id="call-6",
            function_name="test",
            function_arguments="{}",
        )
        with pytest.raises(RuntimeError, match="not initialized"):
            await middleware.evaluate_tool_call(tool_call)

    def test_platform_property(self):
        middleware = AzureAgentMiddleware()
        assert middleware.platform == "azure"


# ── Cross-Platform Equivalence Tests ──────────────────────────────

class TestCrossPlatformEquivalence:
    """Test that all adapters produce identical decisions for equivalent inputs.

    Cross-platform guarantee: identical inputs → identical Decisions
    regardless of which platform adapter is used.
    """

    @pytest.mark.asyncio
    async def test_same_engine_same_decisions(self, engine: TealEngineV13):
        """All adapters using the same engine produce equivalent allow decisions."""
        bedrock = BedrockGuardrailAdapter()
        agentcore = AgentCorePlugin()
        azure = AzureAgentMiddleware()

        await bedrock.initialize(engine)
        await agentcore.initialize(engine)
        await azure.initialize(engine)

        # Bedrock evaluation
        bedrock_event = BedrockGuardrailEvent(
            source="ORCHESTRATION",
            input_text="test content",
            action_group={"name": "search", "apiPath": "/search", "httpMethod": "GET"},
        )
        bedrock_decision = await bedrock.evaluate(bedrock_event)

        # AgentCore evaluation
        agentcore_action = AgentCoreAction(
            action_id="act-1",
            type="tool_call",
            agent_id="agent-1",
            tool_name="search",
            content="test content",
        )
        agentcore_decision = await agentcore.evaluate(agentcore_action)

        # Azure evaluation
        azure_tool_call = AzureToolCall(
            id="call-1",
            function_name="search",
            function_arguments='{"query": "test content"}',
        )
        azure_decision = await azure.evaluate({
            "tool_call": azure_tool_call,
            "context": AzureAgentContext(deployment_name="test"),
        })

        # All should produce ALLOW (same engine, no blocking rules)
        assert bedrock_decision.allowed is True
        assert agentcore_decision.allowed is True
        assert azure_decision.allowed is True

    @pytest.mark.asyncio
    async def test_same_engine_same_deny_decisions(self):
        """All adapters using the same engine with FREEZE rules produce equivalent deny decisions."""
        from tealtiger.core.engine.v1_3 import FreezeRule, PolicyMatcher

        # Engine with a FREEZE rule blocking all TOOL_INVOKE actions
        engine = TealEngineV13(TealEngineV13Options(
            freeze_rules=[
                FreezeRule(
                    id="freeze-all-tools",
                    match=PolicyMatcher(action_class="TOOL_INVOKE"),
                    reason="All tool invocations frozen",
                    created_at=1000,
                    created_by="admin",
                )
            ]
        ))

        bedrock = BedrockGuardrailAdapter()
        agentcore = AgentCorePlugin()
        azure = AzureAgentMiddleware()

        await bedrock.initialize(engine)
        await agentcore.initialize(engine)
        await azure.initialize(engine)

        # Bedrock — tool invocation
        bedrock_event = BedrockGuardrailEvent(
            source="ORCHESTRATION",
            input_text="invoke tool",
            action_group={"name": "search", "apiPath": "/search", "httpMethod": "GET"},
        )
        bedrock_decision = await bedrock.evaluate(bedrock_event)

        # AgentCore — tool call
        agentcore_action = AgentCoreAction(
            action_id="act-1",
            type="tool_call",
            agent_id="agent-1",
            tool_name="search",
            content="invoke tool",
        )
        agentcore_decision = await agentcore.evaluate(agentcore_action)

        # Azure — tool call
        azure_tool_call = AzureToolCall(
            id="call-1",
            function_name="search",
            function_arguments='{"query": "invoke tool"}',
        )
        azure_decision = await azure.evaluate({
            "tool_call": azure_tool_call,
            "context": AzureAgentContext(deployment_name="test"),
        })

        # All should produce DENY (FREEZE rule blocks TOOL_INVOKE)
        assert bedrock_decision.allowed is False
        assert agentcore_decision.allowed is False
        assert azure_decision.allowed is False

        # All should have FREEZE_BLOCK reason code
        assert "FREEZE_BLOCK" in bedrock_decision.reason_codes
        assert "FREEZE_BLOCK" in agentcore_decision.reason_codes
        assert "FREEZE_BLOCK" in azure_decision.reason_codes
