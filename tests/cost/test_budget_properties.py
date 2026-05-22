"""
Property-based tests for BudgetManager.

These tests validate universal properties that should hold across all inputs.
"""

import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime, timedelta, timezone

from tealtiger.cost.budget import BudgetManager, BudgetEnforcementResult
from tealtiger.cost.storage import InMemoryCostStorage
from tealtiger.cost.types import (
    BudgetConfig,
    BudgetScope,
    CostRecord,
    TokenUsage,
    CostBreakdown,
)


# Strategies for generating test data
budget_periods = st.sampled_from(['hourly', 'daily', 'weekly', 'monthly', 'total'])
budget_actions = st.sampled_from(['alert', 'block', 'throttle'])
alert_thresholds = st.lists(
    st.integers(min_value=1, max_value=100),
    min_size=1,
    max_size=5,
    unique=True
).map(sorted)


@pytest.mark.asyncio
@settings(max_examples=100)
@given(
    period=budget_periods,
    limit=st.floats(min_value=0.01, max_value=100.0),
    cost_amount=st.floats(min_value=0.001, max_value=0.1)
)
async def test_budget_period_calculation(period, limit, cost_amount):
    """
    Feature: python-sdk-feature-parity, Property 11: Budget period calculation
    
    For any budget with a specific period, the calculated spending should only
    include records within the current period boundaries.
    
    **Validates: Requirements 3.3**
    """
    storage = InMemoryCostStorage()
    manager = BudgetManager(storage)
    
    # Create a budget
    budget = manager.create_budget(
        name=f"Test {period} Budget",
        limit=limit,
        period=period,
        alert_thresholds=[50, 75, 90],
        action='block'
    )
    
    # Create cost records at different times
    now = datetime.now(timezone.utc)
    
    # Record within current period
    record_current = CostRecord(
        id='rec-current',
        request_id='req-1',
        agent_id='agent-1',
        model='gpt-4',
        provider='openai',
        actual_tokens=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        actual_cost=cost_amount,
        breakdown=CostBreakdown(input_cost=cost_amount * 0.6, output_cost=cost_amount * 0.4),
        timestamp=now.isoformat()
    )
    await storage.store(record_current)
    
    # Record outside current period (way in the past)
    past_time = now - timedelta(days=365)
    record_past = CostRecord(
        id='rec-past',
        request_id='req-2',
        agent_id='agent-1',
        model='gpt-4',
        provider='openai',
        actual_tokens=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        actual_cost=cost_amount * 10,  # Much larger cost
        breakdown=CostBreakdown(input_cost=cost_amount * 6, output_cost=cost_amount * 4),
        timestamp=past_time.isoformat()
    )
    await storage.store(record_past)
    
    # Get budget status
    status = await manager.get_budget_status(budget.id)
    
    # The current spending should only include the current period record
    # For 'total' period, it includes all records
    if period == 'total':
        assert status.current_spending == pytest.approx(cost_amount + cost_amount * 10, rel=1e-6)
    else:
        # For time-bounded periods, should only include current record
        assert status.current_spending == pytest.approx(cost_amount, rel=1e-6)
    
    # Verify period boundaries are set
    assert status.period_start is not None
    assert status.period_end is not None
    period_start = datetime.fromisoformat(status.period_start)
    period_end = datetime.fromisoformat(status.period_end)
    
    # Current record should be within period
    record_time = datetime.fromisoformat(record_current.timestamp)
    assert period_start <= record_time <= period_end


