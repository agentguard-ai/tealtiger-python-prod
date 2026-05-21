"""
Unit tests for CostTracker edge cases.

Tests specific examples and edge cases for cost tracking.
"""

import pytest
from tealtiger.cost.tracker import CostTracker, CostTrackerConfig
from tealtiger.cost.types import TokenUsage, ModelPricing


def test_missing_pricing_data_returns_zero_cost():
    """
    Test missing pricing data (returns zero cost).
    **Validates: Requirements 1.8**
    """
    tracker = CostTracker()
    
    tokens = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500
    )
    
    # Test with completely unknown model
    estimate = tracker.estimate_cost('unknown-model-xyz', tokens)
    assert estimate.estimated_cost == 0.0
    assert estimate.breakdown.input_cost == 0.0
    assert estimate.breakdown.output_cost == 0.0
    
    record = tracker.calculate_actual_cost(
        request_id='req-1',
        agent_id='agent-1',
        model='unknown-model-xyz',
        actual_tokens=tokens
    )
    assert record.actual_cost == 0.0
    assert record.breakdown.input_cost == 0.0
    assert record.breakdown.output_cost == 0.0


def test_gpt_4_turbo_preview_uses_turbo_pricing():
    """Test GPT-4 Turbo preview uses Turbo pricing instead of GPT-4 pricing."""
    tracker = CostTracker()

    tokens = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500
    )

    estimate = tracker.estimate_cost('gpt-4-turbo-preview', tokens, 'openai')

    assert estimate.model == 'gpt-4-turbo-preview'
    assert estimate.provider == 'openai'
    assert estimate.estimated_cost == pytest.approx(0.025)
    assert estimate.breakdown.input_cost == pytest.approx(0.01)
    assert estimate.breakdown.output_cost == pytest.approx(0.015)


def test_versioned_gpt_4_turbo_alias_prefers_turbo_over_gpt_4():
    """Test longest-prefix matching for versioned GPT-4 Turbo aliases."""
    tracker = CostTracker()

    tokens = TokenUsage(
        input_tokens=1000,
        output_tokens=1000,
        total_tokens=2000
    )

    estimate = tracker.estimate_cost('gpt-4-turbo-2024-04-09', tokens, 'openai')

    assert estimate.model == 'gpt-4-turbo'
    assert estimate.estimated_cost == pytest.approx(0.04)


def test_vision_models_with_image_costs():
    """
    Test vision models with per-image pricing.
    **Validates: Requirements 1.10**
    """
    tracker = CostTracker()
    
    tokens = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500,
        images=3
    )
    
    # Test with gpt-4-vision-preview which has image costs
    estimate = tracker.estimate_cost('gpt-4-vision-preview', tokens)
    
    # Should include image costs
    assert estimate.breakdown.image_cost is not None
    assert estimate.breakdown.image_cost > 0
    assert estimate.estimated_cost > (estimate.breakdown.input_cost + estimate.breakdown.output_cost)


def test_audio_models_with_audio_costs():
    """
    Test audio models with per-second pricing.
    **Validates: Requirements 1.11**
    """
    tracker = CostTracker()
    
    # Add custom audio model pricing
    audio_pricing = ModelPricing(
        model='whisper-1',
        provider='openai',
        input_cost_per_1k=0.006,
        output_cost_per_1k=0.0,
        audio_cost_per_second=0.0001,
        last_updated='2026-01-31'
    )
    tracker.add_custom_pricing('whisper-1', audio_pricing)
    
    tokens = TokenUsage(
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        audio_duration=120.0  # 2 minutes
    )
    
    estimate = tracker.estimate_cost('whisper-1', tokens)
    
    # Should include audio costs
    assert estimate.breakdown.audio_cost is not None
    assert estimate.breakdown.audio_cost > 0
    expected_audio_cost = 120.0 * 0.0001
    assert abs(estimate.breakdown.audio_cost - expected_audio_cost) < 0.0001


def test_vision_model_without_images():
    """
    Test vision model without images (should not add image cost).
    """
    tracker = CostTracker()
    
    tokens = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500,
        images=None
    )
    
    estimate = tracker.estimate_cost('gpt-4-vision-preview', tokens)
    
    # Should not include image costs
    assert estimate.breakdown.image_cost is None


def test_model_without_image_pricing():
    """
    Test regular model with images parameter (should ignore images).
    """
    tracker = CostTracker()
    
    tokens = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500,
        images=5
    )
    
    # gpt-4 doesn't have image pricing
    estimate = tracker.estimate_cost('gpt-4', tokens)
    
    # Should not include image costs
    assert estimate.breakdown.image_cost is None


