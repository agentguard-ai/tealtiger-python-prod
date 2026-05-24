"""
Unit tests for BudgetManager.

These tests validate specific examples and edge cases.
"""

import pytest
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


class TestBudgetCRUD:
    """Test budget CRUD operations."""
    
    def test_create_budget(self):
        """Test creating a budget."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        budget = manager.create_budget(
            name="Test Budget",
            limit=100.0,
            period='daily',
            alert_thresholds=[50, 75, 90],
            action='block'
        )
        
        assert budget.id is not None
        assert budget.name == "Test Budget"
        assert budget.limit == 100.0
        assert budget.period == 'daily'
        assert budget.alert_thresholds == [50, 75, 90]
        assert budget.action == 'block'
        assert budget.enabled is True
        assert budget.created_at is not None
        assert budget.updated_at is not None
    
    def test_create_budget_with_scope(self):
        """Test creating a budget with agent scope."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        scope = BudgetScope(type='agent', id='agent-123')
        budget = manager.create_budget(
            name="Agent Budget",
            limit=50.0,
            period='monthly',
            alert_thresholds=[80],
            action='alert',
            scope=scope
        )
        
        assert budget.scope is not None
        assert budget.scope.type == 'agent'
        assert budget.scope.id == 'agent-123'
    
    def test_get_budget(self):
        """Test getting a budget by ID."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        budget = manager.create_budget(
            name="Test Budget",
            limit=100.0,
            period='daily',
            alert_thresholds=[50],
            action='block'
        )
        
        retrieved = manager.get_budget(budget.id)
        assert retrieved is not None
        assert retrieved.id == budget.id
        assert retrieved.name == budget.name
    
    def test_get_nonexistent_budget(self):
        """Test getting a budget that doesn't exist."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        result = manager.get_budget('nonexistent-id')
        assert result is None
    
    def test_update_budget(self):
        """Test updating a budget."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        budget = manager.create_budget(
            name="Test Budget",
            limit=100.0,
            period='daily',
            alert_thresholds=[50],
            action='block'
        )
        
        original_updated_at = budget.updated_at
        
        updated = manager.update_budget(
            budget.id,
            limit=200.0,
            name="Updated Budget"
        )
        
        assert updated is not None
        assert updated.limit == 200.0
        assert updated.name == "Updated Budget"
        assert updated.period == 'daily'  # Unchanged
        assert updated.updated_at != original_updated_at
    
    def test_update_nonexistent_budget(self):
        """Test updating a budget that doesn't exist."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        result = manager.update_budget('nonexistent-id', limit=200.0)
        assert result is None
    
    def test_delete_budget(self):
        """Test deleting a budget."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        budget = manager.create_budget(
            name="Test Budget",
            limit=100.0,
            period='daily',
            alert_thresholds=[50],
            action='block'
        )
        
        result = manager.delete_budget(budget.id)
        assert result is True
        
        # Verify it's deleted
        retrieved = manager.get_budget(budget.id)
        assert retrieved is None
    
    def test_delete_nonexistent_budget(self):
        """Test deleting a budget that doesn't exist."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        result = manager.delete_budget('nonexistent-id')
        assert result is False
    
    def test_get_all_budgets(self):
        """Test getting all budgets."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        budget1 = manager.create_budget(
            name="Budget 1",
            limit=100.0,
            period='daily',
            alert_thresholds=[50],
            action='block'
        )
        
        budget2 = manager.create_budget(
            name="Budget 2",
            limit=200.0,
            period='monthly',
            alert_thresholds=[75],
            action='alert'
        )
        
        all_budgets = manager.get_all_budgets()
        assert len(all_budgets) == 2
        assert budget1 in all_budgets
        assert budget2 in all_budgets
    
    def test_get_budgets_by_scope(self):
        """Test getting budgets by scope."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        # Create budgets with different scopes
        budget1 = manager.create_budget(
            name="Agent 1 Budget",
            limit=100.0,
            period='daily',
            alert_thresholds=[50],
            action='block',
            scope=BudgetScope(type='agent', id='agent-1')
        )
        
        budget2 = manager.create_budget(
            name="Agent 2 Budget",
            limit=200.0,
            period='daily',
            alert_thresholds=[50],
            action='block',
            scope=BudgetScope(type='agent', id='agent-2')
        )
        
        budget3 = manager.create_budget(
            name="Global Budget",
            limit=500.0,
            period='daily',
            alert_thresholds=[50],
            action='block'
        )
        
        # Get budgets for agent-1
        agent1_budgets = manager.get_budgets_by_scope('agent', 'agent-1')
        assert len(agent1_budgets) == 1
        assert agent1_budgets[0].id == budget1.id


