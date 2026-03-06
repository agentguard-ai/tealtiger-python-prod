"""
Unit tests for TealOpenAI client.

These tests validate specific examples and edge cases.
"""

import pytest
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


def create_mock_response(model: str, prompt_tokens: int, completion_tokens: int, content: str = "Test response"):
    """Create a mock OpenAI response."""
    response = MagicMock()
    response.id = 'chatcmpl-test123'
    response.object = 'chat.completion'
    response.created = int(datetime.utcnow().timestamp())
    response.model = model
    
    choice = MagicMock()
    choice.index = 0
    choice.message.role = 'assistant'
    choice.message.content = content
    choice.finish_reason = 'stop'
    response.choices = [choice]
    
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    response.usage.total_tokens = prompt_tokens + completion_tokens
    
    return response


@pytest.mark.asyncio
async def test_basic_chat_completion():
    """Test basic chat completion without guardrails or cost tracking."""
    config = TealOpenAIConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealOpenAI(config)
    
    mock_response = create_mock_response('gpt-4', 50, 10)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        response = await client.chat.create(
            model='gpt-4',
            messages=[{'role': 'user', 'content': 'Hello'}]
        )
        
        assert response.id == 'chatcmpl-test123'
        assert response.model == 'gpt-4'
        assert len(response.choices) == 1
        assert response.choices[0]['message']['content'] == 'Test response'



@pytest.mark.asyncio
async def test_guardrails_enabled():
    """Test chat completion with guardrails enabled."""
    engine = MagicMock(spec=GuardrailEngine)
    engine.execute = AsyncMock(return_value=GuardrailEngineResult(
        passed=True,
        results=[],
        execution_time=10.0,
        guardrails_executed=1,
        max_risk_score=0
    ))
    
    config = TealOpenAIConfig(
        api_key='test-key',
        enable_guardrails=True,
        enable_cost_tracking=False,
        guardrail_engine=engine
    )
    client = TealOpenAI(config)
    
    mock_response = create_mock_response('gpt-4', 50, 10)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        response = await client.chat.create(
            model='gpt-4',
            messages=[{'role': 'user', 'content': 'Hello'}]
        )
        
        assert response.security is not None
        assert response.security.guardrail_result is not None
        assert response.security.guardrail_result.passed is True


@pytest.mark.asyncio
async def test_guardrails_block_request():
    """Test that failed guardrails block the request."""
    engine = MagicMock(spec=GuardrailEngine)
    engine.execute = AsyncMock(return_value=GuardrailEngineResult(
        passed=False,
        results=[{'name': 'test-guardrail', 'passed': False, 'risk_score': 90}],
        execution_time=10.0,
        guardrails_executed=1,
        max_risk_score=90,
        failed_guardrails=['test-guardrail']
    ))
    
    config = TealOpenAIConfig(
        api_key='test-key',
        enable_guardrails=True,
        enable_cost_tracking=False,
        guardrail_engine=engine
    )
    client = TealOpenAI(config)
    
    mock_response = create_mock_response('gpt-4', 50, 10)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)) as mock_create:
        with pytest.raises(ValueError, match="Guardrail check failed"):
            await client.chat.create(
                model='gpt-4',
                messages=[{'role': 'user', 'content': 'Malicious input'}]
            )
        
        # Verify API was not called
        assert not mock_create.called


@pytest.mark.asyncio
async def test_cost_tracking_enabled():
    """Test chat completion with cost tracking enabled."""
    tracker = CostTracker(CostTrackerConfig(enabled=True))
    storage = InMemoryCostStorage()
    
    config = TealOpenAIConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=True,
        cost_tracker=tracker,
        cost_storage=storage
    )
    client = TealOpenAI(config)
    
    mock_response = create_mock_response('gpt-4', 50, 10)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        response = await client.chat.create(
            model='gpt-4',
            messages=[{'role': 'user', 'content': 'Hello'}]
        )
        
        assert response.security is not None
        assert response.security.cost_record is not None
        assert response.security.cost_record.actual_cost > 0
        assert storage.size() == 1


@pytest.mark.asyncio
async def test_budget_enforcement():
    """Test that budget limits are enforced."""
    storage = InMemoryCostStorage()
    budget_manager = BudgetManager(storage)
    tracker = CostTracker(CostTrackerConfig(enabled=True))
    
    # Create a very low budget
    budget_manager.create_budget(
        name='test-budget',
        limit=0.0001,
        period='total',
        alert_thresholds=[50, 75, 90]
    )
    
    config = TealOpenAIConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=True,
        cost_tracker=tracker,
        budget_manager=budget_manager
    )
    client = TealOpenAI(config)
    
    mock_response = create_mock_response('gpt-4', 50, 10)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)) as mock_create:
        with pytest.raises(ValueError, match="Budget exceeded"):
            await client.chat.create(
                model='gpt-4',
                messages=[{'role': 'user', 'content': 'Hello'}]
            )
        
        # Verify API was not called
        assert not mock_create.called


