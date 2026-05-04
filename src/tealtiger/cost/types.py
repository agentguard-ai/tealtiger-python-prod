"""
Cost tracking types and data models.

This module defines Pydantic models for cost tracking, budget management,
and cost analytics in the TealTiger SDK.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, Any, List
from datetime import datetime

# Type aliases for literals
ModelProvider = Literal['openai', 'anthropic', 'azure-openai', 'google', 'bedrock', 'cohere', 'mistral', 'custom']
BudgetPeriod = Literal['hourly', 'daily', 'weekly', 'monthly', 'total']
BudgetAction = Literal['alert', 'block', 'throttle']
AlertSeverity = Literal['info', 'warning', 'critical']


class ModelPricing(BaseModel):
    """Pricing information for an AI model."""
    model: str
    provider: ModelProvider
    input_cost_per_1k: float
    output_cost_per_1k: float
    image_cost: Optional[float] = None
    audio_cost_per_second: Optional[float] = None
    last_updated: str


class TokenUsage(BaseModel):
    """Token usage information for a request."""
    input_tokens: int
    output_tokens: int
    total_tokens: int
    images: Optional[int] = None
    audio_duration: Optional[float] = None


class CostBreakdown(BaseModel):
    """Detailed cost breakdown by component."""
    input_cost: float
    output_cost: float
    image_cost: Optional[float] = None
    audio_cost: Optional[float] = None


class CostEstimate(BaseModel):
    """Pre-execution cost estimate."""
    estimated_cost: float
    model: str
    provider: ModelProvider
    estimated_tokens: TokenUsage
    breakdown: CostBreakdown
    timestamp: str


class CostRecord(BaseModel):
    """Post-execution cost record."""
    id: str
    request_id: str
    agent_id: str
    model: str
    provider: ModelProvider
    actual_tokens: TokenUsage
    actual_cost: float
    breakdown: CostBreakdown
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None


class BudgetScope(BaseModel):
    """Scope for budget enforcement."""
    type: Literal['agent', 'project', 'organization']
    id: str


class BudgetConfig(BaseModel):
    """Budget configuration."""
    id: str
    name: str
    limit: float
    period: BudgetPeriod
    alert_thresholds: List[int]
    action: BudgetAction
    scope: Optional[BudgetScope] = None
    enabled: bool = True
    created_at: str
    updated_at: str


class BudgetStatus(BaseModel):
    """Current budget status."""
    budget: BudgetConfig
    current_spending: float
    remaining: float
    percentage_used: float
    is_exceeded: bool
    active_alerts: List[int]
    period_start: str
    period_end: str
    last_updated: str


class CostAlert(BaseModel):
    """Budget alert notification."""
    id: str
    budget_id: str
    threshold: int
    current_spending: float
    limit: float
    message: str
    severity: AlertSeverity
    timestamp: str
    acknowledged: bool = False


class CostSummary(BaseModel):
    """Aggregated cost analytics."""
    total_cost: float
    total_requests: int
    average_cost_per_request: float
    by_model: Dict[str, float]
    by_provider: Dict[ModelProvider, float]
    by_agent: Dict[str, float]
    period: Dict[str, str]
    total_tokens: Dict[str, int]
