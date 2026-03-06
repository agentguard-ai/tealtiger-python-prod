"""
Property-based tests for TealOpenAI client.

These tests validate universal properties that should hold across all inputs.
"""

import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from tealtiger.clients.teal_openai import (
    TealOpenAI,
    TealOpenAIConfig,
    ChatCompletionResponse,
)
from tealtiger.guardrails.engine import GuardrailEngine, GuardrailEngineResult
from tealtiger.cost.tracker import CostTracker, CostTrackerConfig
from tealtiger.cost.budget import BudgetManager
from tealtiger.cost.storage import InMemoryCostStorage
from tealtiger.cost.types import TokenUsage


# Test strategies
@st.composite
def chat_messages(draw):
    """Generate chat messages."""
    num_messages = draw(st.integers(min_value=1, max_value=5))
    messages = []
    for _ in range(num_messages):
        role = draw(st.sampled_from(['system', 'user', 'assistant']))
        content = draw(st.text(min_size=1, max_size=200))
        messages.append({'role': role, 'content': content})
    return messages


@st.composite
def openai_models(draw):
    """Generate OpenAI model names."""
    return draw(st.sampled_from([
        'gpt-4', 'gpt-4-turbo', 'gpt-3.5-turbo', 'gpt-4o', 'gpt-4o-mini'
    ]))


# Mock OpenAI response
def create_mock_response(model: str, prompt_tokens: int, completion_tokens: int):
    """Create a mock OpenAI response."""
    response = MagicMock()
    response.id = 'chatcmpl-test123'
    response.object = 'chat.completion'
    response.created = int(datetime.now().timestamp())
    response.model = model
    
    choice = MagicMock()
    choice.index = 0
    choice.message.role = 'assistant'
    choice.message.content = 'This is a test response.'
    choice.finish_reason = 'stop'
    response.choices = [choice]
    
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    response.usage.total_tokens = prompt_tokens + completion_tokens
    
    return response


def create_passing_guardrail_result():
    """Create a passing guardrail result."""
    return GuardrailEngineResult(
        passed=True,
        results=[],
        execution_time=10.0,
        guardrails_executed=1,
        max_risk_score=0
    )


def create_failing_guardrail_result(risk_score: int = 90):
    """Create a failing guardrail result."""
    return GuardrailEngineResult(
        passed=False,
        results=[{'name': 'test-guardrail', 'passed': False, 'risk_score': risk_score}],
        execution_time=10.0,
        guardrails_executed=1,
        max_risk_score=risk_score,
        failed_guardrails=['test-guardrail']
    )


@pytest.mark.asyncio
@settings(max_examples=20, deadline=None)
@given(
    messages=chat_messages(),
    model=openai_models(),
)
async def test_property_17_input_guardrail_execution(messages, model):
    """
    Feature: python-sdk-feature-parity, Property 17: Input guardrail execution
    **Validates: Requirements 4.2**
    
    For any request with guardrails enabled, the guardrail engine should execute 
    on the user messages before the API call.
    """
    # Create mock guardrail engine
    engine = MagicMock(spec=GuardrailEngine)
    engine.execute = AsyncMock(return_value=create_passing_guardrail_result())
    
    # Create guarded client with guardrails enabled
    config = TealOpenAIConfig(
        api_key='test-key',
        agent_id='test-agent',
        enable_guardrails=True,
        enable_cost_tracking=False,
        guardrail_engine=engine
    )
    client = TealOpenAI(config)
    
    # Mock OpenAI API call
    mock_response = create_mock_response(model, 50, 10)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        # Make request
        response = await client.chat.create(
            model=model,
            messages=messages
        )
        
        # Property: Guardrail engine should have been called
        assert engine.execute.called, "Guardrail engine should be executed"
        
        # Property: Response should include guardrail result
        assert response.security is not None, "Response should include security metadata"
        assert response.security.guardrail_result is not None, "Security should include guardrail result"


@pytest.mark.asyncio
@settings(max_examples=20, deadline=None)
@given(
    messages=chat_messages(),
    model=openai_models(),
    risk_score=st.integers(min_value=80, max_value=100),
)
async def test_property_18_input_guardrail_blocking(messages, model, risk_score):
    """
    Feature: python-sdk-feature-parity, Property 18: Input guardrail blocking
    **Validates: Requirements 4.3**
    
    For any request where input guardrails fail, the request should be blocked 
    and raise an error before making the API call.
    """
    # Create mock guardrail engine that fails
    engine = MagicMock(spec=GuardrailEngine)
    engine.execute = AsyncMock(return_value=create_failing_guardrail_result(risk_score))
    
    # Create guarded client
    config = TealOpenAIConfig(
        api_key='test-key',
        agent_id='test-agent',
        enable_guardrails=True,
        enable_cost_tracking=False,
        guardrail_engine=engine
    )
    client = TealOpenAI(config)
    
    # Mock OpenAI API call (should not be reached)
    mock_response = create_mock_response(model, 50, 10)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)) as mock_create:
        # Property: Request should be blocked with ValueError
        with pytest.raises(ValueError, match="Guardrail check failed"):
            await client.chat.create(
                model=model,
                messages=messages
            )
        
        # Property: OpenAI API should NOT be called
        assert not mock_create.called, "OpenAI API should not be called when guardrails fail"


@pytest.mark.asyncio
@settings(max_examples=20, deadline=None)
@given(
    messages=chat_messages(),
    model=openai_models(),
)
async def test_property_19_cost_estimation_before_api_call(messages, model):
    """
    Feature: python-sdk-feature-parity, Property 19: Cost estimation before API call
    **Validates: Requirements 4.4**
    
    For any request with cost tracking enabled, cost estimation should occur 
    before the API call.
    """
    # Create cost tracker
    tracker = CostTracker(CostTrackerConfig(enabled=True))
    
    # Track if estimate_cost was called
    estimate_called = False
    original_estimate = tracker.estimate_cost
    
    def track_estimate(*args, **kwargs):
        nonlocal estimate_called
        estimate_called = True
        return original_estimate(*args, **kwargs)
    
    tracker.estimate_cost = track_estimate
    
    # Create guarded client
    config = TealOpenAIConfig(
        api_key='test-key',
        agent_id='test-agent',
        enable_guardrails=False,
        enable_cost_tracking=True,
        cost_tracker=tracker
    )
    client = TealOpenAI(config)
    
    # Mock OpenAI API call
    mock_response = create_mock_response(model, 50, 10)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        # Make request
        response = await client.chat.create(
            model=model,
            messages=messages
        )
        
        # Property: Cost estimation should have been called
        assert estimate_called, "Cost estimation should occur before API call"
        
        # Property: Response should include cost record
        assert response.security is not None, "Response should include security metadata"
        assert response.security.cost_record is not None, "Security should include cost record"

