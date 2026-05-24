"""
Budget Manager

Manages budgets, alerts, and enforcement for cost control.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel

from .types import (
    BudgetConfig,
    BudgetStatus,
    CostAlert,
    CostRecord,
    BudgetPeriod,
    AlertSeverity,
    BudgetScope,
    BudgetAction,
)
from .storage import CostStorage
from .utils import generate_id


class BudgetEnforcementResult(BaseModel):
    """Budget enforcement action result."""
    allowed: bool
    blocked_by: Optional[BudgetConfig] = None
    alerts: List[CostAlert] = []
    status: Optional[BudgetStatus] = None


class BudgetManager:
    """Budget Manager class for cost control."""
    
    def __init__(self, storage: CostStorage):
        """
        Initialize BudgetManager.
        
        Args:
            storage: Cost storage instance for querying spending data
        """
        self.budgets: Dict[str, BudgetConfig] = {}
        self.alerts: Dict[str, List[CostAlert]] = {}
        self.storage = storage
    
    def create_budget(
        self,
        name: str,
        limit: float,
        period: BudgetPeriod,
        alert_thresholds: List[int],
        action: BudgetAction = 'block',
        scope: Optional[BudgetScope] = None,
        enabled: bool = True
    ) -> BudgetConfig:
        """
        Create a new budget.
        
        Args:
            name: Budget name
            limit: Budget limit in USD
            period: Budget period (hourly, daily, weekly, monthly, total)
            alert_thresholds: Alert thresholds as percentages (e.g., [50, 75, 90])
            action: Action to take when budget is exceeded (alert, block, throttle)
            scope: Optional scope for budget (agent, project, organization)
            enabled: Whether budget is enabled
            
        Returns:
            Created budget configuration
        """
        now = datetime.now(timezone.utc).isoformat()
        budget = BudgetConfig(
            id=generate_id(),
            name=name,
            limit=limit,
            period=period,
            alert_thresholds=alert_thresholds,
            action=action,
            scope=scope,
            enabled=enabled,
            created_at=now,
            updated_at=now
        )
        self.budgets[budget.id] = budget
        self.alerts[budget.id] = []
        return budget
    
    def update_budget(
        self,
        id: str,
        **updates
    ) -> Optional[BudgetConfig]:
        """
        Update an existing budget.
        
        Args:
            id: Budget ID
            **updates: Fields to update
            
        Returns:
            Updated budget or None if not found
        """
        budget = self.budgets.get(id)
        if not budget:
            return None
        
        updated_data = budget.dict()
        updated_data.update(updates)
        updated_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        updated_budget = BudgetConfig(**updated_data)
        self.budgets[id] = updated_budget
        return updated_budget
    
    def delete_budget(self, id: str) -> bool:
        """
        Delete a budget.
        
        Args:
            id: Budget ID
            
        Returns:
            True if deleted, False if not found
        """
        self.alerts.pop(id, None)
        return self.budgets.pop(id, None) is not None
    
    def get_budget(self, id: str) -> Optional[BudgetConfig]:
        """
        Get a budget by ID.
        
        Args:
            id: Budget ID
            
        Returns:
            Budget or None if not found
        """
        return self.budgets.get(id)
    
    def get_all_budgets(self) -> List[BudgetConfig]:
        """
        Get all budgets.
        
        Returns:
            List of all budgets
        """
        return list(self.budgets.values())
    
    def get_budgets_by_scope(
        self,
        scope_type: str,
        scope_id: str
    ) -> List[BudgetConfig]:
        """
        Get budgets for a specific scope.
        
        Args:
            scope_type: Scope type (agent, project, organization)
            scope_id: Scope ID
            
        Returns:
            List of budgets matching the scope
        """
        return [
            b for b in self.budgets.values()
            if b.scope and b.scope.type == scope_type and b.scope.id == scope_id
        ]
    
    async def check_budget(
        self,
        agent_id: str,
        estimated_cost: float
    ) -> BudgetEnforcementResult:
        """
        Check if a cost would exceed any budgets.
        
        Args:
            agent_id: Agent ID
            estimated_cost: Estimated cost in USD
            
        Returns:
            Enforcement result with allowed status and alerts
        """
        relevant_budgets = self._get_relevant_budgets(agent_id)
        alerts: List[CostAlert] = []
        blocked_by: Optional[BudgetConfig] = None
        
        for budget in relevant_budgets:
            if not budget.enabled:
                continue
            
            status = await self.get_budget_status(budget.id)
            if not status:
                continue
            
            # Check if adding this cost would exceed the budget
            projected_spending = status.current_spending + estimated_cost
            projected_percentage = (projected_spending / budget.limit) * 100
            
            # Check for threshold alerts
            for threshold in budget.alert_thresholds:
                if projected_percentage >= threshold and status.percentage_used < threshold:
                    alert = self._create_alert(budget, threshold, projected_spending)
                    alerts.append(alert)
                    self._add_alert(budget.id, alert)
            
            # Check if budget would be exceeded
            if projected_spending > budget.limit and budget.action == 'block':
                blocked_by = budget
                break
        
        return BudgetEnforcementResult(
            allowed=blocked_by is None,
            blocked_by=blocked_by,
            alerts=alerts,
            status=await self.get_budget_status(blocked_by.id) if blocked_by else None
        )
    
    async def record_cost(self, record: CostRecord) -> None:
        """
        Record a cost and update budget tracking.
        
        Args:
            record: Cost record to process
        """
        relevant_budgets = self._get_relevant_budgets(record.agent_id)
        
        for budget in relevant_budgets:
            if not budget.enabled:
                continue
            
            status = await self.get_budget_status(budget.id)
            if not status:
                continue
            
            # Check for threshold alerts - generate alerts for any active thresholds
            # that don't already have alerts
            existing_alerts = self.get_alerts(budget.id)
            existing_thresholds = {a.threshold for a in existing_alerts}
            
            for threshold in budget.alert_thresholds:
                # Generate alert if we've crossed this threshold and don't have an alert for it yet
                if status.percentage_used >= threshold and threshold not in existing_thresholds:
                    alert = self._create_alert(budget, threshold, status.current_spending)
                    self._add_alert(budget.id, alert)
    
    async def get_budget_status(self, budget_id: str) -> Optional[BudgetStatus]:
        """
        Get budget status.
        
        Args:
            budget_id: Budget ID
            
        Returns:
            Budget status or None if not found
        """
        budget = self.budgets.get(budget_id)
        if not budget:
            return None
        
        start, end = self._get_period_dates(budget.period)
        records = await self.storage.get_by_date_range(start, end)
        
        # Filter by scope if applicable
        if budget.scope:
            if budget.scope.type == 'agent':
                records = [r for r in records if r.agent_id == budget.scope.id]
            # TODO: Add project and organization filtering when those concepts are implemented
        
        current_spending = sum(r.actual_cost for r in records)
        remaining = max(0.0, budget.limit - current_spending)
        percentage_used = (current_spending / budget.limit) * 100
        is_exceeded = current_spending > budget.limit
        
        # Get active alerts
        active_alerts = [t for t in budget.alert_thresholds if percentage_used >= t]
        
        return BudgetStatus(
            budget=budget,
            current_spending=current_spending,
            remaining=remaining,
            percentage_used=percentage_used,
            is_exceeded=is_exceeded,
            active_alerts=active_alerts,
            period_start=start.isoformat(),
            period_end=end.isoformat(),
            last_updated=datetime.now(timezone.utc).isoformat()
        )
    
    def get_alerts(self, budget_id: str) -> List[CostAlert]:
        """
        Get all alerts for a budget.
        
        Args:
            budget_id: Budget ID
            
        Returns:
            List of alerts
        """
        return self.alerts.get(budget_id, [])
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """
        Acknowledge an alert.
        
        Args:
            alert_id: Alert ID
            
        Returns:
            True if acknowledged, False if not found
        """
        for alerts in self.alerts.values():
            for alert in alerts:
                if alert.id == alert_id:
                    alert.acknowledged = True
                    return True
        return False
    
    def clear_alerts(self, budget_id: str) -> None:
        """
        Clear all alerts for a budget.
        
        Args:
            budget_id: Budget ID
        """
        self.alerts[budget_id] = []
    
    def _get_relevant_budgets(self, agent_id: str) -> List[BudgetConfig]:
        """
        Get relevant budgets for an agent.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            List of relevant budgets
        """
        return [
            b for b in self.budgets.values()
            if b.enabled and (
                not b.scope or
                (b.scope.type == 'agent' and b.scope.id == agent_id)
            )
        ]
    
    def _get_period_dates(self, period: BudgetPeriod) -> tuple:
        """
        Get period start and end dates.
        
        Args:
            period: Budget period
            
        Returns:
            Tuple of (start_date, end_date)
        """
        now = datetime.now(timezone.utc)
        end = now
        
        if period == 'hourly':
            start = now.replace(minute=0, second=0, microsecond=0)
        elif period == 'daily':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'weekly':
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'monthly':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:  # total
            start = datetime(1970, 1, 1, tzinfo=timezone.utc)
        
        return start, end
    
    def _create_alert(
        self,
        budget: BudgetConfig,
        threshold: int,
        current_spending: float
    ) -> CostAlert:
        """
        Create an alert.
        
        Args:
            budget: Budget configuration
            threshold: Threshold percentage
            current_spending: Current spending amount
            
        Returns:
            Created alert
        """
        severity: AlertSeverity = (
            'critical' if threshold >= 100 else
            'warning' if threshold >= 90 else
            'info'
        )
        
        return CostAlert(
            id=generate_id(),
            budget_id=budget.id,
            threshold=threshold,
            current_spending=current_spending,
            limit=budget.limit,
            message=f'Budget "{budget.name}" has reached {threshold}% ({current_spending:.4f} / {budget.limit} USD)',
            severity=severity,
            timestamp=datetime.now(timezone.utc).isoformat(),
            acknowledged=False
        )
    
    def _add_alert(self, budget_id: str, alert: CostAlert) -> None:
        """
        Add an alert to the budget.
        
        Args:
            budget_id: Budget ID
            alert: Alert to add
        """
        if budget_id not in self.alerts:
            self.alerts[budget_id] = []
        self.alerts[budget_id].append(alert)
