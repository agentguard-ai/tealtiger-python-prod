"""
Cost Tracker

Core component for calculating and tracking AI model costs.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from pydantic import BaseModel

from .pricing import get_model_pricing
from .types import (
    CostBreakdown,
    CostEstimate,
    CostRecord,
    ModelPricing,
    ModelProvider,
    TokenUsage,
)
from .utils import generate_id

logger = logging.getLogger(__name__)


class CostTrackerConfig(BaseModel):
    """Configuration for CostTracker."""
    enabled: bool = True
    persist_records: bool = True
    custom_pricing: Optional[Dict[str, ModelPricing]] = None
    default_provider: Optional[ModelProvider] = None
    enable_budgets: bool = True
    enable_alerts: bool = True


class CostTracker:
    """
    Core component for calculating and tracking AI model costs.

    Supports:
    - Pre-execution cost estimation
    - Post-execution actual cost calculation
    - Custom pricing overrides
    - Multiple AI providers (OpenAI, Anthropic, Google, Cohere)
    - Vision and audio models
    """

    def __init__(self, config: Optional[CostTrackerConfig] = None):
        """
        Initialize CostTracker.

        Args:
            config: Optional configuration
        """
        self.config = config or CostTrackerConfig()
        self.custom_pricing: Dict[str, ModelPricing] = {}

        if config and config.custom_pricing:
            self.custom_pricing = config.custom_pricing

    def estimate_cost(
        self,
        model: str,
        estimated_tokens: TokenUsage,
        provider: Optional[ModelProvider] = None
    ) -> CostEstimate:
        """
        Estimate cost before API call.

        Args:
            model: Model identifier
            estimated_tokens: Estimated token usage
            provider: Optional provider override

        Returns:
            Cost estimate with breakdown
        """
        if not self.config.enabled:
            return self._create_zero_estimate(
                model,
                provider or self.config.default_provider or 'openai',
                estimated_tokens
            )

        pricing = self._get_pricing(model, provider)
        if not pricing:
            logger.warning(f"No pricing found for model: {model}")
            return self._create_zero_estimate(
                model,
                provider or self.config.default_provider or 'custom',
                estimated_tokens
            )

        breakdown = self._calculate_breakdown(pricing, estimated_tokens)
        total_cost = sum(v for v in breakdown.model_dump().values() if v is not None)

        return CostEstimate(
            estimated_cost=total_cost,
            model=pricing.model,
            provider=pricing.provider,
            estimated_tokens=estimated_tokens,
            breakdown=breakdown,
            timestamp=datetime.now(timezone.utc).isoformat()
        )

    def calculate_actual_cost(
        self,
        request_id: str,
        agent_id: str,
        model: str,
        actual_tokens: TokenUsage,
        provider: Optional[ModelProvider] = None,
        metadata: Optional[Dict] = None
    ) -> CostRecord:
        """
        Calculate actual cost after API call.

        Args:
            request_id: Unique request identifier
            agent_id: Agent identifier
            model: Model identifier
            actual_tokens: Actual token usage from API response
            provider: Optional provider override
            metadata: Optional metadata to attach to record

        Returns:
            Cost record with actual costs
        """
        if not self.config.enabled:
            return self._create_zero_record(
                request_id,
                agent_id,
                model,
                provider or self.config.default_provider or 'openai',
                actual_tokens
            )

        pricing = self._get_pricing(model, provider)
        if not pricing:
            logger.warning(f"No pricing found for model: {model}")
            return self._create_zero_record(
                request_id,
                agent_id,
                model,
                provider or self.config.default_provider or 'custom',
                actual_tokens
            )

        breakdown = self._calculate_breakdown(pricing, actual_tokens)
        total_cost = sum(v for v in breakdown.model_dump().values() if v is not None)

        return CostRecord(
            id=generate_id(),
            request_id=request_id,
            agent_id=agent_id,
            model=pricing.model,
            provider=pricing.provider,
            actual_tokens=actual_tokens,
            actual_cost=total_cost,
            breakdown=breakdown,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=metadata
        )

    def add_custom_pricing(self, model: str, pricing: ModelPricing) -> None:
        """
        Add custom pricing for a model.

        Args:
            model: Model identifier
            pricing: Custom pricing information
        """
        self.custom_pricing[model] = pricing

    def remove_custom_pricing(self, model: str) -> None:
        """
        Remove custom pricing for a model.

        Args:
            model: Model identifier
        """
        self.custom_pricing.pop(model, None)

    def get_pricing(self, model: str) -> Optional[ModelPricing]:
        """
        Get pricing for a model (custom or default).

        Args:
            model: Model identifier

        Returns:
            Model pricing or None if not found
        """
        return self._get_pricing(model)

    def _get_pricing(
        self,
        model: str,
        provider: Optional[ModelProvider] = None
    ) -> Optional[ModelPricing]:
        """
        Internal method to get pricing.

        Args:
            model: Model identifier
            provider: Optional provider override

        Returns:
            Model pricing or None if not found
        """
        # Check custom pricing first
        if model in self.custom_pricing:
            return self.custom_pricing[model]

        # Fall back to default pricing
        return get_model_pricing(model, provider or self.config.default_provider)

    def _calculate_breakdown(
        self,
        pricing: ModelPricing,
        tokens: TokenUsage
    ) -> CostBreakdown:
        """
        Calculate cost breakdown.

        Args:
            pricing: Model pricing information
            tokens: Token usage

        Returns:
            Cost breakdown by component
        """
        input_cost = (tokens.input_tokens / 1000) * pricing.input_cost_per_1k
        output_cost = (tokens.output_tokens / 1000) * pricing.output_cost_per_1k

        image_cost = None
        if tokens.images and pricing.image_cost:
            image_cost = tokens.images * pricing.image_cost

        audio_cost = None
        if tokens.audio_duration and pricing.audio_cost_per_second:
            audio_cost = tokens.audio_duration * pricing.audio_cost_per_second

        return CostBreakdown(
            input_cost=input_cost,
            output_cost=output_cost,
            image_cost=image_cost,
            audio_cost=audio_cost
        )

    def _create_zero_estimate(
        self,
        model: str,
        provider: ModelProvider,
        tokens: TokenUsage
    ) -> CostEstimate:
        """
        Create zero-cost estimate.

        Args:
            model: Model identifier
            provider: Provider name
            tokens: Token usage

        Returns:
            Zero-cost estimate
        """
        return CostEstimate(
            estimated_cost=0.0,
            model=model,
            provider=provider,
            estimated_tokens=tokens,
            breakdown=CostBreakdown(input_cost=0.0, output_cost=0.0),
            timestamp=datetime.now(timezone.utc).isoformat()
        )

    def _create_zero_record(
        self,
        request_id: str,
        agent_id: str,
        model: str,
        provider: ModelProvider,
        tokens: TokenUsage
    ) -> CostRecord:
        """
        Create zero-cost record.

        Args:
            request_id: Request identifier
            agent_id: Agent identifier
            model: Model identifier
            provider: Provider name
            tokens: Token usage

        Returns:
            Zero-cost record
        """
        return CostRecord(
            id=generate_id(),
            request_id=request_id,
            agent_id=agent_id,
            model=model,
            provider=provider,
            actual_tokens=tokens,
            actual_cost=0.0,
            breakdown=CostBreakdown(input_cost=0.0, output_cost=0.0),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