@pytest.mark.asyncio
@settings(max_examples=100)
@given(
    limit=st.floats(min_value=0.01, max_value=1.0),
    current_cost=st.floats(min_value=0.001, max_value=0.5),
    estimated_cost=st.floats(min_value=0.001, max_value=1.0)
)
async def test_budget_blocking(limit, current_cost, estimated_cost):
    """
    Feature: python-sdk-feature-parity, Property 12: Budget blocking
    
    For any budget check where estimated cost plus current spending exceeds
    the budget limit, the check should return allowed=False.
    
    **Validates: Requirements 3.4**
    """
    storage = InMemoryCostStorage()
    manager = BudgetManager(storage)
    
    # Create a budget with 'block' action
    budget = manager.create_budget(
        name="Test Budget",
        limit=limit,
        period='total',
        alert_thresholds=[90],
        action='block'
    )
    
    # Add current spending
    if current_cost > 0:
        record = CostRecord(
            id='rec-1',
            request_id='req-1',
            agent_id='agent-1',
            model='gpt-4',
            provider='openai',
            actual_tokens=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
            actual_cost=current_cost,
            breakdown=CostBreakdown(input_cost=current_cost * 0.6, output_cost=current_cost * 0.4),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        await storage.store(record)
    
    # Check budget
    result = await manager.check_budget('agent-1', estimated_cost)
    
    # Verify blocking behavior
    projected_spending = current_cost + estimated_cost
    if projected_spending > limit:
        assert result.allowed is False
        assert result.blocked_by is not None
        assert result.blocked_by.id == budget.id
    else:
        assert result.allowed is True
        assert result.blocked_by is None


@pytest.mark.asyncio
@settings(max_examples=100)
@given(
    limit=st.floats(min_value=1.0, max_value=10.0),
    threshold=st.integers(min_value=1, max_value=100),
    spending_ratio=st.floats(min_value=0.0, max_value=1.5)
)
async def test_alert_threshold_generation(limit, threshold, spending_ratio):
    """
    Feature: python-sdk-feature-parity, Property 13: Alert threshold generation
    
    For any budget where current spending crosses a threshold percentage,
    an alert should be generated with the correct threshold value.
    
    **Validates: Requirements 3.5**
    """
    storage = InMemoryCostStorage()
    manager = BudgetManager(storage)
    
    # Create a budget with a single threshold
    budget = manager.create_budget(
        name="Test Budget",
        limit=limit,
        period='total',
        alert_thresholds=[threshold],
        action='alert'
    )
    
    # Calculate spending that crosses the threshold
    spending = limit * (spending_ratio)
    
    if spending > 0:
        record = CostRecord(
            id='rec-1',
            request_id='req-1',
            agent_id='agent-1',
            model='gpt-4',
            provider='openai',
            actual_tokens=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
            actual_cost=spending,
            breakdown=CostBreakdown(input_cost=spending * 0.6, output_cost=spending * 0.4),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        await storage.store(record)
    
    # Get budget status
    status = await manager.get_budget_status(budget.id)
    
    # Check if threshold should be active
    percentage_used = (spending / limit) * 100
    
    if percentage_used >= threshold:
        # Threshold should be in active alerts
        assert threshold in status.active_alerts
    else:
        # Threshold should not be in active alerts
        assert threshold not in status.active_alerts


@pytest.mark.asyncio
@settings(max_examples=100)
@given(
    limit=st.floats(min_value=0.1, max_value=10.0),
    agent1_cost=st.floats(min_value=0.01, max_value=5.0),
    agent2_cost=st.floats(min_value=0.01, max_value=5.0)
)
async def test_agent_scoped_budget_isolation(limit, agent1_cost, agent2_cost):
    """
    Feature: python-sdk-feature-parity, Property 14: Agent-scoped budget isolation
    
    For any agent-scoped budget, budget checks for different agents should not
    affect each other's spending calculations.
    
    **Validates: Requirements 3.7**
    """
    storage = InMemoryCostStorage()
    manager = BudgetManager(storage)
    
    # Create agent-scoped budgets
    budget1 = manager.create_budget(
        name="Agent 1 Budget",
        limit=limit,
        period='total',
        alert_thresholds=[90],
        action='block',
        scope=BudgetScope(type='agent', id='agent-1')
    )
    
    budget2 = manager.create_budget(
        name="Agent 2 Budget",
        limit=limit,
        period='total',
        alert_thresholds=[90],
        action='block',
        scope=BudgetScope(type='agent', id='agent-2')
    )
    
    # Add spending for agent 1
    record1 = CostRecord(
        id='rec-1',
        request_id='req-1',
        agent_id='agent-1',
        model='gpt-4',
        provider='openai',
        actual_tokens=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        actual_cost=agent1_cost,
        breakdown=CostBreakdown(input_cost=agent1_cost * 0.6, output_cost=agent1_cost * 0.4),
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    await storage.store(record1)
    
    # Add spending for agent 2
    record2 = CostRecord(
        id='rec-2',
        request_id='req-2',
        agent_id='agent-2',
        model='gpt-4',
        provider='openai',
        actual_tokens=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        actual_cost=agent2_cost,
        breakdown=CostBreakdown(input_cost=agent2_cost * 0.6, output_cost=agent2_cost * 0.4),
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    await storage.store(record2)
    
    # Get budget status for each agent
    status1 = await manager.get_budget_status(budget1.id)
    status2 = await manager.get_budget_status(budget2.id)
    
    # Each budget should only see its own agent's spending
    assert status1.current_spending == pytest.approx(agent1_cost, rel=1e-6)
    assert status2.current_spending == pytest.approx(agent2_cost, rel=1e-6)
    
    # Spending should be isolated
    assert status1.current_spending != status2.current_spending or agent1_cost == agent2_cost


@pytest.mark.asyncio
@settings(max_examples=100)
@given(
    limit=st.floats(min_value=0.1, max_value=100.0),
    spending=st.floats(min_value=0.0, max_value=150.0)
)
async def test_budget_status_calculation(limit, spending):
    """
    Feature: python-sdk-feature-parity, Property 15: Budget status calculation
    
    For any budget, the status remaining amount should equal limit minus
    current spending, and percentage_used should equal
    (current_spending / limit) * 100.
    
    **Validates: Requirements 3.10**
    """
    storage = InMemoryCostStorage()
    manager = BudgetManager(storage)
    
    # Create a budget
    budget = manager.create_budget(
        name="Test Budget",
        limit=limit,
        period='total',
        alert_thresholds=[50, 75, 90],
        action='block'
    )
    
    # Add spending
    if spending > 0:
        record = CostRecord(
            id='rec-1',
            request_id='req-1',
            agent_id='agent-1',
            model='gpt-4',
            provider='openai',
            actual_tokens=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
            actual_cost=spending,
            breakdown=CostBreakdown(input_cost=spending * 0.6, output_cost=spending * 0.4),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        await storage.store(record)
    
    # Get budget status
    status = await manager.get_budget_status(budget.id)
    
    # Verify calculations
    expected_remaining = max(0.0, limit - spending)
    expected_percentage = (spending / limit) * 100
    expected_exceeded = spending > limit
    
    assert status.current_spending == pytest.approx(spending, rel=1e-6)
    assert status.remaining == pytest.approx(expected_remaining, rel=1e-6)
    assert status.percentage_used == pytest.approx(expected_percentage, rel=1e-6)
    assert status.is_exceeded == expected_exceeded


@pytest.mark.asyncio
@settings(max_examples=100)
@given(
    limit=st.floats(min_value=1.0, max_value=100.0),
    initial_cost=st.floats(min_value=0.01, max_value=10.0),
    additional_cost=st.floats(min_value=0.01, max_value=10.0)
)
async def test_cost_recording_updates_budget(limit, initial_cost, additional_cost):
    """
    Feature: python-sdk-feature-parity, Property 16: Cost recording updates budget
    
    For any cost record, after recording it with the budget manager, the
    budget's current spending should increase by the record's actual cost.
    
    **Validates: Requirements 3.11**
    """
    storage = InMemoryCostStorage()
    manager = BudgetManager(storage)
    
    # Create a budget
    budget = manager.create_budget(
        name="Test Budget",
        limit=limit,
        period='total',
        alert_thresholds=[50, 75, 90],
        action='alert'
    )
    
    # Add initial spending
    record1 = CostRecord(
        id='rec-1',
        request_id='req-1',
        agent_id='agent-1',
        model='gpt-4',
        provider='openai',
        actual_tokens=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        actual_cost=initial_cost,
        breakdown=CostBreakdown(input_cost=initial_cost * 0.6, output_cost=initial_cost * 0.4),
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    await storage.store(record1)
    
    # Get initial status
    status_before = await manager.get_budget_status(budget.id)
    spending_before = status_before.current_spending
    
    # Record additional cost
    record2 = CostRecord(
        id='rec-2',
        request_id='req-2',
        agent_id='agent-1',
        model='gpt-4',
        provider='openai',
        actual_tokens=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        actual_cost=additional_cost,
        breakdown=CostBreakdown(input_cost=additional_cost * 0.6, output_cost=additional_cost * 0.4),
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    await storage.store(record2)
    await manager.record_cost(record2)
    
    # Get updated status
    status_after = await manager.get_budget_status(budget.id)
    spending_after = status_after.current_spending
    
    # Verify spending increased by the additional cost
    expected_increase = additional_cost
    actual_increase = spending_after - spending_before
    
    assert actual_increase == pytest.approx(expected_increase, rel=1e-6)
    assert spending_after == pytest.approx(initial_cost + additional_cost, rel=1e-6)

