"""
Property-based tests for TealAzureOpenAI client.

These tests validate universal properties that should hold across all inputs.
"""

import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from tealtiger.clients.teal_azure_openai import (
    TealAzureOpenAI,
    TealAzureOpenAIConfig,
    AzureChatCompletionResponse,
)
from tealtiger.guardrails.engine import GuardrailEngine, GuardrailEngineResult
from tealtiger.cost.tracker import CostTracker, CostTrackerConfig
from tealtiger.cost.budget import BudgetManager, BudgetEnforcementResult
from tealtiger.cost.storage import InMemoryCostStorage
from tealtiger.cost.types import TokenUsage, BudgetConfig


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
def azure_deployments(draw):
    """Generate Azure deployment names."""
    return draw(st.sampled_from([
        'gpt-4-deployment',
        'gpt-4-turbo-deployment',
        'gpt-35-turbo-deployment',
        'my-gpt4-deployment',
        'production-gpt-4',
        'gpt-3.5-turbo-16k-deployment',
    ]))


# Mock Azure OpenAI response
def create_mock_response(deployment: str, prompt_tokens: int, completion_tokens: int):
    """Create a mock Azure OpenAI response."""
    response = MagicMock()
    response.id = 'chatcmpl-test123'
    response.object = 'chat.completion'
    response.created = int(datetime.now().timestamp())
    response.model = deployment
    
    choice = MagicMock()
    choice.index = 0
    choice.message.role = 'assistant'
    choice.message.content = 'This is a test response from Azure OpenAI.'
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
    deployment=azure_deployments(),
)
async def test_property_37_azure_deployment_to_model_mapping(deployment):
    """
    Feature: python-sdk-feature-parity, Property 37: Azure deployment to model mapping
    **Validates: Requirements 6.5**
    
    For any Azure deployment name, the mapping function should return a valid 
    OpenAI model name for pricing.
    """
    # Create guarded client
    config = TealAzureOpenAIConfig(
        api_key='test-key',
        endpoint='https://test.openai.azure.com',
        agent_id='test-agent',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealAzureOpenAI(config)
    
    # Property: Mapping should return a valid model name
    model = client.map_deployment_to_model(deployment)
    assert model is not None, "Mapping should return a model name"
    assert isinstance(model, str), "Model name should be a string"
    assert len(model) > 0, "Model name should not be empty"
    
    # Property: Mapped model should be a known OpenAI model
    known_models = [
        'gpt-4', 'gpt-4-32k', 'gpt-4-turbo',
        'gpt-3.5-turbo', 'gpt-3.5-turbo-16k'
    ]
    assert model in known_models, f"Mapped model '{model}' should be a known OpenAI model"


@pytest.mark.asyncio
@settings(max_examples=20, deadline=None)
@given(
    messages=chat_messages(),
    deployment=azure_deployments(),
)
async def test_property_38_azure_input_guardrail_execution(messages, deployment):
    """
    Feature: python-sdk-feature-parity, Property 38: Azure input guardrail execution
    **Validates: Requirements 6.3**
    
    For any Azure request with guardrails enabled, the guardrail engine should 
    execute on the user messages before the API call.
    """
    # Create mock guardrail engine
    engine = MagicMock(spec=GuardrailEngine)
    engine.execute = AsyncMock(return_value=create_passing_guardrail_result())
    
    # Create guarded client with guardrails enabled
    config = TealAzureOpenAIConfig(
        api_key='test-key',
        endpoint='https://test.openai.azure.com',
        agent_id='test-agent',
        enable_guardrails=True,
        enable_cost_tracking=False,
        guardrail_engine=engine
    )
    client = TealAzureOpenAI(config)
    
    # Mock Azure OpenAI API call
    mock_response = create_mock_response(deployment, 50, 10)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        # Make request
        response = await client.chat.completions.create(
            deployment=deployment,
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
    deployment=azure_deployments(),
)
async def test_property_39_azure_cost_estimation_with_deployment_mapping(messages, deployment):
    """
    Feature: python-sdk-feature-parity, Property 39: Azure cost estimation with deployment mapping
    **Validates: Requirements 6.6**
    
    For any Azure request with cost tracking enabled, cost estimation should use 
    the mapped model name for pricing.
    """
    # Create cost tracker
    tracker = CostTracker(CostTrackerConfig(enabled=True))
    
    # Track the model used for estimation
    estimated_model = None
    original_estimate = tracker.estimate_cost
    
    def track_estimate(model, *args, **kwargs):
        nonlocal estimated_model
        estimated_model = model
        return original_estimate(model, *args, **kwargs)
    
    tracker.estimate_cost = track_estimate
    
    # Create guarded client
    config = TealAzureOpenAIConfig(
        api_key='test-key',
        endpoint='https://test.openai.azure.com',
        agent_id='test-agent',
        enable_guardrails=False,
        enable_cost_tracking=True,
        cost_tracker=tracker
    )
    client = TealAzureOpenAI(config)
    
    # Mock Azure OpenAI API call
    mock_response = create_mock_response(deployment, 50, 10)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        # Make request
        response = await client.chat.completions.create(
            deployment=deployment,
            messages=messages
        )
        
        # Property: Cost estimation should use mapped model name
        assert estimated_model is not None, "Cost estimation should have been called"
        
        # Property: Estimated model should match the mapped model
        expected_model = client.map_deployment_to_model(deployment)
        assert estimated_model == expected_model, \
            f"Cost estimation should use mapped model '{expected_model}', got '{estimated_model}'"


@pytest.mark.asyncio
@settings(max_examples=20, deadline=None)
@given(
    messages=chat_messages(),
    deployment=azure_deployments(),
)
async def test_property_40_azure_budget_verification(messages, deployment):
    """
    Feature: python-sdk-feature-parity, Property 40: Azure budget verification
    **Validates: Requirements 6.7**
    
    For any Azure request with budget checking enabled, budget verification should 
    occur before the API call.
    """
    # Create cost components
    storage = InMemoryCostStorage()
    tracker = CostTracker(CostTrackerConfig(enabled=True))
    budget_manager = BudgetManager(storage)
    
    # Create a budget with high limit (won't block)
    budget_manager.create_budget(
        name='test-budget',
        limit=100.0,
        period='total',
        alert_thresholds=[50, 75, 90]
    )
    
    # Track if budget check was called
    check_called = False
    original_check = budget_manager.check_budget
    
    async def track_check(*args, **kwargs):
        nonlocal check_called
        check_called = True
        return await original_check(*args, **kwargs)
    
    budget_manager.check_budget = track_check
    
    # Create guarded client
    config = TealAzureOpenAIConfig(
        api_key='test-key',
        endpoint='https://test.openai.azure.com',
        agent_id='test-agent',
        enable_guardrails=False,
        enable_cost_tracking=True,
        cost_tracker=tracker,
        budget_manager=budget_manager
    )
    client = TealAzureOpenAI(config)
    
    # Mock Azure OpenAI API call
    mock_response = create_mock_response(deployment, 50, 10)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        # Make request
        response = await client.chat.completions.create(
            deployment=deployment,
            messages=messages
        )
        
        # Property: Budget check should have been called
        assert check_called, "Budget verification should occur before API call"
        
        # Property: Response should include budget check result
        assert response.security is not None, "Response should include security metadata"
        assert response.security.budget_check is not None, "Security should include budget check"


@pytest.mark.asyncio
@settings(max_examples=20, deadline=None)
@given(
    messages=chat_messages(),
    deployment=azure_deployments(),
)
async def test_property_41_azure_budget_blocking(messages, deployment):
    """
    Feature: python-sdk-feature-parity, Property 41: Azure budget blocking
    **Validates: Requirements 6.8**
    
    For any Azure request where the budget check fails, the request should be 
    blocked and raise an error.
    """
    # Create cost components
    storage = InMemoryCostStorage()
    tracker = CostTracker(CostTrackerConfig(enabled=True))
    budget_manager = BudgetManager(storage)
    
    # Create a budget with very low limit (will block)
    budget_manager.create_budget(
        name='test-budget',
        limit=0.0001,  # Very low limit
        period='total',
        alert_thresholds=[50, 75, 90]
    )
    
    # Create guarded client
    config = TealAzureOpenAIConfig(
        api_key='test-key',
        endpoint='https://test.openai.azure.com',
        agent_id='test-agent',
        enable_guardrails=False,
        enable_cost_tracking=True,
        cost_tracker=tracker,
        budget_manager=budget_manager
    )
    client = TealAzureOpenAI(config)
    
    # Mock Azure OpenAI API call (should not be reached)
    mock_response = create_mock_response(deployment, 50, 10)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)) as mock_create:
        # Property: Request should be blocked with ValueError
        with pytest.raises(ValueError, match="Budget exceeded"):
            await client.chat.completions.create(
                deployment=deployment,
                messages=messages
            )
        
        # Property: Azure OpenAI API should NOT be called
        assert not mock_create.called, "Azure OpenAI API should not be called when budget is exceeded"


