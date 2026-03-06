"""
Model Pricing Data

Up-to-date pricing information for major AI model providers
Last updated: January 2026
"""

from typing import Dict, List, Optional
from .types import ModelPricing, ModelProvider

# Pricing database for all supported models
# Prices are in USD per 1K tokens
MODEL_PRICING: Dict[str, ModelPricing] = {
    # OpenAI GPT-4 Models
    'gpt-4': ModelPricing(
        model='gpt-4',
        provider='openai',
        input_cost_per_1k=0.03,
        output_cost_per_1k=0.06,
        last_updated='2026-01-31'
    ),
    'gpt-4-32k': ModelPricing(
        model='gpt-4-32k',
        provider='openai',
        input_cost_per_1k=0.06,
        output_cost_per_1k=0.12,
        last_updated='2026-01-31'
    ),
    'gpt-4-turbo': ModelPricing(
        model='gpt-4-turbo',
        provider='openai',
        input_cost_per_1k=0.01,
        output_cost_per_1k=0.03,
        last_updated='2026-01-31'
    ),
    'gpt-4-turbo-preview': ModelPricing(
        model='gpt-4-turbo-preview',
        provider='openai',
        input_cost_per_1k=0.01,
        output_cost_per_1k=0.03,
        last_updated='2026-01-31'
    ),
    'gpt-4-vision-preview': ModelPricing(
        model='gpt-4-vision-preview',
        provider='openai',
        input_cost_per_1k=0.01,
        output_cost_per_1k=0.03,
        image_cost=0.00765,  # per image (1024x1024)
        last_updated='2026-01-31'
    ),
    
    # OpenAI GPT-3.5 Models
    'gpt-3.5-turbo': ModelPricing(
        model='gpt-3.5-turbo',
        provider='openai',
        input_cost_per_1k=0.0005,
        output_cost_per_1k=0.0015,
        last_updated='2026-01-31'
    ),
    'gpt-3.5-turbo-16k': ModelPricing(
        model='gpt-3.5-turbo-16k',
        provider='openai',
        input_cost_per_1k=0.003,
        output_cost_per_1k=0.004,
        last_updated='2026-01-31'
    ),
    
    # Anthropic Claude Models
    'claude-3-opus-20240229': ModelPricing(
        model='claude-3-opus-20240229',
        provider='anthropic',
        input_cost_per_1k=0.015,
        output_cost_per_1k=0.075,
        last_updated='2026-01-31'
    ),
    'claude-3-sonnet-20240229': ModelPricing(
        model='claude-3-sonnet-20240229',
        provider='anthropic',
        input_cost_per_1k=0.003,
        output_cost_per_1k=0.015,
        last_updated='2026-01-31'
    ),
    'claude-3-haiku-20240307': ModelPricing(
        model='claude-3-haiku-20240307',
        provider='anthropic',
        input_cost_per_1k=0.00025,
        output_cost_per_1k=0.00125,
        last_updated='2026-01-31'
    ),
    'claude-2.1': ModelPricing(
        model='claude-2.1',
        provider='anthropic',
        input_cost_per_1k=0.008,
        output_cost_per_1k=0.024,
        last_updated='2026-01-31'
    ),
    'claude-2.0': ModelPricing(
        model='claude-2.0',
        provider='anthropic',
        input_cost_per_1k=0.008,
        output_cost_per_1k=0.024,
        last_updated='2026-01-31'
    ),
    'claude-instant-1.2': ModelPricing(
        model='claude-instant-1.2',
        provider='anthropic',
        input_cost_per_1k=0.0008,
        output_cost_per_1k=0.0024,
        last_updated='2026-01-31'
    ),
    
    # Google PaLM/Gemini Models
    'gemini-pro': ModelPricing(
        model='gemini-pro',
        provider='google',
        input_cost_per_1k=0.0005,  # $0.50 per 1M tokens = $0.0005 per 1K tokens
        output_cost_per_1k=0.0015,  # $1.50 per 1M tokens = $0.0015 per 1K tokens
        last_updated='2026-03-06'
    ),
    'gemini-pro-vision': ModelPricing(
        model='gemini-pro-vision',
        provider='google',
        input_cost_per_1k=0.0005,
        output_cost_per_1k=0.0015,
        image_cost=0.0025,
        last_updated='2026-03-06'
    ),
    'gemini-ultra': ModelPricing(
        model='gemini-ultra',
        provider='google',
        input_cost_per_1k=0.007,  # $7.00 per 1M tokens = $0.007 per 1K tokens
        output_cost_per_1k=0.021,  # $21.00 per 1M tokens = $0.021 per 1K tokens
        last_updated='2026-03-06'
    ),
    'gemini-1.5-pro': ModelPricing(
        model='gemini-1.5-pro',
        provider='google',
        input_cost_per_1k=0.0005,
        output_cost_per_1k=0.0015,
        last_updated='2026-03-06'
    ),
    'palm-2': ModelPricing(
        model='palm-2',
        provider='google',
        input_cost_per_1k=0.0005,
        output_cost_per_1k=0.0005,
        last_updated='2026-01-31'
    ),
    
    # Cohere Models
    'command': ModelPricing(
        model='command',
        provider='cohere',
        input_cost_per_1k=0.001,
        output_cost_per_1k=0.002,
        last_updated='2026-01-31'
    ),
    'command-light': ModelPricing(
        model='command-light',
        provider='cohere',
        input_cost_per_1k=0.0003,
        output_cost_per_1k=0.0006,
        last_updated='2026-01-31'
    ),
    'command-nightly': ModelPricing(
        model='command-nightly',
        provider='cohere',
        input_cost_per_1k=0.001,
        output_cost_per_1k=0.002,
        last_updated='2026-01-31'
    ),
    
    # AWS Bedrock - Anthropic Claude Models
    'anthropic.claude-v2': ModelPricing(
        model='anthropic.claude-v2',
        provider='bedrock',
        input_cost_per_1k=0.008,
        output_cost_per_1k=0.024,
        last_updated='2026-03-06'
    ),
    'anthropic.claude-v2:1': ModelPricing(
        model='anthropic.claude-v2:1',
        provider='bedrock',
        input_cost_per_1k=0.008,
        output_cost_per_1k=0.024,
        last_updated='2026-03-06'
    ),
    'anthropic.claude-instant-v1': ModelPricing(
        model='anthropic.claude-instant-v1',
        provider='bedrock',
        input_cost_per_1k=0.0008,
        output_cost_per_1k=0.0024,
        last_updated='2026-03-06'
    ),
    'anthropic.claude-3-sonnet-20240229-v1:0': ModelPricing(
        model='anthropic.claude-3-sonnet-20240229-v1:0',
        provider='bedrock',
        input_cost_per_1k=0.003,
        output_cost_per_1k=0.015,
        last_updated='2026-03-06'
    ),
    'anthropic.claude-3-haiku-20240307-v1:0': ModelPricing(
        model='anthropic.claude-3-haiku-20240307-v1:0',
        provider='bedrock',
        input_cost_per_1k=0.00025,
        output_cost_per_1k=0.00125,
        last_updated='2026-03-06'
    ),
    
    # AWS Bedrock - Amazon Titan Models
    'amazon.titan-text-lite-v1': ModelPricing(
        model='amazon.titan-text-lite-v1',
        provider='bedrock',
        input_cost_per_1k=0.0003,
        output_cost_per_1k=0.0004,
        last_updated='2026-03-06'
    ),
    'amazon.titan-text-express-v1': ModelPricing(
        model='amazon.titan-text-express-v1',
        provider='bedrock',
        input_cost_per_1k=0.0008,
        output_cost_per_1k=0.0016,
        last_updated='2026-03-06'
    ),
    'amazon.titan-text-premier-v1:0': ModelPricing(
        model='amazon.titan-text-premier-v1:0',
        provider='bedrock',
        input_cost_per_1k=0.0005,
        output_cost_per_1k=0.0015,
        last_updated='2026-03-06'
    ),
    
    # AWS Bedrock - AI21 Jurassic Models
    'ai21.j2-ultra-v1': ModelPricing(
        model='ai21.j2-ultra-v1',
        provider='bedrock',
        input_cost_per_1k=0.0188,
        output_cost_per_1k=0.0188,
        last_updated='2026-03-06'
    ),
    'ai21.j2-mid-v1': ModelPricing(
        model='ai21.j2-mid-v1',
        provider='bedrock',
        input_cost_per_1k=0.0125,
        output_cost_per_1k=0.0125,
        last_updated='2026-03-06'
    ),
    
    # AWS Bedrock - Cohere Command Models
    'cohere.command-text-v14': ModelPricing(
        model='cohere.command-text-v14',
        provider='bedrock',
        input_cost_per_1k=0.0015,
        output_cost_per_1k=0.002,
        last_updated='2026-03-06'
    ),
    'cohere.command-light-text-v14': ModelPricing(
        model='cohere.command-light-text-v14',
        provider='bedrock',
        input_cost_per_1k=0.0003,
        output_cost_per_1k=0.0006,
        last_updated='2026-03-06'
    ),
    
    # AWS Bedrock - Meta Llama Models
    'meta.llama2-13b-chat-v1': ModelPricing(
        model='meta.llama2-13b-chat-v1',
        provider='bedrock',
        input_cost_per_1k=0.00075,
        output_cost_per_1k=0.001,
        last_updated='2026-03-06'
    ),
    'meta.llama2-70b-chat-v1': ModelPricing(
        model='meta.llama2-70b-chat-v1',
        provider='bedrock',
        input_cost_per_1k=0.00195,
        output_cost_per_1k=0.00256,
        last_updated='2026-03-06'
    ),
    
    # Mistral AI Models
    'mistral-small': ModelPricing(
        model='mistral-small',
        provider='mistral',
        input_cost_per_1k=0.001,
        output_cost_per_1k=0.003,
        last_updated='2026-03-06'
    ),
    'mistral-small-latest': ModelPricing(
        model='mistral-small-latest',
        provider='mistral',
        input_cost_per_1k=0.001,
        output_cost_per_1k=0.003,
        last_updated='2026-03-06'
    ),
    'mistral-medium': ModelPricing(
        model='mistral-medium',
        provider='mistral',
        input_cost_per_1k=0.0027,
        output_cost_per_1k=0.0081,
        last_updated='2026-03-06'
    ),
    'mistral-medium-latest': ModelPricing(
        model='mistral-medium-latest',
        provider='mistral',
        input_cost_per_1k=0.0027,
        output_cost_per_1k=0.0081,
        last_updated='2026-03-06'
    ),
    'mistral-large': ModelPricing(
        model='mistral-large',
        provider='mistral',
        input_cost_per_1k=0.004,
        output_cost_per_1k=0.012,
        last_updated='2026-03-06'
    ),
    'mistral-large-latest': ModelPricing(
        model='mistral-large-latest',
        provider='mistral',
        input_cost_per_1k=0.004,
        output_cost_per_1k=0.012,
        last_updated='2026-03-06'
    ),
    'mixtral-8x7b': ModelPricing(
        model='mixtral-8x7b',
        provider='mistral',
        input_cost_per_1k=0.0007,
        output_cost_per_1k=0.0007,
        last_updated='2026-03-06'
    ),
    'mixtral-8x22b': ModelPricing(
        model='mixtral-8x22b',
        provider='mistral',
        input_cost_per_1k=0.002,
        output_cost_per_1k=0.006,
        last_updated='2026-03-06'
    ),
}