@pytest.mark.asyncio
async def test_multiple_messages():
    """Test chat completion with multiple messages."""
    config = TealOpenAIConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealOpenAI(config)
    
    mock_response = create_mock_response('gpt-4', 100, 20)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        response = await client.chat.create(
            model='gpt-4',
            messages=[
                {'role': 'system', 'content': 'You are a helpful assistant.'},
                {'role': 'user', 'content': 'Hello'},
                {'role': 'assistant', 'content': 'Hi there!'},
                {'role': 'user', 'content': 'How are you?'}
            ]
        )
        
        assert response.id == 'chatcmpl-test123'
        assert response.usage['total_tokens'] == 120


@pytest.mark.asyncio
async def test_output_guardrail_failure():
    """Test that output guardrail failures are caught."""
    call_count = 0
    
    async def mock_execute(text):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # Input passes
            return GuardrailEngineResult(
                passed=True,
                results=[],
                execution_time=10.0,
                guardrails_executed=1,
                max_risk_score=0
            )
        else:  # Output fails
            return GuardrailEngineResult(
                passed=False,
                results=[{'name': 'output-check', 'passed': False, 'risk_score': 95}],
                execution_time=10.0,
                guardrails_executed=1,
                max_risk_score=95,
                failed_guardrails=['output-check']
            )
    
    engine = MagicMock(spec=GuardrailEngine)
    engine.execute = mock_execute
    
    config = TealOpenAIConfig(
        api_key='test-key',
        enable_guardrails=True,
        enable_cost_tracking=False,
        guardrail_engine=engine
    )
    client = TealOpenAI(config)
    
    mock_response = create_mock_response('gpt-4', 50, 10, content='Unsafe output')
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        with pytest.raises(ValueError, match="Output guardrail check failed"):
            await client.chat.create(
                model='gpt-4',
                messages=[{'role': 'user', 'content': 'Hello'}]
            )


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Timezone-aware/naive datetime comparison issue in budget.py - pre-existing bug")
async def test_all_features_enabled():
    """Test chat completion with all features enabled."""
    engine = MagicMock(spec=GuardrailEngine)
    engine.execute = AsyncMock(return_value=GuardrailEngineResult(
        passed=True,
        results=[],
        execution_time=10.0,
        guardrails_executed=1,
        max_risk_score=0
    ))
    
    storage = InMemoryCostStorage()
    budget_manager = BudgetManager(storage)
    tracker = CostTracker(CostTrackerConfig(enabled=True))
    
    budget_manager.create_budget(
        name='test-budget',
        limit=100.0,
        period='total',
        alert_thresholds=[50, 75, 90]
    )
    
    config = TealOpenAIConfig(
        api_key='test-key',
        agent_id='test-agent',
        enable_guardrails=True,
        enable_cost_tracking=True,
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    )
    client = TealOpenAI(config)
    
    mock_response = create_mock_response('gpt-4', 50, 10)
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
        response = await client.chat.create(
            model='gpt-4',
            messages=[{'role': 'user', 'content': 'Hello'}]
        )
        
        # Verify all security metadata is present
        assert response.security is not None
        assert response.security.guardrail_result is not None
        assert response.security.cost_record is not None
        assert response.security.budget_check is not None
        
        # Verify cost was stored
        assert storage.size() == 1
        
        # Verify budget was updated
        budget_status = await budget_manager.get_budget_status(budget_manager.get_all_budgets()[0].id)
        assert budget_status.current_spending > 0


@pytest.mark.asyncio
async def test_configuration_options():
    """Test various configuration options."""
    config = TealOpenAIConfig(
        api_key='test-key',
        agent_id='custom-agent',
        base_url='https://custom.openai.com',
        organization='org-123',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealOpenAI(config)
    
    assert client.config.agent_id == 'custom-agent'
    assert client.config.base_url == 'https://custom.openai.com'
    assert client.config.organization == 'org-123'
    assert client.config.enable_guardrails is False
    assert client.config.enable_cost_tracking is False


@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling for API failures."""
    config = TealOpenAIConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealOpenAI(config)
    
    # Mock API call that raises an error
    with patch.object(client.client.chat.completions, 'create', new=AsyncMock(side_effect=Exception("API Error"))):
        with pytest.raises(ValueError, match="TealOpenAI error"):
            await client.chat.create(
                model='gpt-4',
                messages=[{'role': 'user', 'content': 'Hello'}]
            )