def test_disabled_tracker():
    """
    Test that disabled tracker returns zero costs.
    """
    config = CostTrackerConfig(enabled=False)
    tracker = CostTracker(config)
    
    tokens = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500
    )
    
    estimate = tracker.estimate_cost('gpt-4', tokens)
    assert estimate.estimated_cost == 0.0
    
    record = tracker.calculate_actual_cost(
        request_id='req-1',
        agent_id='agent-1',
        model='gpt-4',
        actual_tokens=tokens
    )
    assert record.actual_cost == 0.0


def test_default_provider_configuration():
    """
    Test default provider configuration.
    """
    config = CostTrackerConfig(default_provider='anthropic')
    tracker = CostTracker(config)
    
    # This should use the default provider if model is ambiguous
    assert tracker.config.default_provider == 'anthropic'


def test_custom_pricing_in_config():
    """
    Test custom pricing provided in configuration.
    """
    custom_pricing = {
        'my-custom-model': ModelPricing(
            model='my-custom-model',
            provider='custom',
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.02,
            last_updated='2026-01-31'
        )
    }
    
    config = CostTrackerConfig(custom_pricing=custom_pricing)
    tracker = CostTracker(config)
    
    tokens = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500
    )
    
    estimate = tracker.estimate_cost('my-custom-model', tokens)
    
    expected_cost = (1000 / 1000) * 0.01 + (500 / 1000) * 0.02
    assert abs(estimate.estimated_cost - expected_cost) < 0.0001


def test_zero_tokens():
    """
    Test with zero tokens.
    """
    tracker = CostTracker()
    
    tokens = TokenUsage(
        input_tokens=0,
        output_tokens=0,
        total_tokens=0
    )
    
    estimate = tracker.estimate_cost('gpt-4', tokens)
    assert estimate.estimated_cost == 0.0
    assert estimate.breakdown.input_cost == 0.0
    assert estimate.breakdown.output_cost == 0.0


def test_very_large_token_counts():
    """
    Test with very large token counts.
    """
    tracker = CostTracker()
    
    tokens = TokenUsage(
        input_tokens=1000000,  # 1 million tokens
        output_tokens=500000,   # 500k tokens
        total_tokens=1500000
    )
    
    estimate = tracker.estimate_cost('gpt-4', tokens)
    
    # Should handle large numbers correctly
    assert estimate.estimated_cost > 0
    assert estimate.breakdown.input_cost > 0
    assert estimate.breakdown.output_cost > 0
    
    # Verify calculation
    expected_input = (1000000 / 1000) * 0.03  # gpt-4 pricing
    expected_output = (500000 / 1000) * 0.06
    expected_total = expected_input + expected_output
    
    assert abs(estimate.estimated_cost - expected_total) < 0.01


def test_fractional_tokens():
    """
    Test with fractional token counts (should still work).
    """
    tracker = CostTracker()
    
    # Even though tokens are integers, the calculation should handle edge cases
    tokens = TokenUsage(
        input_tokens=1,
        output_tokens=1,
        total_tokens=2
    )
    
    estimate = tracker.estimate_cost('gpt-4', tokens)
    
    # Should calculate correctly for very small amounts
    assert estimate.estimated_cost > 0
    assert estimate.estimated_cost < 0.001  # Should be very small


def test_cost_record_timestamp_format():
    """
    Test that cost record timestamps are in ISO format.
    """
    tracker = CostTracker()
    
    tokens = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500
    )
    
    record = tracker.calculate_actual_cost(
        request_id='req-1',
        agent_id='agent-1',
        model='gpt-4',
        actual_tokens=tokens
    )
    
    # Timestamp should be ISO format string
    assert isinstance(record.timestamp, str)
    assert 'T' in record.timestamp  # ISO format includes 'T'
    assert len(record.timestamp) > 10  # Should be a full timestamp


def test_estimate_timestamp_format():
    """
    Test that cost estimate timestamps are in ISO format.
    """
    tracker = CostTracker()
    
    tokens = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500
    )
    
    estimate = tracker.estimate_cost('gpt-4', tokens)
    
    # Timestamp should be ISO format string
    assert isinstance(estimate.timestamp, str)
    assert 'T' in estimate.timestamp  # ISO format includes 'T'
    assert len(estimate.timestamp) > 10  # Should be a full timestamp
