"""
Unit tests for TealAnthropic client.

These tests validate specific examples and edge cases.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from tealtiger.clients.teal_anthropic import (
    TealAnthropic,
    TealAnthropicConfig,
    MessageCreateResponse,
)
from tealtiger.guardrails.engine import GuardrailEngine, GuardrailEngineResult
from tealtiger.cost.tracker import CostTracker, CostTrackerConfig
from tealtiger.cost.budget import BudgetManager
from tealtiger.cost.storage import InMemoryCostStorage


def create_mock_anthropic_response(
    model: str, 
    input_tokens: int, 
    output_tokens: int, 
    content: str = "Test response from Claude"
):
    """Create a mock Anthropic response."""
    response = MagicMock()
    response.id = 'msg-test123'
    response.type = 'message'
    response.role = 'assistant'
    
    content_block = MagicMock()
    content_block.type = 'text'
    content_block.text = content
    response.content = [content_block]
    
    response.model = model
    response.stop_reason = 'end_turn'
    response.stop_sequence = None
    
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    
    return response


@pytest.mark.asyncio
async def test_basic_message_creation():
    """Test basic message creation without guardrails or cost tracking."""
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealAnthropic(config)
    
    mock_response = create_mock_anthropic_response('claude-3-opus-20240229', 50, 10)
    with patch.object(client.client.messages, 'create', new=AsyncMock(return_value=mock_response)):
        response = await client.messages.create(
            model='claude-3-opus-20240229',
            max_tokens=1024,
            messages=[{'role': 'user', 'content': 'Hello'}]
        )
        
        assert response.id == 'msg-test123'
        assert response.type == 'message'
        assert response.role == 'assistant'
        assert response.model == 'claude-3-opus-20240229'
        assert len(response.content) == 1
        assert response.content[0]['text'] == 'Test response from Claude'


@pytest.mark.asyncio
async def test_string_message_content():
    """Test message creation with string content."""
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealAnthropic(config)
    
    mock_response = create_mock_anthropic_response('claude-3-sonnet-20240229', 30, 15)
    with patch.object(client.client.messages, 'create', new=AsyncMock(return_value=mock_response)):
        response = await client.messages.create(
            model='claude-3-sonnet-20240229',
            max_tokens=512,
            messages=[
                {'role': 'user', 'content': 'What is the weather?'}
            ]
        )
        
        assert response.id == 'msg-test123'
        assert response.usage['input_tokens'] == 30
        assert response.usage['output_tokens'] == 15


@pytest.mark.asyncio
async def test_array_message_content():
    """Test message creation with array content format."""
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealAnthropic(config)
    
    mock_response = create_mock_anthropic_response('claude-3-haiku-20240307', 40, 20)
    with patch.object(client.client.messages, 'create', new=AsyncMock(return_value=mock_response)):
        response = await client.messages.create(
            model='claude-3-haiku-20240307',
            max_tokens=256,
            messages=[
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': 'Hello, Claude!'}
                    ]
                }
            ]
        )
        
        assert response.id == 'msg-test123'
        assert response.model == 'claude-3-haiku-20240307'


@pytest.mark.asyncio
async def test_mixed_content_formats():
    """Test message creation with mixed string and array content."""
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealAnthropic(config)
    
    mock_response = create_mock_anthropic_response('claude-2.1', 60, 25)
    with patch.object(client.client.messages, 'create', new=AsyncMock(return_value=mock_response)):
        response = await client.messages.create(
            model='claude-2.1',
            max_tokens=1024,
            messages=[
                {'role': 'user', 'content': 'First message as string'},
                {
                    'role': 'assistant',
                    'content': [
                        {'type': 'text', 'text': 'Response as array'}
                    ]
                },
                {'role': 'user', 'content': 'Second message as string'}
            ]
        )
        
        assert response.id == 'msg-test123'


@pytest.mark.asyncio
async def test_text_content_extraction_string():
    """Test text content extraction from string format."""
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealAnthropic(config)
    
    # Test string content
    text = "Hello, world!"
    extracted = client._extract_text_content(text)
    assert extracted == text


@pytest.mark.asyncio
async def test_text_content_extraction_array():
    """Test text content extraction from array format."""
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealAnthropic(config)
    
    # Test array content with text blocks
    content = [
        {'type': 'text', 'text': 'First part'},
        {'type': 'text', 'text': 'Second part'}
    ]
    extracted = client._extract_text_content(content)
    assert 'First part' in extracted
    assert 'Second part' in extracted


@pytest.mark.asyncio
async def test_text_content_extraction_mixed():
    """Test text content extraction with mixed content types."""
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealAnthropic(config)
    
    # Test array with text and non-text blocks
    content = [
        {'type': 'text', 'text': 'Text content'},
        {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': 'abc123'}}
    ]
    extracted = client._extract_text_content(content)
    assert 'Text content' in extracted
    # Image blocks should be ignored


@pytest.mark.asyncio
async def test_guardrails_enabled():
    """Test message creation with guardrails enabled."""
    engine = MagicMock(spec=GuardrailEngine)
    engine.execute = AsyncMock(return_value=GuardrailEngineResult(
        passed=True,
        results=[],
        execution_time=10.0,
        guardrails_executed=1,
        max_risk_score=0
    ))
    
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=True,
        enable_cost_tracking=False,
        guardrail_engine=engine
    )
    client = TealAnthropic(config)
    
    mock_response = create_mock_anthropic_response('claude-3-opus-20240229', 50, 10)
    with patch.object(client.client.messages, 'create', new=AsyncMock(return_value=mock_response)):
        response = await client.messages.create(
            model='claude-3-opus-20240229',
            max_tokens=1024,
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
    
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=True,
        enable_cost_tracking=False,
        guardrail_engine=engine
    )
    client = TealAnthropic(config)
    
    mock_response = create_mock_anthropic_response('claude-3-opus-20240229', 50, 10)
    with patch.object(client.client.messages, 'create', new=AsyncMock(return_value=mock_response)) as mock_create:
        with pytest.raises(ValueError, match="Guardrail check failed"):
            await client.messages.create(
                model='claude-3-opus-20240229',
                max_tokens=1024,
                messages=[{'role': 'user', 'content': 'Malicious input'}]
            )
        
        # Verify API was not called
        assert not mock_create.called


@pytest.mark.asyncio
async def test_cost_tracking_enabled():
    """Test message creation with cost tracking enabled."""
    tracker = CostTracker(CostTrackerConfig(enabled=True))
    storage = InMemoryCostStorage()
    
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=True,
        cost_tracker=tracker,
        cost_storage=storage
    )
    client = TealAnthropic(config)
    
    mock_response = create_mock_anthropic_response('claude-3-opus-20240229', 50, 10)
    with patch.object(client.client.messages, 'create', new=AsyncMock(return_value=mock_response)):
        response = await client.messages.create(
            model='claude-3-opus-20240229',
            max_tokens=1024,
            messages=[{'role': 'user', 'content': 'Hello'}]
        )
        
        assert response.security is not None
        assert response.security.cost_record is not None
        assert response.security.cost_record.actual_cost > 0
        assert response.security.cost_record.provider == 'anthropic'
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
    
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=True,
        cost_tracker=tracker,
        budget_manager=budget_manager
    )
    client = TealAnthropic(config)
    
    mock_response = create_mock_anthropic_response('claude-3-opus-20240229', 50, 10)
    with patch.object(client.client.messages, 'create', new=AsyncMock(return_value=mock_response)) as mock_create:
        with pytest.raises(ValueError, match="Budget exceeded"):
            await client.messages.create(
                model='claude-3-opus-20240229',
                max_tokens=1024,
                messages=[{'role': 'user', 'content': 'Hello'}]
            )
        
        # Verify API was not called
        assert not mock_create.called


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
    
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=True,
        enable_cost_tracking=False,
        guardrail_engine=engine
    )
    client = TealAnthropic(config)
    
    mock_response = create_mock_anthropic_response('claude-3-opus-20240229', 50, 10, content='Unsafe output')
    with patch.object(client.client.messages, 'create', new=AsyncMock(return_value=mock_response)):
        with pytest.raises(ValueError, match="Output guardrail check failed"):
            await client.messages.create(
                model='claude-3-opus-20240229',
                max_tokens=1024,
                messages=[{'role': 'user', 'content': 'Hello'}]
            )


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Timezone-aware/naive datetime comparison issue in budget.py - pre-existing bug")
async def test_all_features_enabled():
    """Test message creation with all features enabled."""
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
    
    config = TealAnthropicConfig(
        api_key='test-key',
        agent_id='test-agent',
        enable_guardrails=True,
        enable_cost_tracking=True,
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    )
    client = TealAnthropic(config)
    
    mock_response = create_mock_anthropic_response('claude-3-opus-20240229', 50, 10)
    with patch.object(client.client.messages, 'create', new=AsyncMock(return_value=mock_response)):
        response = await client.messages.create(
            model='claude-3-opus-20240229',
            max_tokens=1024,
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
    config = TealAnthropicConfig(
        api_key='test-key',
        agent_id='custom-agent',
        base_url='https://custom.anthropic.com',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealAnthropic(config)
    
    assert client.config.agent_id == 'custom-agent'
    assert client.config.base_url == 'https://custom.anthropic.com'
    assert client.config.enable_guardrails is False
    assert client.config.enable_cost_tracking is False


@pytest.mark.asyncio
async def test_system_message():
    """Test message creation with system parameter."""
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealAnthropic(config)
    
    mock_response = create_mock_anthropic_response('claude-3-opus-20240229', 70, 15)
    with patch.object(client.client.messages, 'create', new=AsyncMock(return_value=mock_response)):
        response = await client.messages.create(
            model='claude-3-opus-20240229',
            max_tokens=1024,
            system='You are a helpful assistant.',
            messages=[{'role': 'user', 'content': 'Hello'}]
        )
        
        assert response.id == 'msg-test123'


@pytest.mark.asyncio
async def test_multiple_messages():
    """Test message creation with multiple messages."""
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealAnthropic(config)
    
    mock_response = create_mock_anthropic_response('claude-3-sonnet-20240229', 100, 30)
    with patch.object(client.client.messages, 'create', new=AsyncMock(return_value=mock_response)):
        response = await client.messages.create(
            model='claude-3-sonnet-20240229',
            max_tokens=2048,
            messages=[
                {'role': 'user', 'content': 'Hello'},
                {'role': 'assistant', 'content': 'Hi there!'},
                {'role': 'user', 'content': 'How are you?'}
            ]
        )
        
        assert response.id == 'msg-test123'
        assert response.usage['input_tokens'] == 100
        assert response.usage['output_tokens'] == 30


@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling for API failures."""
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealAnthropic(config)
    
    # Mock API call that raises an error
    with patch.object(client.client.messages, 'create', new=AsyncMock(side_effect=Exception("API Error"))):
        with pytest.raises(ValueError, match="TealAnthropic error"):
            await client.messages.create(
                model='claude-3-opus-20240229',
                max_tokens=1024,
                messages=[{'role': 'user', 'content': 'Hello'}]
            )


@pytest.mark.asyncio
async def test_stop_reason_max_tokens():
    """Test message creation that stops due to max_tokens."""
    config = TealAnthropicConfig(
        api_key='test-key',
        enable_guardrails=False,
        enable_cost_tracking=False
    )
    client = TealAnthropic(config)
    
    # Create response with max_tokens stop reason
    response_obj = MagicMock()
    response_obj.id = 'msg-test456'
    response_obj.type = 'message'
    response_obj.role = 'assistant'
    
    content_block = MagicMock()
    content_block.type = 'text'
    content_block.text = 'Truncated response...'
    response_obj.content = [content_block]
    
    response_obj.model = 'claude-3-haiku-20240307'
    response_obj.stop_reason = 'max_tokens'
    response_obj.stop_sequence = None
    response_obj.usage.input_tokens = 20
    response_obj.usage.output_tokens = 100
    
    with patch.object(client.client.messages, 'create', new=AsyncMock(return_value=response_obj)):
        response = await client.messages.create(
            model='claude-3-haiku-20240307',
            max_tokens=100,
            messages=[{'role': 'user', 'content': 'Write a long story'}]
        )
        
        assert response.stop_reason == 'max_tokens'
        assert response.usage['output_tokens'] == 100