@pytest.mark.asyncio
@settings(max_examples=20, deadline=None)
@given(
    messages=chat_messages(),
    deployment=azure_deployments(),
)
async def test_property_42_azure_output_guardrail_execution(messages, deployment):
    """
    Feature: python-sdk-feature-parity, Property 42: Azure output guardrail execution
    **Validates: Requirements 6.10**
    
    For any Azure response with guardrails enabled, the guardrail engine should 
    execute on the assistant message.
    """
    # Create mock guardrail engine
    engine = MagicMock(spec=GuardrailEngine)
    engine.execute = AsyncMock(return_value=create_passing_guardrail_result())
    
    # Create guarded client with guardrails enabled
    config = TealAzureOpenAIConfig(
        api_key='test-key',
        endpoint='https://test.openai.azure.com',
        agent_id='test-agent',
        enable_guardrails=True,
        enable_cost_tracking=False,
        guardrail_engine=engine
    )
    client = TealAzureOpenAI(config)
    
    # Mock Azure OpenAI API call
    mock_response = create_mock_response(deployment, 50, 10)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        # Make request
        response = await client.chat.completions.create(
            deployment=deployment,
            messages=messages
        )
        
        # Property: Guardrail engine should have been called twice (input + output)
        assert engine.execute.call_count == 2, \
            "Guardrail engine should be called for both input and output"
        
        # Property: Response should include guardrail result
        assert response.security is not None, "Response should include security metadata"
        assert response.security.guardrail_result is not None, "Security should include guardrail result"