def get_model_pricing(model: str, provider: Optional[ModelProvider] = None) -> Optional[ModelPricing]:
    """
    Get pricing for a specific model with fuzzy matching.
    
    Args:
        model: Model identifier
        provider: Optional provider override
        
    Returns:
        Model pricing or None if not found
    """
    # Handle empty or whitespace-only strings
    if not model or not model.strip():
        return None
    
    # Try exact match first
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    
    # Try case-insensitive match
    normalized = model.lower().strip()
    for key, pricing in MODEL_PRICING.items():
        if key.lower() == normalized:
            return pricing
    
    # Try partial match for versioned models (only if normalized is not empty)
    if normalized:
        for key, pricing in MODEL_PRICING.items():
            if normalized.startswith(key.lower()) or key.lower().startswith(normalized):
                if not provider or pricing.provider == provider:
                    return pricing
    
    return None


def get_provider_models(provider: ModelProvider) -> List[ModelPricing]:
    """
    Get all models for a specific provider.
    
    Args:
        provider: Provider name
        
    Returns:
        List of model pricing
    """
    return [p for p in MODEL_PRICING.values() if p.provider == provider]


def is_model_supported(model: str) -> bool:
    """
    Check if a model is supported.
    
    Args:
        model: Model identifier
        
    Returns:
        True if model pricing is available
    """
    return get_model_pricing(model) is not None


def get_supported_models() -> List[str]:
    """
    Get list of all supported models.
    
    Returns:
        List of model identifiers
    """
    return list(MODEL_PRICING.keys())


def get_supported_providers() -> List[ModelProvider]:
    """
    Get list of all supported providers.
    
    Returns:
        List of provider names
    """
    providers = set(p.provider for p in MODEL_PRICING.values())
    return list(providers)