class TestBudgetPeriods:
    """Test different budget period types."""
    
    @pytest.mark.asyncio
    async def test_hourly_period(self):
        """Test hourly budget period."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        budget = manager.create_budget(
            name="Hourly Budget",
            limit=10.0,
            period='hourly',
            alert_thresholds=[90],
            action='block'
        )
        
        status = await manager.get_budget_status(budget.id)
        assert status is not None
        
        # Verify period is within the current hour
        start = datetime.fromisoformat(status.period_start)
        end = datetime.fromisoformat(status.period_end)
        assert start.minute == 0
        assert start.second == 0
        assert end >= start
    
    @pytest.mark.asyncio
    async def test_daily_period(self):
        """Test daily budget period."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        budget = manager.create_budget(
            name="Daily Budget",
            limit=100.0,
            period='daily',
            alert_thresholds=[90],
            action='block'
        )
        
        status = await manager.get_budget_status(budget.id)
        assert status is not None
        
        # Verify period starts at midnight
        start = datetime.fromisoformat(status.period_start)
        assert start.hour == 0
        assert start.minute == 0
        assert start.second == 0
    
    @pytest.mark.asyncio
    async def test_weekly_period(self):
        """Test weekly budget period."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        budget = manager.create_budget(
            name="Weekly Budget",
            limit=500.0,
            period='weekly',
            alert_thresholds=[90],
            action='block'
        )
        
        status = await manager.get_budget_status(budget.id)
        assert status is not None
        
        # Verify period starts on Monday
        start = datetime.fromisoformat(status.period_start)
        assert start.weekday() == 0  # Monday
    
    @pytest.mark.asyncio
    async def test_monthly_period(self):
        """Test monthly budget period."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        budget = manager.create_budget(
            name="Monthly Budget",
            limit=1000.0,
            period='monthly',
            alert_thresholds=[90],
            action='block'
        )
        
        status = await manager.get_budget_status(budget.id)
        assert status is not None
        
        # Verify period starts on first day of month
        start = datetime.fromisoformat(status.period_start)
        assert start.day == 1
    
    @pytest.mark.asyncio
    async def test_total_period(self):
        """Test total budget period."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        budget = manager.create_budget(
            name="Total Budget",
            limit=10000.0,
            period='total',
            alert_thresholds=[90],
            action='block'
        )
        
        status = await manager.get_budget_status(budget.id)
        assert status is not None
        
        # Verify period starts at epoch
        start = datetime.fromisoformat(status.period_start)
        assert start.year == 1970


class TestAlerts:
    """Test alert functionality."""
    
    @pytest.mark.asyncio
    async def test_alert_generation_on_check(self):
        """Test that alerts are generated during budget check."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        budget = manager.create_budget(
            name="Test Budget",
            limit=100.0,
            period='total',
            alert_thresholds=[50, 75, 90],
            action='alert'
        )
        
        # Add spending to 40%
        record = CostRecord(
            id='rec-1',
            request_id='req-1',
            agent_id='agent-1',
            model='gpt-4',
            provider='openai',
            actual_tokens=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
            actual_cost=40.0,
            breakdown=CostBreakdown(input_cost=24.0, output_cost=16.0),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        await storage.store(record)
        
        # Check budget with cost that crosses 50% threshold
        result = await manager.check_budget('agent-1', 15.0)
        
        # Should generate alert for 50% threshold
        assert len(result.alerts) == 1
        assert result.alerts[0].threshold == 50
        assert result.alerts[0].severity == 'info'
    
    @pytest.mark.asyncio
    async def test_alert_generation_on_record(self):
        """Test that alerts are generated when recording costs."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        budget = manager.create_budget(
            name="Test Budget",
            limit=100.0,
            period='total',
            alert_thresholds=[50, 75, 90],
            action='alert'
        )
        
        # Add spending to 60%
        record = CostRecord(
            id='rec-1',
            request_id='req-1',
            agent_id='agent-1',
            model='gpt-4',
            provider='openai',
            actual_tokens=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
            actual_cost=60.0,
            breakdown=CostBreakdown(input_cost=36.0, output_cost=24.0),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        await storage.store(record)
        await manager.record_cost(record)
        
        # Should have generated alert for 50% threshold
        alerts = manager.get_alerts(budget.id)
        assert len(alerts) == 1
        assert alerts[0].threshold == 50
    
    def test_acknowledge_alert(self):
        """Test acknowledging an alert."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        budget = manager.create_budget(
            name="Test Budget",
            limit=100.0,
            period='total',
            alert_thresholds=[50],
            action='alert'
        )
        
        # Manually create an alert
        from tealtiger.cost.types import CostAlert
        alert = CostAlert(
            id='alert-1',
            budget_id=budget.id,
            threshold=50,
            current_spending=55.0,
            limit=100.0,
            message="Test alert",
            severity='info',
            timestamp=datetime.now(timezone.utc).isoformat(),
            acknowledged=False
        )
        manager.alerts[budget.id] = [alert]
        
        # Acknowledge the alert
        result = manager.acknowledge_alert('alert-1')
        assert result is True
        
        # Verify it's acknowledged
        alerts = manager.get_alerts(budget.id)
        assert alerts[0].acknowledged is True
    
    def test_acknowledge_nonexistent_alert(self):
        """Test acknowledging an alert that doesn't exist."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        result = manager.acknowledge_alert('nonexistent-alert')
        assert result is False
    
    def test_clear_alerts(self):
        """Test clearing all alerts for a budget."""
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        budget = manager.create_budget(
            name="Test Budget",
            limit=100.0,
            period='total',
            alert_thresholds=[50],
            action='alert'
        )
        
        # Manually create alerts
        from tealtiger.cost.types import CostAlert
        alert1 = CostAlert(
            id='alert-1',
            budget_id=budget.id,
            threshold=50,
            current_spending=55.0,
            limit=100.0,
            message="Test alert 1",
            severity='info',
            timestamp=datetime.now(timezone.utc).isoformat(),
            acknowledged=False
        )
        alert2 = CostAlert(
            id='alert-2',
            budget_id=budget.id,
            threshold=75,
            current_spending=80.0,
            limit=100.0,
            message="Test alert 2",
            severity='warning',
            timestamp=datetime.now(timezone.utc).isoformat(),
            acknowledged=False
        )
        manager.alerts[budget.id] = [alert1, alert2]
        
        # Clear alerts
        manager.clear_alerts(budget.id)
        
        # Verify they're cleared
        alerts = manager.get_alerts(budget.id)
        assert len(alerts) == 0
    
    @pytest.mark.asyncio
    async def test_alert_severity_levels(self):
        """Test that alert severity is set correctly based on threshold."""
        # Test that severity is correctly assigned based on threshold value
        # info: threshold < 90
        # warning: 90 <= threshold < 100
        # critical: threshold >= 100
        
        storage = InMemoryCostStorage()
        manager = BudgetManager(storage)
        
        # Create a budget and manually check alert creation logic
        budget = manager.create_budget(
            name="Test Budget",
            limit=100.0,
            period='total',
            alert_thresholds=[50, 90, 100],
            action='alert'
        )
        
        # Test alert creation with different thresholds
        alert_50 = manager._create_alert(budget, 50, 55.0)
        assert alert_50.severity == 'info'
        assert alert_50.threshold == 50
        
        alert_90 = manager._create_alert(budget, 90, 95.0)
        assert alert_90.severity == 'warning'
        assert alert_90.threshold == 90
        
        alert_100 = manager._create_alert(budget, 100, 105.0)
        assert alert_100.severity == 'critical'
        assert alert_100.threshold == 100