@pytest.mark.asyncio
@settings(max_examples=20, deadline=None)
@given(
    messages=chat_messages(),
    deployment=azure_deployments(),
)
async def test_property_43_azure_actual_cost_calculation(messages, deployment):
    """
    Feature: python-sdk-feature-parity, Property 43: Azure actual cost calculation
    **Validates: Requirements 6.12**
    
    For any Azure response with cost tracking enabled, actual cost calculation 
    should use the mapped model name.
    """
    # Create cost tracker
    tracker = CostTracker(CostTrackerConfig(enabled=True))
    
    # Track the model used for actual cost calculation
    calculated_model = None
    original_calculate = tracker.calculate_actual_cost
    
    def track_calculate(request_id, agent_id, model, *args, **kwargs):
        nonlocal calculated_model
        calculated_model = model
        return original_calculate(request_id, agent_id, model, *args, **kwargs)
    
    tracker.calculate_actual_cost = track_calculate
    
    # Create guarded client
    config = TealAzureOpenAIConfig(
        api_key='test-key',
        endpoint='https://test.openai.azure.com',
        agent_id='test-agent',
        enable_guardrails=False,
        enable_cost_tracking=True,
        cost_tracker=tracker
    )
    client = TealAzureOpenAI(config)
    
    # Mock Azure OpenAI API call
    mock_response = create_mock_response(deployment, 50, 10)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        # Make request
        response = await client.chat.completions.create(
            deployment=deployment,
            messages=messages
        )
        
        # Property: Actual cost calculation should use mapped model name
        assert calculated_model is not None, "Actual cost calculation should have been called"
        
        # Property: Calculated model should match the mapped model
        expected_model = client.map_deployment_to_model(deployment)
        assert calculated_model == expected_model, \
            f"Actual cost calculation should use mapped model '{expected_model}', got '{calculated_model}'"
        
        # Property: Response should include cost record
        assert response.security is not None, "Response should include security metadata"
        assert response.security.cost_record is not None, "Security should include cost record"

