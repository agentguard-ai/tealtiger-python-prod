"""
Property-based tests for pricing lookup.

Tests universal properties of the pricing system using Hypothesis.
"""

import pytest
from hypothesis import given, strategies as st, settings

from tealtiger.cost.pricing import (
    get_model_pricing,
    get_provider_models,
    is_model_supported,
    get_supported_models,
    get_supported_providers,
    MODEL_PRICING
)
from tealtiger.cost.types import ModelProvider


@settings(max_examples=100)
@given(model=st.sampled_from(list(MODEL_PRICING.keys())))
def test_pricing_lookup_returns_valid_pricing(model: str):
    """
    Feature: python-sdk-feature-parity, Property 1: Cost estimation accuracy
    For any supported model, get_model_pricing should return valid pricing data.
    **Validates: Requirements 1.1**
    """
    pricing = get_model_pricing(model)
    
    assert pricing is not None, f"Pricing should exist for supported model: {model}"
    assert pricing.model == model or model.startswith(pricing.model), \
        f"Returned pricing model should match or be a base version of requested model"
    assert pricing.input_cost_per_1k >= 0, "Input cost should be non-negative"
    assert pricing.output_cost_per_1k >= 0, "Output cost should be non-negative"
    assert pricing.provider in ['openai', 'anthropic', 'google', 'cohere', 'azure-openai', 'bedrock', 'mistral', 'deepseek', 'groq', 'together', 'xai', 'huggingface', 'custom'], \
        f"Provider should be valid: {pricing.provider}"


@settings(max_examples=100)
@given(model=st.sampled_from(list(MODEL_PRICING.keys())))
def test_case_insensitive_lookup(model: str):
    """
    Property: Pricing lookup should be case-insensitive.
    For any supported model, lookup should work with different case variations.
    """
    pricing_original = get_model_pricing(model)
    pricing_lower = get_model_pricing(model.lower())
    pricing_upper = get_model_pricing(model.upper())
    
    assert pricing_original is not None
    assert pricing_lower is not None, f"Lowercase lookup should work for {model}"
    assert pricing_upper is not None, f"Uppercase lookup should work for {model}"
    
    # All should return the same pricing
    assert pricing_original.model == pricing_lower.model
    assert pricing_original.model == pricing_upper.model


@settings(max_examples=100)
@given(model=st.sampled_from(list(MODEL_PRICING.keys())))
def test_is_model_supported_consistency(model: str):
    """
    Property: is_model_supported should be consistent with get_model_pricing.
    If get_model_pricing returns a result, is_model_supported should return True.
    """
    pricing = get_model_pricing(model)
    supported = is_model_supported(model)
    
    if pricing is not None:
        assert supported is True, f"Model {model} has pricing but is_model_supported returns False"
    else:
        assert supported is False, f"Model {model} has no pricing but is_model_supported returns True"


@settings(max_examples=50)
@given(provider=st.sampled_from(['openai', 'anthropic', 'google', 'cohere']))
def test_provider_models_all_match_provider(provider: ModelProvider):
    """
    Property: All models returned by get_provider_models should match the requested provider.
    """
    models = get_provider_models(provider)
    
    assert len(models) > 0, f"Provider {provider} should have at least one model"
    
    for pricing in models:
        assert pricing.provider == provider, \
            f"Model {pricing.model} has provider {pricing.provider}, expected {provider}"


def test_all_supported_models_have_pricing():
    """
    Property: All models in get_supported_models should have valid pricing.
    """
    supported_models = get_supported_models()
    
    assert len(supported_models) > 0, "Should have at least one supported model"
    
    for model in supported_models:
        pricing = get_model_pricing(model)
        assert pricing is not None, f"Supported model {model} should have pricing"
        assert pricing.input_cost_per_1k >= 0
        assert pricing.output_cost_per_1k >= 0


def test_all_supported_providers_have_models():
    """
    Property: All providers in get_supported_providers should have at least one model.
    """
    supported_providers = get_supported_providers()
    
    assert len(supported_providers) > 0, "Should have at least one supported provider"
    
    for provider in supported_providers:
        models = get_provider_models(provider)
        assert len(models) > 0, f"Provider {provider} should have at least one model"


@settings(max_examples=100)
@given(
    model=st.sampled_from(list(MODEL_PRICING.keys())),
    whitespace=st.text(alphabet=' \t\n', min_size=0, max_size=3)
)
def test_pricing_lookup_handles_whitespace(model: str, whitespace: str):
    """
    Property: Pricing lookup should handle leading/trailing whitespace.
    """
    model_with_whitespace = whitespace + model + whitespace
    pricing = get_model_pricing(model_with_whitespace)
    
    assert pricing is not None, f"Lookup should work with whitespace: '{model_with_whitespace}'"
    assert pricing.model == model or model.startswith(pricing.model)


def test_unsupported_model_returns_none():
    """
    Property: Unsupported models should return None.
    """
    unsupported_models = [
        'nonexistent-model',
        'fake-gpt-99',
        'invalid-model-name',
        '',
        'xyz123'
    ]
    
    for model in unsupported_models:
        pricing = get_model_pricing(model)
        assert pricing is None, f"Unsupported model {model} should return None"
        assert not is_model_supported(model), f"Unsupported model {model} should not be supported"


@settings(max_examples=100)
@given(model=st.sampled_from(list(MODEL_PRICING.keys())))
def test_pricing_has_required_fields(model: str):
    """
    Property: All pricing entries should have required fields.
    """
    pricing = get_model_pricing(model)
    
    assert pricing is not None
    assert hasattr(pricing, 'model')
    assert hasattr(pricing, 'provider')
    assert hasattr(pricing, 'input_cost_per_1k')
    assert hasattr(pricing, 'output_cost_per_1k')
    assert hasattr(pricing, 'last_updated')
    
    # Check types
    assert isinstance(pricing.model, str)
    assert isinstance(pricing.provider, str)
    assert isinstance(pricing.input_cost_per_1k, (int, float))
    assert isinstance(pricing.output_cost_per_1k, (int, float))
    assert isinstance(pricing.last_updated, str)

