"""
Property-based tests for CostTracker.

Tests universal properties of cost tracking using Hypothesis.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from tealtiger.cost.pricing import MODEL_PRICING
from tealtiger.cost.tracker import CostTracker, CostTrackerConfig
from tealtiger.cost.types import ModelPricing, TokenUsage


@settings(max_examples=100)
@given(
    model=st.sampled_from(list(MODEL_PRICING.keys())),
    input_tokens=st.integers(min_value=1, max_value=10000),
    output_tokens=st.integers(min_value=1, max_value=10000)
)
def test_cost_estimation_accuracy(model: str, input_tokens: int, output_tokens: int):
    """
    Feature: python-sdk-feature-parity, Property 1: Cost estimation accuracy
    For any model with pricing data and any token usage, the estimated cost
    should equal (input_tokens / 1000 * input_cost_per_1k) +
    (output_tokens / 1000 * output_cost_per_1k)
    **Validates: Requirements 1.1**
    """
    tracker = CostTracker()
    pricing = MODEL_PRICING[model]

    tokens = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens
    )

    estimate = tracker.estimate_cost(model, tokens)

    # Calculate expected cost
    expected_input_cost = (input_tokens / 1000) * pricing.input_cost_per_1k
    expected_output_cost = (output_tokens / 1000) * pricing.output_cost_per_1k
    expected_total = expected_input_cost + expected_output_cost

    # Verify cost calculation
    assert abs(estimate.estimated_cost - expected_total) < 0.0001, \
        f"Estimated cost {estimate.estimated_cost} should equal {expected_total}"
    assert abs(estimate.breakdown.input_cost - expected_input_cost) < 0.0001
    assert abs(estimate.breakdown.output_cost - expected_output_cost) < 0.0001
    assert estimate.model == pricing.model or model.startswith(estimate.model)
    assert estimate.provider == pricing.provider


@settings(max_examples=100)
@given(
    model=st.sampled_from(list(MODEL_PRICING.keys())),
    input_tokens=st.integers(min_value=1, max_value=10000),
    output_tokens=st.integers(min_value=1, max_value=10000),
    images=st.integers(min_value=0, max_value=10)
)
def test_cost_estimation_with_images(
    model: str,
    input_tokens: int,
    output_tokens: int,
    images: int
):
    """
    Property: Cost estimation should handle vision models with images.
    """
    tracker = CostTracker()
    pricing = MODEL_PRICING[model]

    tokens = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        images=images if images > 0 else None
    )

    estimate = tracker.estimate_cost(model, tokens)

    # Calculate expected cost
    expected_input_cost = (input_tokens / 1000) * pricing.input_cost_per_1k
    expected_output_cost = (output_tokens / 1000) * pricing.output_cost_per_1k
    expected_total = expected_input_cost + expected_output_cost

    # Add image cost if applicable
    if images > 0 and pricing.image_cost:
        expected_image_cost = images * pricing.image_cost
        expected_total += expected_image_cost
        assert abs(estimate.breakdown.image_cost - expected_image_cost) < 0.0001

    assert abs(estimate.estimated_cost - expected_total) < 0.0001


@settings(max_examples=100)
@given(
    model=st.sampled_from(list(MODEL_PRICING.keys())),
    input_tokens=st.integers(min_value=1, max_value=10000),
    output_tokens=st.integers(min_value=1, max_value=10000)
)
def test_cost_breakdown_consistency(model: str, input_tokens: int, output_tokens: int):
    """
    Feature: python-sdk-feature-parity, Property 4: Cost breakdown consistency
    For any cost calculation, the sum of input_cost and output_cost (and optional
    image_cost and audio_cost) should equal the total cost
    **Validates: Requirements 1.9**
    """
    tracker = CostTracker()

    tokens = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens
    )

    estimate = tracker.estimate_cost(model, tokens)

    # Sum all breakdown components
    breakdown_total = estimate.breakdown.input_cost + estimate.breakdown.output_cost
    if estimate.breakdown.image_cost:
        breakdown_total += estimate.breakdown.image_cost
    if estimate.breakdown.audio_cost:
        breakdown_total += estimate.breakdown.audio_cost

    # Verify breakdown sum equals total
    assert abs(estimate.estimated_cost - breakdown_total) < 0.0001, \
        f"Total cost {estimate.estimated_cost} should equal breakdown sum {breakdown_total}"


@settings(max_examples=100)
@given(
    model=st.sampled_from(list(MODEL_PRICING.keys())),
    input_tokens=st.integers(min_value=1, max_value=10000),
    output_tokens=st.integers(min_value=1, max_value=10000)
)
def test_disabled_tracker_returns_zero_cost(model: str, input_tokens: int, output_tokens: int):
    """
    Property: Disabled tracker should return zero cost.
    """
    config = CostTrackerConfig(enabled=False)
    tracker = CostTracker(config)

    tokens = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens
    )

    estimate = tracker.estimate_cost(model, tokens)

    assert estimate.estimated_cost == 0.0
    assert estimate.breakdown.input_cost == 0.0
    assert estimate.breakdown.output_cost == 0.0


def test_unsupported_model_returns_zero_cost():
    """
    Property: Unsupported models should return zero cost with warning.
    **Validates: Requirements 1.8**
    """
    tracker = CostTracker()

    tokens = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500
    )

    estimate = tracker.estimate_cost('nonexistent-model', tokens)

    assert estimate.estimated_cost == 0.0
    assert estimate.breakdown.input_cost == 0.0
    assert estimate.breakdown.output_cost == 0.0
    assert estimate.model == 'nonexistent-model'


@settings(max_examples=100)
@given(
    model=st.sampled_from(list(MODEL_PRICING.keys())),
    input_tokens=st.integers(min_value=1, max_value=10000),
    output_tokens=st.integers(min_value=1, max_value=10000)
)
def test_estimate_has_required_fields(model: str, input_tokens: int, output_tokens: int):
    """
    Property: All cost estimates should have required fields.
    """
    tracker = CostTracker()

    tokens = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens
    )

    estimate = tracker.estimate_cost(model, tokens)

    assert hasattr(estimate, 'estimated_cost')
    assert hasattr(estimate, 'model')
    assert hasattr(estimate, 'provider')
    assert hasattr(estimate, 'estimated_tokens')
    assert hasattr(estimate, 'breakdown')
    assert hasattr(estimate, 'timestamp')

    assert isinstance(estimate.estimated_cost, (int, float))
    assert estimate.estimated_cost >= 0
    assert isinstance(estimate.model, str)
    assert isinstance(estimate.provider, str)
    assert isinstance(estimate.timestamp, str)


@settings(max_examples=100)
@given(
    model=st.sampled_from(list(MODEL_PRICING.keys())),
    input_tokens=st.integers(min_value=0, max_value=10000),
    output_tokens=st.integers(min_value=0, max_value=10000)
)
def test_zero_tokens_returns_zero_cost(model: str, input_tokens: int, output_tokens: int):
    """
    Property: Zero tokens should result in zero cost.
    """
    tracker = CostTracker()

    tokens = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens
    )

    estimate = tracker.estimate_cost(model, tokens)

    if input_tokens == 0 and output_tokens == 0:
        assert estimate.estimated_cost == 0.0
        assert estimate.breakdown.input_cost == 0.0
        assert estimate.breakdown.output_cost == 0.0



# Task 3.3: Property test for actual cost calculation
@settings(max_examples=100)
@given(
    model=st.sampled_from(list(MODEL_PRICING.keys())),
    input_tokens=st.integers(min_value=1, max_value=10000),
    output_tokens=st.integers(min_value=1, max_value=10000)
)
def test_actual_cost_calculation_accuracy(model: str, input_tokens: int, output_tokens: int):
    """
    Feature: python-sdk-feature-parity, Property 2: Actual cost calculation accuracy
    For any model with pricing data and any actual token usage, the calculated cost
    should equal (input_tokens / 1000 * input_cost_per_1k) +
    (output_tokens / 1000 * output_cost_per_1k)
    **Validates: Requirements 1.2**
    """
    tracker = CostTracker()
    pricing = MODEL_PRICING[model]

    tokens = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens
    )

    record = tracker.calculate_actual_cost(
        request_id='test-request',
        agent_id='test-agent',
        model=model,
        actual_tokens=tokens
    )

    # Calculate expected cost
    expected_input_cost = (input_tokens / 1000) * pricing.input_cost_per_1k
    expected_output_cost = (output_tokens / 1000) * pricing.output_cost_per_1k
    expected_total = expected_input_cost + expected_output_cost

    # Verify cost calculation
    assert abs(record.actual_cost - expected_total) < 0.0001, \
        f"Actual cost {record.actual_cost} should equal {expected_total}"
    assert abs(record.breakdown.input_cost - expected_input_cost) < 0.0001
    assert abs(record.breakdown.output_cost - expected_output_cost) < 0.0001
    assert record.model == pricing.model or model.startswith(record.model)
    assert record.provider == pricing.provider
    assert record.request_id == 'test-request'
    assert record.agent_id == 'test-agent'


# Task 3.4: Property test for custom pricing override
@settings(max_examples=100)
@given(
    model=st.sampled_from(list(MODEL_PRICING.keys())),
    input_tokens=st.integers(min_value=1, max_value=10000),
    output_tokens=st.integers(min_value=1, max_value=10000),
    custom_input_cost=st.floats(min_value=0.0001, max_value=1.0),
    custom_output_cost=st.floats(min_value=0.0001, max_value=1.0)
)
def test_custom_pricing_override(
    model: str,
    input_tokens: int,
    output_tokens: int,
    custom_input_cost: float,
    custom_output_cost: float
):
    """
    Feature: python-sdk-feature-parity, Property 3: Custom pricing override
    For any model with custom pricing, cost calculations should use the custom
    pricing values instead of default pricing
    **Validates: Requirements 1.7**
    """
    tracker = CostTracker()

    # Add custom pricing
    custom_pricing = ModelPricing(
        model=model,
        provider='custom',
        input_cost_per_1k=custom_input_cost,
        output_cost_per_1k=custom_output_cost,
        last_updated='2026-01-31'
    )
    tracker.add_custom_pricing(model, custom_pricing)

    tokens = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens
    )

    estimate = tracker.estimate_cost(model, tokens)

    # Calculate expected cost with custom pricing
    expected_input_cost = (input_tokens / 1000) * custom_input_cost
    expected_output_cost = (output_tokens / 1000) * custom_output_cost
    expected_total = expected_input_cost + expected_output_cost

    # Verify custom pricing is used
    assert abs(estimate.estimated_cost - expected_total) < 0.0001, \
        f"Should use custom pricing: {estimate.estimated_cost} vs {expected_total}"
    assert abs(estimate.breakdown.input_cost - expected_input_cost) < 0.0001
    assert abs(estimate.breakdown.output_cost - expected_output_cost) < 0.0001


# Task 3.5: Property test for cost breakdown consistency (already covered above)
# This is the same as test_cost_breakdown_consistency


# Additional tests for custom pricing management
def test_custom_pricing_can_be_removed():
    """
    Property: Custom pricing can be added and removed.
    """
    tracker = CostTracker()
    model = 'gpt-4'

    # Add custom pricing
    custom_pricing = ModelPricing(
        model=model,
        provider='custom',
        input_cost_per_1k=0.05,
        output_cost_per_1k=0.10,
        last_updated='2026-01-31'
    )
    tracker.add_custom_pricing(model, custom_pricing)

    # Verify custom pricing is used
    pricing = tracker.get_pricing(model)
    assert pricing is not None
    assert pricing.input_cost_per_1k == 0.05
    assert pricing.output_cost_per_1k == 0.10

    # Remove custom pricing
    tracker.remove_custom_pricing(model)

    # Verify default pricing is used again
    pricing = tracker.get_pricing(model)
    assert pricing is not None
    assert pricing.input_cost_per_1k == MODEL_PRICING[model].input_cost_per_1k
    assert pricing.output_cost_per_1k == MODEL_PRICING[model].output_cost_per_1k


@settings(max_examples=100)
@given(
    model=st.sampled_from(list(MODEL_PRICING.keys())),
    input_tokens=st.integers(min_value=1, max_value=10000),
    output_tokens=st.integers(min_value=1, max_value=10000)
)
def test_actual_cost_record_has_unique_id(model: str, input_tokens: int, output_tokens: int):
    """
    Property: Each cost record should have a unique ID.
    """
    tracker = CostTracker()

    tokens = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens
    )

    # Create multiple records
    record1 = tracker.calculate_actual_cost(
        request_id='req-1',
        agent_id='agent-1',
        model=model,
        actual_tokens=tokens
    )

    record2 = tracker.calculate_actual_cost(
        request_id='req-2',
        agent_id='agent-1',
        model=model,
        actual_tokens=tokens
    )

    # IDs should be different
    assert record1.id != record2.id
    assert len(record1.id) > 0
    assert len(record2.id) > 0


@settings(max_examples=100)
@given(
    model=st.sampled_from(list(MODEL_PRICING.keys())),
    input_tokens=st.integers(min_value=1, max_value=10000),
    output_tokens=st.integers(min_value=1, max_value=10000)
)
def test_cost_record_preserves_metadata(model: str, input_tokens: int, output_tokens: int):
    """
    Property: Cost records should preserve metadata.
    """
    tracker = CostTracker()

    tokens = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens
    )

    metadata = {
        'user_id': 'user-123',
        'session_id': 'session-456',
        'custom_field': 'custom_value'
    }

    record = tracker.calculate_actual_cost(
        request_id='test-request',
        agent_id='test-agent',
        model=model,
        actual_tokens=tokens,
        metadata=metadata
    )

    assert record.metadata is not None
    assert record.metadata['user_id'] == 'user-123'
    assert record.metadata['session_id'] == 'session-456'
    assert record.metadata['custom_field'] == 'custom_value'

